"""Componente vectorial (entrega final): recomendación y búsqueda semántica.

Los embeddings de los productos viven en PostgreSQL + pgvector (contenedor
"vectores", tabla producto_embedding; esquema en database/vectores/). Son una
proyección derivada del catálogo de MongoDB, que sigue siendo la fuente de
verdad: este módulo nunca guarda en pgvector algo que no esté ya en Mongo.

Lo usan:
  - el blueprint de recomendaciones (productos relacionados y búsqueda
    semántica),
  - el catálogo (recalcula el embedding al guardar un producto),
  - el relevo del outbox (reintenta ese cálculo si pgvector no respondía),
  - el script database/migrations/generar_embeddings_productos.py (carga
    completa).

El modelo de lenguaje se carga de forma perezosa la primera vez que hace falta
convertir texto en vector (guardar un producto o una búsqueda semántica): los
productos relacionados solo comparan vectores ya guardados y no lo necesitan.
Detalle de la decisión: docs/decisiones/ADR-008-componente-vectorial.md
"""

import hashlib
import threading

from sqlalchemy import create_engine, text

from .config import VECTORES_URI, MODELO_EMBEDDINGS

DIMENSIONES = 384

# Diversificación de productos relacionados: dos candidatos con similitud
# coseno mayor a este umbral se consideran variantes del mismo producto (misma
# laptop con otra RAM, misma playera en otra talla). Medido sobre el catálogo:
# las variantes quedan entre 0.93 y 0.996; productos distintos de la misma
# categoría, por debajo de 0.90.
UMBRAL_VARIANTE = 0.93

# Engine propio (no el de Flask-SQLAlchemy, que apunta al PostgreSQL
# transaccional). pool_pre_ping: si el contenedor se reinició, la conexión
# muerta se descarta en vez de fallar la primera petición.
engine = create_engine(VECTORES_URI, pool_pre_ping=True, pool_size=5, connect_args={"connect_timeout": 3})

_modelo = None
_candado_modelo = threading.Lock()


def modelo():
    global _modelo
    if _modelo is None:
        with _candado_modelo:
            if _modelo is None:
                # Import aquí: sentence-transformers trae torch y tarda unos
                # segundos en importar; el servidor arranca sin pagar ese costo.
                from sentence_transformers import SentenceTransformer
                print(f"[vectores] Cargando modelo de embeddings {MODELO_EMBEDDINGS}...")
                _modelo = SentenceTransformer(MODELO_EMBEDDINGS, device="cpu")
    return _modelo


def vectorizar(textos):
    """Lista de textos -> lista de vectores normalizados (norma 1), así la
    distancia coseno de pgvector (<=>) equivale a 1 - producto punto."""
    return modelo().encode(textos, normalize_embeddings=True, batch_size=64, show_progress_bar=False).tolist()


def _literal(vector):
    # pgvector acepta el vector como texto '[x1,x2,...]' con cast ::vector; así
    # no hace falta un adaptador extra para psycopg2.
    return "[" + ",".join(f"{x:.7f}" for x in vector) + "]"


# ---------------------------------------------------------------- texto fuente


def texto_producto(doc):
    """Texto que representa al producto para la similitud semántica: nombre,
    categoría y descripción. Los atributos técnicos (RAM, talla...) quedan
    fuera a propósito: los compara mejor el buscador por facetas, y aquí solo
    meterían ruido numérico."""
    categoria = (doc.get("categoria") or {}).get("nombre") or ""
    partes = [doc.get("nombre") or "", categoria, doc.get("descripcion") or ""]
    return ". ".join(p.strip() for p in partes if p and p.strip())


def hash_texto(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- escritura


def guardar_embeddings(docs, forzar=False):
    """Calcula y guarda (upsert) los embeddings de una lista de documentos de
    Mongo. Solo vuelve a vectorizar los productos cuyo texto o modelo cambió;
    al resto solo les actualiza activo/categoría. Idempotente.

    Devuelve {"calculados": n, "sin_cambios": n}."""
    if not docs:
        return {"calculados": 0, "sin_cambios": 0}
    ids = [str(d["_id"]) for d in docs]
    with engine.connect() as con:
        vigentes = {
            fila.producto_id: (fila.texto_hash, fila.modelo)
            for fila in con.execute(
                text("SELECT producto_id, texto_hash, modelo FROM producto_embedding WHERE producto_id = ANY(:ids)"),
                {"ids": ids},
            )
        }

    pendientes, sin_cambios = [], []
    for d in docs:
        texto = texto_producto(d)
        h = hash_texto(texto)
        fila = {
            "producto_id": str(d["_id"]),
            "id_categoria": (d.get("categoria") or {}).get("id_categoria"),
            "activo": bool(d.get("activo", True)),
            "texto_hash": h,
            "texto": texto,
        }
        if not forzar and vigentes.get(fila["producto_id"]) == (h, MODELO_EMBEDDINGS):
            sin_cambios.append(fila)
        else:
            pendientes.append(fila)

    if pendientes:
        vectores = vectorizar([f["texto"] for f in pendientes])
        for f, v in zip(pendientes, vectores):
            f["embedding"] = _literal(v)

    with engine.begin() as con:
        if pendientes:
            con.execute(text("""
                INSERT INTO producto_embedding
                    (producto_id, id_categoria, activo, texto_hash, modelo, embedding, actualizado_en)
                VALUES (:producto_id, :id_categoria, :activo, :texto_hash, :modelo, CAST(:embedding AS vector), now())
                ON CONFLICT (producto_id) DO UPDATE SET
                    id_categoria = EXCLUDED.id_categoria,
                    activo = EXCLUDED.activo,
                    texto_hash = EXCLUDED.texto_hash,
                    modelo = EXCLUDED.modelo,
                    embedding = EXCLUDED.embedding,
                    actualizado_en = now()
            """), [{**f, "modelo": MODELO_EMBEDDINGS} for f in pendientes])
        if sin_cambios:
            con.execute(text("""
                UPDATE producto_embedding SET id_categoria = :id_categoria, activo = :activo
                WHERE producto_id = :producto_id
                  AND (id_categoria IS DISTINCT FROM :id_categoria OR activo IS DISTINCT FROM :activo)
            """), sin_cambios)
    return {"calculados": len(pendientes), "sin_cambios": len(sin_cambios)}


def guardar_embedding_producto(doc):
    return guardar_embeddings([doc])


# ---------------------------------------------------------------- consultas


def _vecinos(sql_vector, params, limite, excluir=None, id_categoria=None, con_vector=False):
    """Vecinos más cercanos por distancia coseno, solo productos activos.

    hnsw.iterative_scan (pgvector >= 0.8): con un WHERE, el índice HNSW sigue
    buscando candidatos hasta llenar el LIMIT en vez de devolver menos filas
    de las pedidas cuando el filtro descarta vecinos."""
    filtros = ["activo"]
    if excluir is not None:
        filtros.append("producto_id <> :excluir")
        params["excluir"] = excluir
    if id_categoria is not None:
        filtros.append("id_categoria = :id_categoria")
        params["id_categoria"] = id_categoria
    params["limite"] = limite
    sql = f"""
        SELECT producto_id, 1 - (embedding <=> {sql_vector}) AS similitud
               {", embedding::text AS vector" if con_vector else ""}
        FROM producto_embedding
        WHERE {" AND ".join(filtros)}
        ORDER BY embedding <=> {sql_vector}
        LIMIT :limite
    """
    with engine.begin() as con:
        con.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        con.execute(text("SET LOCAL hnsw.ef_search = 100"))
        filas = con.execute(text(sql), params).all()
    # relaxed_order puede devolver el orden ligeramente alterado: se reordena
    # por similitud ya con las filas en memoria.
    if con_vector:
        return sorted(
            ((f.producto_id, float(f.similitud), [float(x) for x in f.vector[1:-1].split(",")]) for f in filas),
            key=lambda x: -x[1],
        )
    return sorted(((f.producto_id, float(f.similitud)) for f in filas), key=lambda x: -x[1])


def _diversificar(candidatos, limite):
    """Selección voraz al estilo MMR: recorre los candidatos de más a menos
    parecido al producto de origen y salta los que son casi idénticos
    (> UMBRAL_VARIANTE) a uno ya elegido. Si con eso no se llena el límite,
    completa con los saltados en el mismo orden."""
    elegidos, saltados = [], []
    for pid, sim, vec in candidatos:
        if len(elegidos) == limite:
            break
        es_variante = any(sum(a * b for a, b in zip(vec, v)) > UMBRAL_VARIANTE for _, _, v in elegidos)
        (saltados if es_variante else elegidos).append((pid, sim, vec))
    elegidos += saltados[: limite - len(elegidos)]
    return [(pid, sim) for pid, sim, _ in elegidos]


def relacionados(producto_id, limite=6, misma_categoria=False, diversificar=True):
    """Productos más parecidos semánticamente a uno dado. Devuelve None si ese
    producto todavía no tiene embedding.

    diversificar: pide 5 veces más candidatos y descarta variantes casi
    idénticas entre sí (ver _diversificar), para no recomendar cuatro veces la
    misma laptop con distinta RAM."""
    with engine.connect() as con:
        fila = con.execute(
            text("SELECT id_categoria FROM producto_embedding WHERE producto_id = :id"), {"id": producto_id}
        ).first()
    if fila is None:
        return None
    candidatos = _vecinos(
        "(SELECT embedding FROM producto_embedding WHERE producto_id = :origen)",
        {"origen": producto_id},
        limite * 5 if diversificar else limite,
        excluir=producto_id,
        id_categoria=fila.id_categoria if misma_categoria else None,
        con_vector=diversificar,
    )
    return _diversificar(candidatos, limite) if diversificar else candidatos


def buscar(consulta, limite=12, id_categoria=None):
    """Búsqueda semántica: el texto libre se convierte en vector con el mismo
    modelo y se buscan los productos más cercanos."""
    vector = vectorizar([consulta])[0]
    return _vecinos("CAST(:vector AS vector)", {"vector": _literal(vector)}, limite, id_categoria=id_categoria)


def estado():
    with engine.connect() as con:
        fila = con.execute(text("""
            SELECT count(*) AS total, count(*) FILTER (WHERE activo) AS activos,
                   max(actualizado_en) AS ultima, array_agg(DISTINCT modelo) AS modelos
            FROM producto_embedding
        """)).first()
    return {
        "total": fila.total,
        "activos": fila.activos,
        "ultima_actualizacion": fila.ultima.isoformat() if fila.ultima else None,
        "modelos": [m for m in (fila.modelos or []) if m],
    }
