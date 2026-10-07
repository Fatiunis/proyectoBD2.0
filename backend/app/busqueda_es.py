"""Acceso a Elasticsearch para el buscador del catálogo (Entrega 3).

Lo usan el blueprint de búsqueda, el catálogo (indexa al guardar un producto),
el relevo de eventos de sincronización (stock tras un checkout) y el script de
indexación completa (database/migrations/indexar_productos_elasticsearch.py).

Fuente de verdad: MongoDB. El índice es una proyección de solo lectura de la
colección "productos", pensada para buscar: si se pierde, se reconstruye
entero con el script. Nunca se escribe en Elasticsearch algo que no esté ya en
Mongo (o, para el stock, en el inventario de PostgreSQL).

Definición del índice (mapping y analizadores): database/elasticsearch/productos_indice.json.
El buscador consulta siempre el ALIAS (config.ES_ALIAS_PRODUCTOS), nunca un
índice concreto, para poder reindexar sin cortar el servicio.
"""

import json
import os

from .config import ES_ALIAS_PRODUCTOS
from .extensions import es_client

RUTA_DEFINICION_INDICE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "database", "elasticsearch", "productos_indice.json"
)

POR_PAGINA_DEFECTO = 24
POR_PAGINA_MAXIMO = 100
MAX_AUTOCOMPLETADO = 8

# index.max_result_window de Elasticsearch (10000 por defecto): una búsqueda
# con from + size mayor se rechaza con 400. Las páginas que caen más allá de
# esa ventana se responden como cualquier página posterior a la última
# (items vacíos), sin pedirle hits al motor.
MAX_VENTANA_RESULTADOS = 10000

# Rangos de precio (en quetzales) de la faceta de precio. Cada rango se puede
# elegir como filtro con precio_min / precio_max.
RANGOS_PRECIO = [
    {"key": "Menos de Q100", "to": 100},
    {"key": "Q100 a Q500", "from": 100, "to": 500},
    {"key": "Q500 a Q1,000", "from": 500, "to": 1000},
    {"key": "Q1,000 a Q5,000", "from": 1000, "to": 5000},
    {"key": "Más de Q5,000", "from": 5000},
]

ORDENES = {
    "relevancia": ["_score", {"nombre.orden": "asc"}],
    "precio_asc": [{"precio_base": "asc"}, "_score"],
    "precio_desc": [{"precio_base": "desc"}, "_score"],
}


def cargar_definicion_indice():
    with open(RUTA_DEFINICION_INDICE, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- documentos


def _portada(imagenes):
    if not isinstance(imagenes, list) or not imagenes:
        return None
    portada = next((i for i in imagenes if isinstance(i, dict) and i.get("es_portada")), imagenes[0])
    return portada.get("url") if isinstance(portada, dict) else None


def _atributos_planos(atributos):
    """"flattened" solo acepta valores escalares u objetos: las listas de
    objetos no aplican aquí, así que todo se pasa a texto (las listas simples,
    como "puertos", quedan como lista de strings)."""
    if not isinstance(atributos, dict):
        return {}
    planos = {}
    for clave, valor in atributos.items():
        if valor is None:
            continue
        if isinstance(valor, list):
            planos[clave] = [str(v) for v in valor if v is not None]
        elif isinstance(valor, dict):
            planos[clave] = json.dumps(valor, ensure_ascii=False)
        else:
            planos[clave] = str(valor)
    return planos


def documento_es(doc):
    """Documento de Mongo -> documento del índice. Solo copia los campos que
    el mapping declara (dynamic: strict rechazaría cualquier otro)."""
    atributos = doc.get("atributos") or {}
    marca = atributos.get("marca") if isinstance(atributos, dict) else None
    categoria = doc.get("categoria") or {}
    vendedor = doc.get("vendedor") or {}
    ultima = doc.get("ultima_actualizacion")
    return {
        "producto_id": str(doc["_id"]),
        "id_sql_origen": doc.get("id_sql_origen"),
        "sku": doc.get("sku"),
        "nombre": doc.get("nombre") or "",
        "descripcion": doc.get("descripcion") or "",
        "categoria": {
            "id_categoria": categoria.get("id_categoria"),
            "nombre": categoria.get("nombre"),
        },
        "vendedor": {
            "id_vendedor": vendedor.get("id_vendedor"),
            "nombre_comercial": vendedor.get("nombre_comercial"),
        },
        "marca": str(marca) if marca not in (None, "") else None,
        "atributos": _atributos_planos(atributos),
        "precio_base": doc.get("precio_base"),
        "stock_disponible": doc.get("stock_disponible"),
        "activo": doc.get("activo", True),
        "imagen_portada": _portada(doc.get("imagenes")),
        "ultima_actualizacion": ultima.isoformat() if hasattr(ultima, "isoformat") else ultima,
    }


def indexar_producto(doc, refresh=False):
    """Indexa (o reemplaza) un producto. El _id del documento en Elasticsearch
    es el mismo _id de Mongo, así que repetir la operación es idempotente."""
    es_client.index(
        index=ES_ALIAS_PRODUCTOS,
        id=str(doc["_id"]),
        document=documento_es(doc),
        refresh="wait_for" if refresh else False,
    )


def actualizar_stock(id_sql_origen, stock):
    """Fija (no resta) el stock de un producto, buscándolo por id_sql_origen.
    Asignar un valor absoluto leído de PostgreSQL hace que reintentar sea
    idempotente. Devuelve cuántos documentos se actualizaron."""
    r = es_client.update_by_query(
        index=ES_ALIAS_PRODUCTOS,
        query={"term": {"id_sql_origen": id_sql_origen}},
        script={"source": "ctx._source.stock_disponible = params.stock", "params": {"stock": stock}},
        refresh=True,
        conflicts="proceed",
    )
    return r.get("updated", 0)


# ---------------------------------------------------------------- consultas


def _consulta_texto(q):
    """Relevancia combinada (bool.should, gana el documento que más señales junta):
      - multi_match con fuzziness AUTO: tolera errores de tipeo ("laptp",
        "audifnos") sobre nombre, descripción y categoría, con sinónimos y
        raíces en español gracias a es_texto_busqueda;
      - categoría: si lo buscado nombra un tipo de producto, sus productos
        van primero (ver el comentario en la cláusula);
      - match_phrase sobre el nombre (solo con 2+ palabras): premia la frase
        exacta. Con una sola palabra equivaldría a volver a contar la misma
        coincidencia del multi_match;
      - nombre.autocompletado, con poco peso: encuentra palabras a medio
        escribir ("samsu") sin opacar a las coincidencias completas;
      - sku exacto, con el mayor peso.
    """
    varias_palabras = len(q.split()) > 1
    return {
        "bool": {
            "should": [
                {
                    "multi_match": {
                        "query": q,
                        "fields": ["nombre^3", "categoria.nombre.texto^2", "marca.texto^2", "descripcion"],
                        "type": "best_fields",
                        "tie_breaker": 0.3,
                        "fuzziness": "AUTO",
                        "prefix_length": 1,
                        "minimum_should_match": "75%",
                    }
                },
                # Si lo buscado nombra un tipo de producto ("celular", "laptops"),
                # los productos de esa categoría van primero. Puntaje fijo
                # (constant_score): como el nombre de la categoría se repite en
                # todos sus productos, su IDF es bajo y, sin esto, una tablet
                # "Wi-Fi + Celular" le ganaría a un celular de verdad.
                {
                    "constant_score": {
                        "filter": {
                            "match": {
                                "categoria.nombre.texto": {"query": q, "fuzziness": "AUTO", "prefix_length": 1}
                            }
                        },
                        "boost": 25,
                    }
                },
                *([{"match_phrase": {"nombre": {"query": q, "boost": 4}}}] if varias_palabras else []),
                {"match": {"nombre.autocompletado": {"query": q, "operator": "and", "boost": 0.5}}},
                {"term": {"sku": {"value": q, "boost": 10}}},
            ],
            "minimum_should_match": 1,
        }
    }


def _filtros_faceta(params):
    """Un filtro por faceta elegida. Se guardan por separado para poder calcular
    cada faceta "sin su propio filtro" (facetas disyuntivas: elegir una marca no
    hace desaparecer las demás marcas de la lista)."""
    filtros = {}
    if params.get("categoria_id") is not None:
        filtros["categoria"] = {"term": {"categoria.id_categoria": params["categoria_id"]}}
    if params.get("marca"):
        filtros["marca"] = {"term": {"marca": params["marca"]}}
    if params.get("vendedor_id") is not None:
        filtros["tienda"] = {"term": {"vendedor.id_vendedor": params["vendedor_id"]}}
    rango = {}
    if params.get("precio_min") is not None:
        rango["gte"] = params["precio_min"]
    if params.get("precio_max") is not None:
        rango["lt"] = params["precio_max"]
    if rango:
        filtros["precio"] = {"range": {"precio_base": rango}}
    return filtros


def _filtro_sin(filtros, excluida):
    clausulas = [f for nombre, f in filtros.items() if nombre != excluida]
    return {"bool": {"filter": clausulas}} if clausulas else {"match_all": {}}


def buscar(params):
    """params: q, categoria_id, marca, vendedor_id, precio_min, precio_max,
    orden, pagina, por_pagina (ya validados por el blueprint)."""
    q = params["q"]
    filtros = _filtros_faceta(params)
    pagina = params["pagina"]
    por_pagina = params["por_pagina"]
    desde = (pagina - 1) * por_pagina
    # Fuera de la ventana de resultados: misma consulta con size 0, así se
    # devuelven igual el total, las facetas y la sugerencia reales. La última
    # página alcanzable se recorta para no pasarse de la ventana.
    fuera_de_ventana = desde >= MAX_VENTANA_RESULTADOS
    tamano = 0 if fuera_de_ventana else min(por_pagina, MAX_VENTANA_RESULTADOS - desde)

    cuerpo = {
        # La consulta de texto y "activo" acotan TODO (resultados y facetas);
        # los filtros de faceta van en post_filter para que no recorten las
        # agregaciones, que aplican cada una los filtros de las otras facetas.
        "query": {"bool": {"must": [_consulta_texto(q)], "filter": [{"term": {"activo": True}}]}},
        "post_filter": {"bool": {"filter": list(filtros.values())}},
        "sort": ORDENES[params["orden"]],
        "from": 0 if fuera_de_ventana else desde,
        "size": tamano,
        "track_total_hits": True,
        "aggs": {
            "categorias": {
                "filter": _filtro_sin(filtros, "categoria"),
                "aggs": {
                    "valores": {
                        "terms": {"field": "categoria.id_categoria", "size": 30},
                        "aggs": {"nombre": {"terms": {"field": "categoria.nombre", "size": 1}}},
                    }
                },
            },
            "marcas": {
                "filter": _filtro_sin(filtros, "marca"),
                "aggs": {"valores": {"terms": {"field": "marca", "size": 15}}},
            },
            "tiendas": {
                "filter": _filtro_sin(filtros, "tienda"),
                "aggs": {
                    "valores": {
                        "terms": {"field": "vendedor.id_vendedor", "size": 15},
                        "aggs": {"nombre": {"terms": {"field": "vendedor.nombre_comercial", "size": 1}}},
                    }
                },
            },
            "precios": {
                "filter": _filtro_sin(filtros, "precio"),
                "aggs": {"valores": {"range": {"field": "precio_base", "ranges": RANGOS_PRECIO}}},
            },
        },
        "suggest": {
            "correccion": {
                "text": q,
                "phrase": {
                    "field": "nombre.sugerencia",
                    "size": 1,
                    "max_errors": 2,
                    "direct_generator": [
                        {"field": "nombre.sugerencia", "suggest_mode": "missing", "min_word_length": 3}
                    ],
                },
            }
        },
    }

    r = es_client.search(index=ES_ALIAS_PRODUCTOS, **cuerpo)

    items = []
    for hit in r["hits"]["hits"]:
        s = hit["_source"]
        items.append({
            "_id": s["producto_id"],
            "sku": s.get("sku"),
            "nombre": s.get("nombre"),
            "precio_base": s.get("precio_base"),
            "categoria": s.get("categoria"),
            "vendedor": s.get("vendedor"),
            "stock_disponible": s.get("stock_disponible"),
            "imagenes": [{"url": s["imagen_portada"], "es_portada": True}] if s.get("imagen_portada") else [],
            "relevancia": hit.get("_score"),
        })

    total = r["hits"]["total"]["value"]
    aggs = r["aggregations"]

    def _con_nombre(buckets, clave_id):
        return [
            {
                clave_id: b["key"],
                "nombre": (b["nombre"]["buckets"][0]["key"] if b["nombre"]["buckets"] else str(b["key"])),
                "cantidad": b["doc_count"],
            }
            for b in buckets
        ]

    facetas = {
        "categorias": _con_nombre(aggs["categorias"]["valores"]["buckets"], "id_categoria"),
        "marcas": [{"marca": b["key"], "cantidad": b["doc_count"]} for b in aggs["marcas"]["valores"]["buckets"]],
        "tiendas": _con_nombre(aggs["tiendas"]["valores"]["buckets"], "id_vendedor"),
        "precios": [
            {"rango": b["key"], "precio_min": b.get("from"), "precio_max": b.get("to"), "cantidad": b["doc_count"]}
            for b in aggs["precios"]["valores"]["buckets"]
        ],
    }

    # "¿Quisiste decir...?": solo si el corrector propone algo distinto y la
    # búsqueda no fue un SKU exacto (un SKU no es una palabra mal escrita).
    sugerencia = None
    opciones = r.get("suggest", {}).get("correccion", [{}])[0].get("options", [])
    es_sku_exacto = any((i.get("sku") or "").lower() == q.strip().lower() for i in items)
    if opciones and not es_sku_exacto and opciones[0]["text"].strip().lower() != q.strip().lower():
        sugerencia = opciones[0]["text"]

    return {
        "items": items,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        # Solo las páginas alcanzables dentro de la ventana de resultados.
        "total_paginas": (min(total, MAX_VENTANA_RESULTADOS) + por_pagina - 1) // por_pagina
        if total else 0,
        "facetas": facetas,
        "sugerencia": sugerencia,
        "motor": "elasticsearch",
    }


def autocompletar(q):
    """Sugerencias mientras se escribe: prefijos de palabra (edge n-grams del
    campo nombre.autocompletado) con fuzziness para tolerar un error de tipeo."""
    r = es_client.search(
        index=ES_ALIAS_PRODUCTOS,
        query={
            "bool": {
                "must": [
                    {
                        "match": {
                            "nombre.autocompletado": {
                                "query": q,
                                "operator": "and",
                                "fuzziness": "AUTO",
                                "prefix_length": 1,
                            }
                        }
                    }
                ],
                "should": [{"match_phrase_prefix": {"nombre": {"query": q, "boost": 3}}}],
                "filter": [{"term": {"activo": True}}],
            }
        },
        source=["producto_id", "nombre", "categoria.nombre", "precio_base", "imagen_portada"],
        size=MAX_AUTOCOMPLETADO,
    )
    return [
        {
            "_id": h["_source"]["producto_id"],
            "nombre": h["_source"].get("nombre"),
            "categoria": (h["_source"].get("categoria") or {}).get("nombre"),
            "precio_base": h["_source"].get("precio_base"),
            "imagen_url": h["_source"].get("imagen_portada"),
        }
        for h in r["hits"]["hits"]
    ]
