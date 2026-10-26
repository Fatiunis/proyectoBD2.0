"""
Carga completa de embeddings del catálogo en el componente vectorial (entrega final).

Lee todos los productos de la colección Mongo "productos", arma el texto de
cada uno (nombre + categoría + descripción), lo convierte en un vector de 384
dimensiones con el modelo multilingüe de sentence-transformers y lo guarda en
la tabla producto_embedding de PostgreSQL + pgvector (contenedor "vectores").

Reproducible e idempotente: usa la misma lógica que el backend
(backend/app/vectores.py). Cada fila guarda el hash del texto y el modelo con
que se calculó; si ninguno cambió, el producto se salta. Así volver a correrlo
tras editar unos pocos productos solo recalcula esos. Con --forzar se
recalculan todos (p. ej. después de cambiar MODELO_EMBEDDINGS). Al final borra
los embeddings de productos que ya no existen en Mongo.

La primera vez descarga el modelo (~460 MB) a la caché de Hugging Face.

Uso (con el contenedor "vectores" levantado por docker compose):
    python database/migrations/generar_embeddings_productos.py
    python database/migrations/generar_embeddings_productos.py --forzar
"""

import argparse
import os
import sys
import time

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(RAIZ, "backend"))

from sqlalchemy import text  # noqa: E402

from app import vectores  # noqa: E402
from app.config import MODELO_EMBEDDINGS  # noqa: E402
from app.extensions import col_productos  # noqa: E402

TAMANO_LOTE = 256


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--forzar", action="store_true", help="recalcula todos los embeddings aunque no hayan cambiado")
    args = parser.parse_args()

    total = col_productos.count_documents({})
    print(f"Productos en MongoDB: {total}")
    print(f"Modelo: {MODELO_EMBEDDINGS}")
    inicio = time.time()
    vectores.modelo()
    print(f"Modelo cargado en {time.time() - inicio:.1f} s")

    calculados = sin_cambios = 0
    ids_mongo = []
    lote = []
    inicio = time.time()
    for doc in col_productos.find({}, {"nombre": 1, "descripcion": 1, "categoria": 1, "activo": 1}):
        ids_mongo.append(str(doc["_id"]))
        lote.append(doc)
        if len(lote) == TAMANO_LOTE:
            r = vectores.guardar_embeddings(lote, forzar=args.forzar)
            calculados += r["calculados"]
            sin_cambios += r["sin_cambios"]
            print(f"  {calculados + sin_cambios}/{total}...")
            lote = []
    if lote:
        r = vectores.guardar_embeddings(lote, forzar=args.forzar)
        calculados += r["calculados"]
        sin_cambios += r["sin_cambios"]

    with vectores.engine.begin() as con:
        huerfanos = con.execute(
            text("DELETE FROM producto_embedding WHERE NOT (producto_id = ANY(:ids))"), {"ids": ids_mongo}
        ).rowcount

    e = vectores.estado()
    print(f"\nListo en {time.time() - inicio:.1f} s: {calculados} calculados, {sin_cambios} sin cambios, "
          f"{huerfanos} huérfanos borrados.")
    print(f"pgvector: {e['total']} embeddings ({e['activos']} de productos activos), modelos {e['modelos']}")
    if e["total"] != total:
        print("ADVERTENCIA: la cantidad de embeddings no coincide con la de productos en MongoDB.")
        sys.exit(1)


if __name__ == "__main__":
    main()
