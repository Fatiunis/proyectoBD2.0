"""
Prueba de la recomendación y la búsqueda semántica (entrega final).

Standalone: NO es parte de la app Flask. Se corre contra un servidor real ya
levantado (python backend/main.py) con MongoDB, Elasticsearch y el contenedor
"vectores" (PostgreSQL + pgvector) disponibles, y con los embeddings ya
generados (database/migrations/generar_embeddings_productos.py).

Verifica:
  R1  Cobertura: hay un embedding por cada producto del catálogo de MongoDB.
  R2  Productos relacionados: para un producto de cada categoría, los
      recomendados son de la misma categoría o de una afín, nunca incluyen al
      propio producto, y la diversificación quita variantes casi idénticas.
  R3  Búsqueda semántica: frases en lenguaje natural, sin las palabras exactas
      del catálogo, encuentran la categoría esperada; se compara con lo que
      devuelve el buscador léxico (Elasticsearch) para la misma frase. Se
      exige una tasa de acierto (>= 75 %), no el 100 %: los fallos se muestran
      y están documentados como limitación del modelo.
  R4  Índice HNSW: el índice existe y es utilizable; se mide la consulta con
      el plan que elige PostgreSQL y forzando el índice (con ~1000 filas el
      planificador prefiere un recorrido exacto, que es más barato).
  R5  Sincronización: cambiar la descripción de un producto recalcula solo su
      embedding (hash del texto) y deshacer el cambio lo deja como estaba.
  R6  Permisos en pgvector: vectores_app no puede cambiar el esquema y
      vectores_lector no puede escribir.
  R7  (opcional, --caida-real) se DETIENE el contenedor vectores: el endpoint
      responde 503 VECTORES_NO_DISPONIBLE y el resto del portal sigue; al
      levantarlo vuelve a responder.

Uso:
    venv\\Scripts\\python.exe backend/scripts/prueba_recomendacion.py
    venv\\Scripts\\python.exe backend/scripts/prueba_recomendacion.py --caida-real
"""

import argparse
import os
import subprocess
import sys
import time
from collections import Counter

import requests

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(RAIZ, "backend"))

from sqlalchemy import create_engine, text  # noqa: E402

from app import vectores  # noqa: E402
from app.extensions import col_productos  # noqa: E402

API = os.getenv("API_PRUEBA", "http://127.0.0.1:8000")

# Categorías que se consideran "afines" para la recomendación: un mouse
# recomendado desde una laptop gamer es una buena sugerencia, no un error.
AFINES = [
    {"Laptops", "Monitores", "Mouse", "Teclados", "Tablets", "Mochilas"},
    {"Celulares", "Tablets", "Smartwatches", "Audífonos"},
    {"Playeras", "Sudaderas", "Jeans", "Pantalones", "Vestidos", "Gorras"},
    {"Tenis", "Zapatos"},
    {"Electrodomésticos de Cocina", "Utensilios de Cocina"},
    {"Pesas y Mancuernas", "Tapetes de Yoga", "Bicicletas", "Tenis", "Sudaderas", "Smartwatches"},
    {"Cuidado de la Piel", "Perfumes"},
]

CONSULTAS = [
    ("algo para andar en bici por la ciudad", "Bicicletas"),
    ("celular con buena cámara para fotos", "Celulares"),
    ("regalo para alguien que ama la música", "Audífonos"),
    ("quiero hacer yoga en casa", "Tapetes de Yoga"),
    ("algo para preparar el desayuno en la cocina", "Electrodomésticos de Cocina"),
    ("crema para la cara con piel seca", "Cuidado de la Piel"),
    ("reloj que mida mis pasos y el ritmo cardiaco", "Smartwatches"),
    ("fragancia elegante para una cena", "Perfumes"),
]

resultados = []


def verificar(descripcion, condicion, detalle=""):
    resultados.append(bool(condicion))
    print(f"   [{'OK  ' if condicion else 'FALLA'}] {descripcion}" + (f"  ({detalle})" if detalle else ""))


def afin(cat_a, cat_b):
    return cat_a == cat_b or any(cat_a in g and cat_b in g for g in AFINES)


def get(ruta, **params):
    return requests.get(f"{API}{ruta}", params=params, timeout=60)


def r1_cobertura():
    print("\n[R1] Cobertura de embeddings")
    e = get("/api/vectores/estado").json()
    print(f"   catálogo={e['productos_catalogo']}  embeddings={e['total']}  modelo={e['modelos']}")
    verificar("un embedding por cada producto del catálogo", e["total"] == e["productos_catalogo"])
    verificar("todos calculados con un solo modelo", len(e["modelos"]) == 1)


def r2_relacionados():
    print("\n[R2] Productos relacionados (uno por categoría)")
    muestras = list(col_productos.aggregate([
        {"$match": {"activo": True}},
        {"$group": {"_id": "$categoria.nombre", "pid": {"$first": "$_id"}, "nombre": {"$first": "$nombre"}}},
        {"$sort": {"_id": 1}},
    ]))
    total = afines = mismas = 0
    tiempos = []
    a_si_mismo = []
    for m in muestras:
        inicio = time.perf_counter()
        r = get(f"/api/productos/{m['pid']}/relacionados", limite=6)
        tiempos.append((time.perf_counter() - inicio) * 1000)
        items = r.json()["items"]
        cats = [i["categoria"]["nombre"] for i in items]
        total += len(items)
        mismas += sum(c == m["_id"] for c in cats)
        afines += sum(afin(m["_id"], c) for c in cats)
        if m["pid"] in [i["_id"] for i in items]:
            a_si_mismo.append(m["pid"])
        print(f"   {m['_id'][:22]:<22} {m['nombre'][:34]:<34} -> "
              + ", ".join(f"{i['nombre'][:22]} ({i['similitud']:.2f})" for i in items[:3]))
    verificar("ningún producto se recomienda a sí mismo", not a_si_mismo, ", ".join(a_si_mismo))
    verificar("todas las categorías reciben 6 recomendaciones", total == 6 * len(muestras), f"{total} de {6 * len(muestras)}")
    verificar("≥ 70 % de las recomendaciones son de la misma categoría", mismas / total >= 0.7,
              f"{100 * mismas / total:.0f} %")
    verificar("≥ 90 % son de la misma categoría o de una afín", afines / total >= 0.9, f"{100 * afines / total:.0f} %")
    tiempos.sort()
    print(f"   latencia HTTP de /relacionados: mediana {tiempos[len(tiempos) // 2]:.0f} ms, máx {tiempos[-1]:.0f} ms")

    print("\n   Diversificación (PROD-0005, laptop con muchas variantes casi iguales):")
    con = get("/api/productos/PROD-0005/relacionados", limite=6).json()["items"]
    sin = get("/api/productos/PROD-0005/relacionados", limite=6, diversificar=0).json()["items"]

    def modelos_distintos(items):
        return len({" ".join(i["nombre"].split()[:3]) for i in items})

    print("     sin diversificar: " + " | ".join(i["nombre"][:30] for i in sin))
    print("     diversificado   : " + " | ".join(i["nombre"][:30] for i in con))
    verificar("diversificar aumenta la cantidad de modelos distintos recomendados",
              modelos_distintos(con) > modelos_distintos(sin),
              f"{modelos_distintos(sin)} -> {modelos_distintos(con)} modelos distintos")


def r3_busqueda_semantica():
    print("\n[R3] Búsqueda semántica vs. buscador léxico (Elasticsearch)")
    aciertos = 0
    for consulta, esperada in CONSULTAS:
        items = get("/api/busqueda/semantica", q=consulta, limite=5).json()["items"]
        cats = Counter(i["categoria"]["nombre"] for i in items)
        acierto = cats.get(esperada, 0) >= 3
        aciertos += acierto
        es = get("/api/busqueda", q=consulta, por_pagina=5)
        es_items = es.json().get("items", []) if es.ok else []
        es_cats = Counter((i.get("categoria") or {}).get("nombre") for i in es_items)
        print(f"   «{consulta}»  esperado: {esperada}")
        print(f"      semántica : {dict(cats)}  -> {items[0]['nombre'][:40] if items else '-'}")
        print(f"      léxica(ES): {dict(es_cats) if es_items else 'sin resultados'}"
              + (f"  -> {es_items[0]['nombre'][:40]}" if es_items else ""))
        print(f"      {'ACIERTO' if acierto else 'FALLO  '}: {cats.get(esperada, 0)}/5 resultados en {esperada}")
    verificar("tasa de acierto de la búsqueda semántica ≥ 75 %", aciertos / len(CONSULTAS) >= 0.75,
              f"{aciertos}/{len(CONSULTAS)} consultas")


def r4_indice():
    print("\n[R4] Plan de ejecución en pgvector")
    consulta = """
        EXPLAIN (ANALYZE, COSTS OFF) SELECT producto_id FROM producto_embedding
        ORDER BY embedding <=> (SELECT embedding FROM producto_embedding WHERE producto_id = 'PROD-0001')
        LIMIT 10
    """
    planes = {}
    for nombre, forzar in (("plan elegido por PostgreSQL", False), ("forzando el índice HNSW", True)):
        with vectores.engine.begin() as con:
            if forzar:
                con.execute(text("SET LOCAL enable_seqscan = off"))
            planes[nombre] = [r[0] for r in con.execute(text(consulta))]
        tiempo = next((l for l in planes[nombre] if l.startswith("Execution Time")), "")
        recorrido = next((l.strip().lstrip("-> ") for l in planes[nombre]
                          if "Scan" in l and "pkey" not in l), "")
        print(f"   {nombre:<30}: {recorrido[:60]:<60} {tiempo}")
    verificar("el índice HNSW existe y PostgreSQL puede usarlo",
              any("idx_producto_embedding_hnsw" in l for l in planes["forzando el índice HNSW"]))
    print("   Con ~1000 vectores el recorrido exacto (100 % de recall) tarda pocos ms y el planificador lo")
    print("   prefiere; el índice HNSW toma el relevo solo a medida que el catálogo crece (ver ADR-008).")


def r5_sincronizacion():
    print("\n[R5] Recalcular el embedding al editar un producto (hash del texto)")
    doc = col_productos.find_one({"_id": "PROD-0003"})
    def leer():
        with vectores.engine.connect() as con:
            return con.execute(text(
                "SELECT texto_hash, embedding::text AS e FROM producto_embedding WHERE producto_id = 'PROD-0003'"
            )).first()
    antes = leer()
    sin_cambio = vectores.guardar_embedding_producto(doc)
    verificar("guardar sin cambios no recalcula", sin_cambio == {"calculados": 0, "sin_cambios": 1}, str(sin_cambio))
    editado = dict(doc, descripcion="Chumpa impermeable para lluvia con capucha")
    r = vectores.guardar_embedding_producto(editado)
    despues = leer()
    verificar("cambiar la descripción recalcula ese embedding", r["calculados"] == 1 and despues.e != antes.e,
              f"hash {antes.texto_hash[:8]}… -> {despues.texto_hash[:8]}…")
    vectores.guardar_embedding_producto(doc)
    verificar("deshacer el cambio vuelve al embedding original", leer().texto_hash == antes.texto_hash)


def r6_permisos():
    print("\n[R6] Permisos en el componente vectorial (roles de PostgreSQL)")
    base = "postgresql+psycopg2://{}@localhost:5433/tiendaya_vectores"
    casos = [
        ("vectores_app:vectores_app_2026", "DROP TABLE producto_embedding", "vectores_app no puede borrar la tabla"),
        ("vectores_app:vectores_app_2026", "CREATE TABLE intrusa (x int)", "vectores_app no puede crear tablas"),
        ("vectores_lector:vectores_lector_2026",
         "UPDATE producto_embedding SET activo = false", "vectores_lector no puede modificar filas"),
    ]
    for cred, sql, descripcion in casos:
        try:
            with create_engine(base.format(cred)).begin() as con:
                con.execute(text(sql))
            verificar(descripcion, False, "la operación se ejecutó")
        except Exception as e:
            verificar(descripcion, "permission denied" in str(e) or "must be owner" in str(e),
                      str(e.orig).strip().splitlines()[0] if hasattr(e, "orig") else str(e)[:80])
    with create_engine(base.format("vectores_lector:vectores_lector_2026")).connect() as con:
        n = con.execute(text("SELECT count(*) FROM producto_embedding")).scalar()
    verificar("vectores_lector sí puede leer", n > 0, f"{n} filas")


def r7_caida_real():
    print("\n[R7] Caída real del componente vectorial")
    subprocess.run(["docker", "compose", "stop", "vectores"], cwd=RAIZ, check=True, capture_output=True)
    try:
        r = get("/api/productos/PROD-0001/relacionados")
        verificar("relacionados responde 503 VECTORES_NO_DISPONIBLE",
                  r.status_code == 503 and r.json().get("codigo") == "VECTORES_NO_DISPONIBLE", str(r.status_code))
        verificar("el detalle del producto sigue funcionando", get("/api/productos/PROD-0001").ok)
        verificar("el buscador (Elasticsearch) sigue funcionando", get("/api/busqueda", q="laptop").ok)
    finally:
        subprocess.run(["docker", "compose", "start", "vectores"], cwd=RAIZ, check=True, capture_output=True)
        # Las conexiones que este script tenía abiertas murieron con el contenedor.
        vectores.engine.dispose()
    for _ in range(30):
        r = get("/api/productos/PROD-0001/relacionados")
        if r.ok:
            break
        time.sleep(1)
    verificar("al volver a levantarlo, las recomendaciones vuelven solas", r.ok)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--caida-real", action="store_true", help="detiene y vuelve a levantar el contenedor vectores")
    args = parser.parse_args()
    print("=" * 100)
    print("PRUEBA DE RECOMENDACIÓN Y BÚSQUEDA SEMÁNTICA (pgvector)")
    print("=" * 100)
    r1_cobertura()
    r2_relacionados()
    r3_busqueda_semantica()
    r4_indice()
    r5_sincronizacion()
    r6_permisos()
    if args.caida_real:
        r7_caida_real()
    total, ok = len(resultados), sum(resultados)
    print("\n" + "=" * 100)
    print(f"RESUMEN: {ok}/{total} verificaciones correctas")
    print(f"RESULTADO: {'PASS' if ok == total else 'FAIL'}")
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    main()
