from datetime import datetime

from flask import Blueprint, request, jsonify

from ..extensions import col_historial, col_productos

bp = Blueprint("historial", __name__)

LIMIT_DEFAULT = 50
LIMIT_MAXIMO = 200


@bp.route("/api/historial", methods=["GET"])
def listar_historial():
    # Feed de eventos (a diferencia de /api/historial/<producto_id>, que reconstruye
    # el estado de UN producto en una fecha exacta). vendedor_id requiere un $lookup
    # porque el historial no guarda el vendedor, solo producto_id.
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

    try:
        limit = int(request.args.get("limit", LIMIT_DEFAULT))
    except (TypeError, ValueError):
        limit = LIMIT_DEFAULT
    if limit <= 0 or limit > LIMIT_MAXIMO:
        limit = LIMIT_DEFAULT if limit <= 0 else LIMIT_MAXIMO

    pipeline = [
        {"$match": match_evento},
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

    if vendedor_id:
        try:
            vendedor_id_int = int(vendedor_id)
        except ValueError:
            return jsonify({"error": "vendedor_id debe ser numérico"}), 400
        pipeline.append({"$match": {"producto_info.vendedor.id_vendedor": vendedor_id_int}})

    pipeline.extend([
        {"$sort": {"fecha_evento": -1}},
        {"$limit": limit},
        {
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
        }
    ])

    eventos = list(col_historial.aggregate(pipeline))
    for e in eventos:
        e["fecha_evento"] = e["fecha_evento"].isoformat()

    return jsonify({"eventos": eventos})


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
