"""
Indexación completa del catálogo de MongoDB en Elasticsearch (Entrega 3).

Reproducible e idempotente: cada corrida construye un índice NUEVO y versionado
(productos_v<AAAAMMDDHHMMSS>) con la definición de
database/elasticsearch/productos_indice.json, lo llena con todos los productos
de la colección Mongo "productos", verifica que tenga la misma cantidad de
documentos y recién entonces mueve el alias "productos" (ES_ALIAS_PRODUCTOS)
al índice nuevo, en una sola operación atómica. Los índices anteriores se
borran al final.

Así el buscador (que siempre consulta el alias) nunca ve un índice vacío o a
medio llenar, y cambiar el mapping es tan simple como editar el JSON y volver
a correr este script.

Uso (con Elasticsearch levantado por docker compose):
    python database/migrations/indexar_productos_elasticsearch.py
    python database/migrations/indexar_productos_elasticsearch.py --conservar-anteriores
"""

import argparse
import os
import sys
from datetime import datetime

# Reutiliza la misma conversión documento Mongo -> documento del índice que usa
# el backend (backend/app/busqueda_es.py), para que no existan dos versiones.
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(RAIZ, "backend"))

from elasticsearch import helpers  # noqa: E402

from app.busqueda_es import cargar_definicion_indice, documento_es  # noqa: E402
from app.config import ES_ALIAS_PRODUCTOS  # noqa: E402
from app.extensions import col_productos, es_client  # noqa: E402


def acciones_bulk(nombre_indice):
    for doc in col_productos.find({}):
        yield {"_index": nombre_indice, "_id": str(doc["_id"]), "_source": documento_es(doc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--conservar-anteriores", action="store_true",
                        help="No borra los índices versionados anteriores (útil para comparar).")
    args = parser.parse_args()

    if not es_client.ping():
        sys.exit("Elasticsearch no responde. Levántalo con: docker compose up -d elasticsearch")

    if es_client.indices.exists(index=ES_ALIAS_PRODUCTOS) and not es_client.indices.exists_alias(name=ES_ALIAS_PRODUCTOS):
        sys.exit(f"Existe un índice llamado '{ES_ALIAS_PRODUCTOS}' que no es un alias. "
                 f"Bórralo (DELETE /{ES_ALIAS_PRODUCTOS}) y vuelve a correr el script.")

    nombre_nuevo = f"{ES_ALIAS_PRODUCTOS}_v{datetime.now().strftime('%Y%m%d%H%M%S')}"
    definicion = cargar_definicion_indice()

    print(f"[1/4] Creando índice {nombre_nuevo} con la definición de productos_indice.json...")
    es_client.indices.create(index=nombre_nuevo, settings=definicion["settings"], mappings=definicion["mappings"])

    print("[2/4] Indexando productos de MongoDB...")
    ok, errores = helpers.bulk(es_client.options(request_timeout=120), acciones_bulk(nombre_nuevo),
                               chunk_size=500, raise_on_error=False)
    if errores:
        for e in errores[:5]:
            print(f"       ERROR: {e}")
        es_client.indices.delete(index=nombre_nuevo)
        sys.exit(f"{len(errores)} documentos fallaron; se borró {nombre_nuevo} y el alias no se tocó.")
    es_client.indices.refresh(index=nombre_nuevo)

    total_mongo = col_productos.count_documents({})
    total_es = es_client.count(index=nombre_nuevo)["count"]
    print(f"[3/4] Verificación: MongoDB={total_mongo}  Elasticsearch={total_es}")
    if total_mongo != total_es:
        es_client.indices.delete(index=nombre_nuevo)
        sys.exit("Las cantidades no coinciden; se borró el índice nuevo y el alias no se tocó.")

    anteriores = []
    if es_client.indices.exists_alias(name=ES_ALIAS_PRODUCTOS):
        anteriores = list(es_client.indices.get_alias(name=ES_ALIAS_PRODUCTOS).keys())

    print(f"[4/4] Moviendo el alias '{ES_ALIAS_PRODUCTOS}' -> {nombre_nuevo} (antes: {anteriores or 'ninguno'})")
    acciones = [{"remove": {"index": i, "alias": ES_ALIAS_PRODUCTOS}} for i in anteriores]
    acciones.append({"add": {"index": nombre_nuevo, "alias": ES_ALIAS_PRODUCTOS}})
    es_client.indices.update_aliases(actions=acciones)

    if anteriores and not args.conservar_anteriores:
        es_client.indices.delete(index=",".join(anteriores))
        print(f"       Índices anteriores borrados: {', '.join(anteriores)}")

    print(f"Listo: {ok} productos indexados en {nombre_nuevo}.")


if __name__ == "__main__":
    main()
