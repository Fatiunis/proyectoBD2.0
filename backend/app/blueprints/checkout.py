import json

from flask import Blueprint, request, jsonify
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ..extensions import db

bp = Blueprint("checkout", __name__)

# La lógica transaccional (bloqueo pesimista con SELECT ... FOR UPDATE, cálculo
# del total, descuento de inventario y rollback automático ante cualquier
# excepción) vive intencionalmente en el stored procedure `sp_procesar_checkout`
# (ver database/postgres/ddl_tiendaya.sql). Este endpoint NO reimplementa esa
# lógica en Python/SQLAlchemy: solo invoca el procedimiento con `CALL` a través
# de la sesión de SQLAlchemy, en vez de psycopg2 directo.


@bp.route("/api/checkout", methods=["POST"])
def procesar_checkout():
    data = request.get_json() or {}
    id_comprador = data.get("id_comprador")
    id_direccion = data.get("id_direccion")
    metodo_pago = data.get("metodo_pago")
    referencia_pago = data.get("referencia_pago")
    items = data.get("items")

    if not all([id_comprador, id_direccion, metodo_pago, referencia_pago]) or not items:
        return jsonify({"error": "id_comprador, id_direccion, metodo_pago, referencia_pago e items son obligatorios"}), 400

    try:
        resultado = db.session.execute(
            text(
                "CALL sp_procesar_checkout("
                ":id_comprador, :id_direccion, :metodo_pago, :referencia_pago, "
                "CAST(:items AS JSONB), NULL, NULL)"
            ),
            {
                "id_comprador": id_comprador,
                "id_direccion": id_direccion,
                "metodo_pago": metodo_pago,
                "referencia_pago": referencia_pago,
                "items": json.dumps(items),
            },
        )
        id_pedido, mensaje = resultado.fetchone()
        db.session.commit()
        return jsonify({"mensaje": mensaje, "id_pedido": id_pedido}), 201
    except DBAPIError as e:
        db.session.rollback()
        diag = getattr(e.orig, "diag", None)
        mensaje_error = (diag.message_primary if diag else None) or str(e.orig).strip()
        return jsonify({"error": mensaje_error}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500
