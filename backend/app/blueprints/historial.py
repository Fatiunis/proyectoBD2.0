from datetime import datetime

from flask import Blueprint, request, jsonify

from ..extensions import col_historial, col_productos

bp = Blueprint("historial", __name__)

POR_PAGINA_DEFAULT = 20
POR_PAGINA_MAXIMO = 100
SALTO_MAXIMO = 2**63 - 1  # mayor entero que acepta $skip (int64)


def _entero_param(nombre, default):
    """Lee un parámetro entero de la query. None si no es numérico."""
    valor = request.args.get(nombre)
    if valor is None or valor.strip() == "":
        return default
    try:
        return int(valor)
    except ValueError:
        return None


@bp.route("/api/historial", methods=["GET"])
def listar_historial():
    # Feed paginado de eventos (a diferencia de /api/historial/<producto_id>, que
    # reconstruye el estado de UN producto en una fecha exacta). vendedor_id requiere
    # un $lookup porque el historial no guarda el vendedor, solo producto_id.
    producto_id = request.args.get("producto_id")
    fecha_desde = request.args.get("fecha_desde")
    fecha_hasta = request.args.get("fecha_hasta")
    vendedor_id = request.args.get("vendedor_id")

    match_evento = {}
    if producto_id:
        match_evento["producto_id"] = producto_id

    rango_fecha = {}
    if fecha_desde:
        try:
            rango_fecha["$gte"] = datetime.fromisoformat(fecha_desde.replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"error": "Formato de fecha_desde inválido. Usar ISO 8601"}), 400
    if fecha_hasta:
        try:
            rango_fecha["$lte"] = datetime.fromisoformat(fecha_hasta.replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"error": "Formato de fecha_hasta inválido. Usar ISO 8601"}), 400
    if rango_fecha:
        match_evento["fecha_evento"] = rango_fecha

    vendedor_id_int = None
    if vendedor_id:
        try:
            vendedor_id_int = int(vendedor_id)
        except ValueError:
            return jsonify({"error": "vendedor_id debe ser numérico"}), 400

    # Paginación con el mismo criterio que GET /api/productos: valores <= 0 se
    # ajustan a 1 y por_pagina se capa al máximo. "limit" es el parámetro viejo
    # (antes de paginar) y se acepta como alias de por_pagina.
    pagina = _entero_param("pagina", 1)
    if pagina is None:
        return jsonify({"error": "pagina debe ser numérico"}), 400
    nombre_por_pagina = "por_pagina" if request.args.get("por_pagina") is not None else "limit"
    por_pagina = _entero_param(nombre_por_pagina, POR_PAGINA_DEFAULT)
    if por_pagina is None:
        return jsonify({"error": f"{nombre_por_pagina} debe ser numérico"}), 400
    pagina = max(pagina, 1)
    por_pagina = min(max(por_pagina, 1), POR_PAGINA_MAXIMO)

    lookup_producto = [
        {
            "$lookup": {
                "from": col_productos.name,
                "localField": "producto_id",
                "foreignField": "_id",
                "as": "producto_info"
            }
        },
        {"$unwind": {"path": "$producto_info", "preserveNullAndEmptyArrays": True}},
    ]

    # El primer $match va al inicio para que use idx_historial_producto_fecha
    # (producto_id, fecha_evento) cuando hay producto_id. Sin vendedor_id, el
    # $lookup se hace solo sobre la página (no sobre todos los eventos).
    pipeline = [{"$match": match_evento}]
    if vendedor_id_int is not None:
        pipeline.extend(lookup_producto)
        pipeline.append({"$match": {"producto_info.vendedor.id_vendedor": vendedor_id_int}})

    # Desempate por _id para que la paginación sea estable con fechas repetidas.
    pipeline.append({"$sort": {"fecha_evento": -1, "_id": -1}})

    # $skip es un entero de 8 bytes en MongoDB: con páginas enormes el salto se
    # topa a SALTO_MAXIMO (sigue estando más allá de cualquier total real, así
    # que la página sale vacía con el total verdadero, igual que fuera de rango).
    rama_pagina = [
        {"$skip": min((pagina - 1) * por_pagina, SALTO_MAXIMO)},
        {"$limit": por_pagina},
    ]
    if vendedor_id_int is None:
        rama_pagina.extend(lookup_producto)
    rama_pagina.append({
        "$project": {
            "_id": 0,
            "producto_id": 1,
            "tipo_evento": 1,
            "fecha_evento": 1,
            "responsable": "$usuario_responsable.nombre",
            "nombre": "$estado_resultante.nombre",
            "precio_base": "$estado_resultante.precio_base",
            "activo": "$estado_resultante.activo",
            "sku": "$producto_info.sku"
        }
    })

    pipeline.append({
        "$facet": {
            "conteo": [{"$count": "total"}],
            "eventos": rama_pagina,
        }
    })

    resultado = next(col_historial.aggregate(pipeline), {"conteo": [], "eventos": []})
    total = resultado["conteo"][0]["total"] if resultado["conteo"] else 0
    eventos = resultado["eventos"]
    for e in eventos:
        e["fecha_evento"] = e["fecha_evento"].isoformat()

    return jsonify({
        "eventos": eventos,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total_paginas": (total + por_pagina - 1) // por_pagina,
    })


@bp.route("/api/historial/<producto_id>", methods=["GET"])
def reconstruir_historial(producto_id):
    fecha_corte = request.args.get("fecha_corte")
    if not fecha_corte:
        return jsonify({"error": "Parámetro fecha_corte requerido"}), 400

    try:
        dt_corte = datetime.fromisoformat(fecha_corte.replace("Z", "+00:00"))
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Usar ISO 8601"}), 400

    pipeline = [
        {"$match": {"producto_id": producto_id, "fecha_evento": {"$lte": dt_corte}}},
        {"$sort": {"fecha_evento": -1}},
        {"$limit": 1},
        {
            "$project": {
                "_id": 0,
                "producto_id": 1,
                "fecha_vigencia_evento": "$fecha_evento",
                "tipo_evento": 1,
                "responsable": "$usuario_responsable.nombre",
                "estado_en_esa_fecha": "$estado_resultante"
            }
        }
    ]

    res = list(col_historial.aggregate(pipeline))
    if not res:
        return jsonify({"error": "No existe estado registrado previo a la fecha especificada."}), 404

    res[0]["fecha_vigencia_evento"] = res[0]["fecha_vigencia_evento"].isoformat()
    return jsonify(res[0])
