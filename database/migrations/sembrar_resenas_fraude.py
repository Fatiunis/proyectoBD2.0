"""
Siembra de reseñas (Mongo + Neo4j) con un patrón de fraude real para la Entrega 2.

Propósito
---------
El sistema de reseñas ya existe (col_resenas en Mongo + espejo en Neo4j vía
backend/app/blueprints/resenas.py). Lo que falta es DATO: necesitamos un
catálogo de reseñas donde exista "ruido" legítimo (reseñas normales, variadas,
de autores distintos) y, escondido dentro de ese ruido, un anillo de fraude
real -- un grupo pequeño de cuentas que se reseñan entre sí, concentradas en
el catálogo de UN mismo vendedor, en una ventana de tiempo muy corta -- para
que la consulta de detección de fraude (que construirá otro agente después)
tenga un patrón genuino que encontrar. También sembramos un "anillo débil" de
control que comparte menos productos de los que el umbral de detección exige,
para poder demostrar en el informe que el umbral no genera falsos positivos.

Este script es standalone y va en database/migrations/ siguiendo el mismo
estilo que migracion_postgres_a_mongo.py: se conecta a Postgres (para leer
compradores reales, nunca IDs fijos) y a Mongo (para leer el catálogo real de
productos, nunca IDs fijos), y además sincroniza cada reseña a Neo4j con el
mismo patrón MERGE que ya usa el blueprint de reseñas.

Idempotencia
------------
Al igual que migracion_postgres_a_mongo.py recrea sus colecciones desde cero
cada vez que se corre, este script BORRA primero cualquier reseña/relación de
fraude previa (col_resenas completa en Mongo, y el subgrafo Cuenta-CALIFICO-
Producto en Neo4j) antes de volver a sembrar. Es un script de DATOS DE PRUEBA
para la demo de detección de fraude -- no un proceso pensado para correr en
producción sobre reseñas reales de usuarios. Además, la selección de qué
cuentas/productos forman cada anillo es determinística (ordenada por ID, con
una semilla fija para el azar de textos/fechas), así que volver a correrlo
produce siempre el mismo patrón (mismos anillos, mismos conteos), aunque los
_id de Mongo generados para cada documento sean nuevos en cada corrida.
"""
import os
import sys
import random
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from pymongo import MongoClient
from neo4j import GraphDatabase

# La consola de Windows no usa UTF-8 por defecto; forzamos la codificación de
# salida para que el script corra igual en todo el equipo (mismo criterio que
# migracion_postgres_a_mongo.py).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# ============================================================================
# CONFIGURACIÓN DE CONEXIONES (mismo patrón que migracion_postgres_a_mongo.py)
# ============================================================================
PG_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DBNAME", "tiendaya_db"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "root"),
}

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "tiendaya_nosql")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "tiendaya123")

# Guatemala usa UTC-6 fijo todo el año (sin horario de verano), consistente
# con backend/app/extensions.py y migracion_postgres_a_mongo.py.
ZONA_GUATEMALA = timezone(timedelta(hours=-6))

# Semilla fija: los textos y las fechas de las reseñas se generan con
# `random`, pero con esta semilla el resultado es reproducible entre
# corridas (mismo patrón de fraude, mismos conteos) tal como exige la
# verificación de idempotencia.
random.seed(42)

# ============================================================================
# TEXTOS DE RESEÑA
# ============================================================================
# Ruido legítimo: pool variado para que no se vea artificial (evitamos repetir
# literalmente el mismo texto en reseñas normales).
FRASES_RUIDO = [
    "Buen producto, cumple lo esperado.",
    "Tardó un poco en llegar pero llegó en buen estado.",
    "Cinco estrellas, lo recomiendo ampliamente.",
    "La calidad es aceptable por el precio que pagué.",
    "No era exactamente lo que esperaba, pero funciona bien.",
    "Excelente atención del vendedor y entrega rápida.",
    "Cumple con la descripción, quedé satisfecho con la compra.",
    "Buena relación calidad-precio, volvería a comprar.",
    "El empaque llegó algo golpeado pero el producto está intacto.",
    "Superó mis expectativas, muy contento con la compra.",
]

# Anillo de fraude: textos cortos y genéricos, intencionalmente repetitivos
# (así se ve un patrón de reseñas "compradas" en vez de opiniones reales).
FRASES_FRAUDE = [
    "Excelente producto!",
    "Muy recomendado, 100%",
    "Increíble calidad",
]


def conectar_todo():
    """Abre las tres conexiones (Postgres, Mongo, Neo4j) y valida que respondan."""
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        print("[OK] Conectado a PostgreSQL")
    except Exception as e:
        print(f"[X] Error conectando a PostgreSQL: {e}")
        sys.exit(1)

    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command("ping")
        mongo_db = mongo_client[MONGO_DB_NAME]
        print("[OK] Conectado a MongoDB")
    except Exception as e:
        print(f"[X] Error conectando a MongoDB: {e}")
        sys.exit(1)

    try:
        neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        neo4j_driver.verify_connectivity()
        print("[OK] Conectado a Neo4j")
    except Exception as e:
        print(f"[X] Error conectando a Neo4j: {e}")
        sys.exit(1)

    return pg_conn, mongo_client, mongo_db, neo4j_driver


def obtener_compradores_reales(pg_conn):
    """Lee TODOS los compradores actuales de Postgres, sin asumir IDs fijos."""
    cursor = pg_conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id_usuario, nombre FROM usuarios WHERE rol = 'comprador' ORDER BY id_usuario ASC")
    compradores = cursor.fetchall()
    cursor.close()
    return [dict(c) for c in compradores]


def obtener_productos_activos(mongo_db):
    """Lee el catálogo real de productos activos desde Mongo, sin asumir IDs fijos."""
    col_productos = mongo_db["productos"]
    cursor = col_productos.find(
        {"activo": True},
        {"_id": 1, "nombre": 1, "sku": 1, "id_sql_origen": 1, "vendedor": 1},
    ).sort("_id", 1)
    return list(cursor)


def elegir_vendedor_para_el_anillo(productos):
    """
    Agrupa los productos activos por vendedor y elige el vendedor con más
    productos (mínimo 3, idealmente 4+) para armar el anillo de fraude fuerte
    sobre SU catálogo -- el patrón típico de fraude es concentrado en un solo
    vendedor, no disperso entre varios.
    """
    por_vendedor = {}
    for p in productos:
        vendedor = p.get("vendedor") or {}
        id_vendedor = vendedor.get("id_vendedor")
        por_vendedor.setdefault(id_vendedor, {"nombre_comercial": vendedor.get("nombre_comercial"), "productos": []})
        por_vendedor[id_vendedor]["productos"].append(p)

    candidatos = [(id_v, info) for id_v, info in por_vendedor.items() if len(info["productos"]) >= 3]
    if not candidatos:
        print("[X] Ningún vendedor tiene al menos 3 productos activos; no se puede armar el anillo de fraude.")
        sys.exit(1)

    # El de mayor catálogo primero; a igualdad, el id_vendedor más bajo (determinismo).
    candidatos.sort(key=lambda item: (-len(item[1]["productos"]), item[0]))
    id_vendedor_elegido, info = candidatos[0]
    return id_vendedor_elegido, info["nombre_comercial"], info["productos"]


def limpiar_datos_previos(mongo_db, neo4j_driver):
    """
    Paso 1: borra cualquier reseña/fraude sembrado en una corrida anterior
    para partir de un estado limpio y reproducible. Solo toca `resenas` en
    Mongo (no `productos` ni `historial_cambios_productos`) y solo el
    subgrafo Cuenta-CALIFICO-Producto en Neo4j (no otros nodos/relaciones).
    Es intencional -- mismo criterio que migracion_postgres_a_mongo.py, que
    también recrea sus colecciones desde cero al re-correrse.
    """
    col_resenas = mongo_db["resenas"]
    borradas = col_resenas.delete_many({}).deleted_count
    print(f"[*] Limpieza Mongo: {borradas} reseña(s) previa(s) eliminada(s) de 'resenas'")

    with neo4j_driver.session() as session:
        resultado = session.run("MATCH (c:Cuenta)-[r:CALIFICO]->(p:Producto) DELETE r, c, p")
        resultado.consume()
    print("[*] Limpieza Neo4j: subgrafo Cuenta-CALIFICO-Producto anterior eliminado")

    # Reconstruye el índice único (idempotente, mismo criterio que resenas.py).
    col_resenas.create_index([("producto_id", 1), ("autor.id_usuario", 1)], unique=True)


def insertar_resena(col_resenas, neo4j_driver, *, producto, autor, calificacion, texto, fecha, pares_usados):
    """
    Inserta una reseña en Mongo (respetando el índice único producto/autor) y
    la espeja en Neo4j con el MISMO patrón MERGE que usa
    backend/app/blueprints/resenas.py -> _sincronizar_neo4j, para no divergir
    del modelo real que usa la aplicación.
    """
    producto_id = producto["_id"]
    clave_par = (producto_id, autor["id_usuario"])
    if clave_par in pares_usados:
        return False  # ya existe esta combinación producto/autor; se omite silenciosamente.

    doc_resena = {
        "producto_id": producto_id,
        "id_sql_origen_producto": producto.get("id_sql_origen"),
        "autor": {"id_usuario": autor["id_usuario"], "nombre": autor["nombre"], "rol": "comprador"},
        "calificacion": calificacion,
        "texto": texto,
        "fecha_creacion": fecha,
    }
    resultado = col_resenas.insert_one(doc_resena)
    pares_usados.add(clave_par)

    query = """
        MERGE (c:Cuenta {id_usuario: $id_usuario})
          SET c.nombre = $nombre, c.rol = $rol
        MERGE (p:Producto {id_producto: $producto_id})
          SET p.nombre = $nombre_producto, p.sku = $sku
        MERGE (c)-[r:CALIFICO]->(p)
          SET r.calificacion = $calificacion, r.fecha = $fecha, r.id_resena = $id_resena
    """
    with neo4j_driver.session() as session:
        session.run(
            query,
            id_usuario=autor["id_usuario"],
            nombre=autor["nombre"],
            rol="comprador",
            producto_id=producto_id,
            nombre_producto=producto.get("nombre"),
            sku=producto.get("sku"),
            calificacion=calificacion,
            fecha=fecha.isoformat(),
            id_resena=str(resultado.inserted_id),
        )
    return True


def sembrar_anillo_fuerte(col_resenas, neo4j_driver, compradores_anillo, productos_anillo, pares_usados):
    """
    Paso 3: 4 cuentas se reseñan mutuamente sobre los MISMOS 4 productos de un
    mismo vendedor (16 reseñas), calificación 5 fija, textos cortos genéricos,
    fechas concentradas en una ventana de pocas horas del mismo día (actividad
    coordinada). Se ejecuta ANTES del ruido para que el ruido pueda evitar
    estos pares exactos.
    """
    # Día base: hace 5 días (dentro de la ventana de "últimos 30 días" del
    # ruido, pero fijo y determinístico gracias a random.seed(42) más arriba
    # solo se usa para el resto de aleatoriedad; aquí usamos un offset fijo
    # para que la ventana de coordinación sea siempre la misma entre corridas).
    dia_base = datetime.now(ZONA_GUATEMALA).replace(hour=14, minute=0, second=0, microsecond=0) - timedelta(days=5)

    contador = 0
    minutos_transcurridos = 0
    for comprador in compradores_anillo:
        for producto in productos_anillo:
            fecha = dia_base + timedelta(minutes=minutos_transcurridos)
            minutos_transcurridos += random.randint(3, 12)  # ráfaga de actividad en pocas horas
            texto = random.choice(FRASES_FRAUDE)
            if insertar_resena(
                col_resenas, neo4j_driver,
                producto=producto, autor=comprador, calificacion=5, texto=texto, fecha=fecha,
                pares_usados=pares_usados,
            ):
                contador += 1
    return contador


def sembrar_anillo_debil(col_resenas, neo4j_driver, compradores_anillo, productos_anillo, pares_usados):
    """
    Paso 4: 2 cuentas de control califican los MISMOS 2 productos (4 reseñas),
    calificación 4-5, fechas dispersas normales. Sirve para demostrar que con
    un umbral de "≥3 productos compartidos" este par NO se marca como
    sospechoso (solo comparte 2), a diferencia del anillo fuerte del paso 3.
    """
    ahora = datetime.now(ZONA_GUATEMALA)
    contador = 0
    for comprador in compradores_anillo:
        for producto in productos_anillo:
            fecha = ahora - timedelta(days=random.randint(1, 29), hours=random.randint(0, 23), minutes=random.randint(0, 59))
            calificacion = random.randint(4, 5)
            texto = random.choice(FRASES_RUIDO)
            if insertar_resena(
                col_resenas, neo4j_driver,
                producto=producto, autor=comprador, calificacion=calificacion, texto=texto, fecha=fecha,
                pares_usados=pares_usados,
            ):
                contador += 1
    return contador


def sembrar_ruido_legitimo(col_resenas, neo4j_driver, compradores, productos, pares_usados, ids_grupo_control=None):
    """
    Paso 2: para cada producto activo del catálogo, entre 2 y 4 reseñas de
    autores distintos elegidos al azar entre TODOS los compradores, evitando
    los pares (producto, autor) ya usados por los anillos de fraude/control.

    Protección del anillo débil: si el ruido pudiera coincidir en agregar, por
    puro azar, a las DOS cuentas del anillo débil de control como autoras del
    mismo producto, eso les sumaría un producto compartido incidental y
    haría que superen el umbral de detección -- justo lo que el anillo débil
    debe demostrar que NO ocurre. `ids_grupo_control` recibe ese par de IDs
    para que, cuando ambas resulten elegibles para un mismo producto, se
    excluya una de ellas del sorteo (deja participar a la otra igual, solo se
    evita que las dos coincidan juntas fuera de sus 2 productos designados).
    """
    ahora = datetime.now(ZONA_GUATEMALA)
    total_insertadas = 0
    ids_grupo_control = ids_grupo_control or set()
    for producto in productos:
        producto_id = producto["_id"]
        autores_disponibles = [c for c in compradores if (producto_id, c["id_usuario"]) not in pares_usados]

        presentes_del_grupo_control = [c for c in autores_disponibles if c["id_usuario"] in ids_grupo_control]
        if len(presentes_del_grupo_control) >= 2:
            # Excluimos a la de mayor id_usuario para no romper el determinismo
            # entre corridas; la otra sigue siendo elegible normalmente.
            excluir_id = max(c["id_usuario"] for c in presentes_del_grupo_control)
            autores_disponibles = [c for c in autores_disponibles if c["id_usuario"] != excluir_id]

        cantidad = min(random.randint(2, 4), len(autores_disponibles))
        if cantidad <= 0:
            continue
        autores_elegidos = random.sample(autores_disponibles, cantidad)
        for autor in autores_elegidos:
            fecha = ahora - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23), minutes=random.randint(0, 59))
            calificacion = random.randint(2, 5)
            texto = random.choice(FRASES_RUIDO)
            if insertar_resena(
                col_resenas, neo4j_driver,
                producto=producto, autor=autor, calificacion=calificacion, texto=texto, fecha=fecha,
                pares_usados=pares_usados,
            ):
                total_insertadas += 1
    return total_insertadas


def ejecutar_siembra():
    print("==================================================================")
    print(" SIEMBRA DE RESEÑAS CON PATRÓN DE FRAUDE (Mongo + Neo4j)")
    print("==================================================================")

    pg_conn, mongo_client, mongo_db, neo4j_driver = conectar_todo()
    col_resenas = mongo_db["resenas"]

    # --- Datos reales, leídos dinámicamente (nunca IDs fijos) ---
    compradores = obtener_compradores_reales(pg_conn)
    print(f"[*] Compradores reales encontrados en Postgres: {len(compradores)}")
    if len(compradores) < 6:
        print("[X] Se necesitan al menos 6 compradores (4 anillo fuerte + 2 anillo débil).")
        sys.exit(1)

    productos_activos = obtener_productos_activos(mongo_db)
    print(f"[*] Productos activos encontrados en Mongo: {len(productos_activos)}")
    if not productos_activos:
        print("[X] No hay productos activos en Mongo; corre primero la migración del catálogo.")
        sys.exit(1)

    id_vendedor, nombre_vendedor, productos_del_vendedor = elegir_vendedor_para_el_anillo(productos_activos)
    print(f"[*] Vendedor elegido para el anillo de fraude: '{nombre_vendedor}' (id_vendedor={id_vendedor}), "
          f"{len(productos_del_vendedor)} producto(s) activos")

    # --- Paso 1: limpieza ---
    limpiar_datos_previos(mongo_db, neo4j_driver)

    # --- Selección determinística de los anillos (ordenados por ID) ---
    n_fuerte = min(4, len(productos_del_vendedor))
    productos_anillo_fuerte = productos_del_vendedor[:n_fuerte]
    productos_restantes_vendedor = productos_del_vendedor[n_fuerte:]
    productos_anillo_debil = productos_restantes_vendedor[:2] if len(productos_restantes_vendedor) >= 2 else productos_del_vendedor[:2]

    compradores_anillo_fuerte = compradores[:4]
    compradores_restantes = compradores[4:]
    compradores_anillo_debil = compradores_restantes[:2] if len(compradores_restantes) >= 2 else compradores[4:6]

    pares_usados = set()

    # --- Paso 3: anillo de fraude fuerte (ANTES del ruido, para que el ruido lo evite) ---
    total_fuerte = sembrar_anillo_fuerte(col_resenas, neo4j_driver, compradores_anillo_fuerte, productos_anillo_fuerte, pares_usados)

    # --- Paso 4: anillo débil de control (también antes del ruido) ---
    total_debil = sembrar_anillo_debil(col_resenas, neo4j_driver, compradores_anillo_debil, productos_anillo_debil, pares_usados)

    # --- Paso 2: ruido legítimo sobre todo el catálogo activo ---
    ids_grupo_control = {c["id_usuario"] for c in compradores_anillo_debil}
    total_ruido = sembrar_ruido_legitimo(
        col_resenas, neo4j_driver, compradores, productos_activos, pares_usados,
        ids_grupo_control=ids_grupo_control,
    )

    # ========================================================================
    # RESUMEN FINAL
    # ========================================================================
    total_mongo = col_resenas.count_documents({})
    with neo4j_driver.session() as session:
        n_cuentas = session.run("MATCH (c:Cuenta) RETURN count(c) AS n").single()["n"]
        n_productos_grafo = session.run("MATCH (p:Producto) RETURN count(p) AS n").single()["n"]
        n_relaciones = session.run("MATCH ()-[r:CALIFICO]->() RETURN count(r) AS n").single()["n"]

    print("==================================================================")
    print(" RESUMEN DE LA SIEMBRA")
    print("==================================================================")
    print(f"[*] Ruido legítimo insertado: {total_ruido} reseña(s)")
    print(f"[*] Anillo de fraude FUERTE insertado: {total_fuerte} reseña(s) (esperado 16, o menos si hubo choque de pares)")
    print("    Cuentas del anillo fuerte:")
    for c in compradores_anillo_fuerte:
        print(f"      - id_usuario={c['id_usuario']}  {c['nombre']}")
    print(f"    Productos del anillo fuerte (vendedor '{nombre_vendedor}'):")
    for p in productos_anillo_fuerte:
        print(f"      - {p['_id']}  {p['nombre']}")

    print(f"[*] Anillo débil de control insertado: {total_debil} reseña(s) (esperado 4)")
    print("    Cuentas del anillo débil:")
    for c in compradores_anillo_debil:
        print(f"      - id_usuario={c['id_usuario']}  {c['nombre']}")
    print("    Productos del anillo débil:")
    for p in productos_anillo_debil:
        print(f"      - {p['_id']}  {p['nombre']}")

    print(f"[*] Total de reseñas en Mongo (col 'resenas'): {total_mongo}")
    print(f"[*] Neo4j -> nodos Cuenta: {n_cuentas}, nodos Producto: {n_productos_grafo}, relaciones CALIFICO: {n_relaciones}")
    print("==================================================================")
    print(" SIEMBRA COMPLETADA")
    print("==================================================================")

    pg_conn.close()
    mongo_client.close()
    neo4j_driver.close()


if __name__ == "__main__":
    ejecutar_siembra()
