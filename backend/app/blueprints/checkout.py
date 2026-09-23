import json
import uuid
from datetime import datetime

import redis
from flask import Blueprint, request, jsonify
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ..extensions import db, redis_client, ZONA_GUATEMALA
from .carrito import _clave_carrito

bp = Blueprint("checkout", __name__)

# La lógica transaccional (bloqueo pesimista con SELECT ... FOR UPDATE, cálculo
# del total, descuento de inventario y rollback automático ante cualquier
# excepción) vive intencionalmente en el stored procedure `sp_procesar_checkout`
# (ver database/postgres/ddl_tiendaya.sql). Este endpoint NO reimplementa esa
# lógica en Python/SQLAlchemy: solo invoca el procedimiento con `CALL` a través
# de la sesión de SQLAlchemy, en vez de psycopg2 directo.
#
# Fuente de verdad de los items: el carrito en Redis (carrito:{id_comprador}),
# NO lo que mande el navegador. Así un carrito que ya expiró por inactividad en
# Redis no se puede pagar con una copia vieja guardada en el cliente. Si el
# body trae "items", se ignoran a propósito.
#
# Orden y fallos parciales (Redis + Postgres):
#   1. Se lee el carrito de Redis. Si Redis falla acá -> 503 y no se toca
#      Postgres (no hay nada que deshacer).
#   2. Se llama al SP. Si falla -> rollback y el carrito queda intacto para
#      que el usuario pueda reintentar.
#   3. Tras el commit, se borra el carrito. Si ese DEL falla, el pedido YA está
#      confirmado en Postgres: no se reporta error al cliente, solo se deja una
#      advertencia (el carrito expirará solo por TTL).
# Carrera conocida: si el usuario modifica el carrito entre el HGETALL y el DEL,
# esa modificación se pierde con el DEL. Es aceptable para este flujo (el
# checkout es la última acción del usuario sobre ese carrito).


def _generar_referencia_pago():
    """Referencia de pago automática: TY-{YYYYMMDDHHMMSS}-{6 hex en mayúsculas}.

    Usa la hora de Guatemala. Mide 24 caracteres (cabe en
    pagos.referencia_transaccion VARCHAR(100), que es UNIQUE). Si por azar
    colisionara, el SP falla, se hace rollback y el cliente puede reintentar.
    """
    marca = datetime.now(ZONA_GUATEMALA).strftime("%Y%m%d%H%M%S")
    return f"TY-{marca}-{uuid.uuid4().hex[:6].upper()}"


@bp.route("/api/checkout", methods=["POST"])
def procesar_checkout():
    data = request.get_json(silent=True) or {}
    id_comprador = data.get("id_comprador")
    id_direccion = data.get("id_direccion")
    metodo_pago = data.get("metodo_pago")
    # La referencia de pago la genera SIEMPRE el backend; si el cliente manda
    # "referencia_pago" se ignora a propósito.

    if not all([id_comprador, id_direccion, metodo_pago]):
        return jsonify({"error": "id_comprador, id_direccion y metodo_pago son obligatorios"}), 400

    clave = _clave_carrito(id_comprador)

    try:
        crudo = redis_client.hgetall(clave)
    except redis.exceptions.RedisError:
        return jsonify({"error": "No se pudo leer el carrito (Redis no disponible)"}), 503

    if not crudo:
        return jsonify({
            "error": "Tu carrito expiró o está vacío. Vuelve a agregar los productos.",
            "codigo": "CARRITO_VACIO",
        }), 409

    items = []
    for id_producto, valor_json in crudo.items():
        try:
            item = json.loads(valor_json)
        except (TypeError, ValueError):
            return jsonify({"error": f"El item {id_producto} del carrito está corrupto"}), 400

        id_sql_origen = item.get("id_sql_origen")
        if id_sql_origen is None:
            return jsonify({
                "error": f"El producto {id_producto} no tiene id_sql_origen: no existe en el "
                         f"inventario transaccional (Postgres) y no se puede comprar. "
                         f"Quítalo del carrito para continuar."
            }), 400

        items.append({"id_producto": id_sql_origen, "cantidad": item.get("cantidad")})

    referencia_pago = _generar_referencia_pago()

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
    except DBAPIError as e:
        db.session.rollback()
        diag = getattr(e.orig, "diag", None)
        mensaje_error = (diag.message_primary if diag else None) or str(e.orig).strip()
        return jsonify({"error": mensaje_error}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500

    try:
        redis_client.delete(clave)
    except Exception as e:
        print(f"[checkout] ADVERTENCIA: pedido {id_pedido} confirmado, pero no se pudo borrar {clave} en Redis: {e}")

    return jsonify({"mensaje": mensaje, "id_pedido": id_pedido, "referencia_pago": referencia_pago}), 201
