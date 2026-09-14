import os

import redis
from flask import Blueprint, request, jsonify

from ..extensions import redis_client

bp = Blueprint("ofertas", __name__)

# ============================================================================
# MÓDULO DE OFERTAS DE INVENTARIO LIMITADO / FLASH SALE (REDIS - ENTREGA 2)
# ============================================================================
# Una oferta reserva un cupo limitado de unidades de un producto en Redis,
# independiente del stock real en Postgres/Mongo. Dos keys por oferta:
#   - oferta:{producto_id}:stock   -> contador que SÍ se decrementa (vía el
#     script Lua) en cada reserva exitosa.
#   - oferta:{producto_id}:limite  -> el límite original, fijo, para poder
#     mostrar "quedan X de Y" en el frontend. Nunca se decrementa.
#
# El endpoint de reserva NO hace check-then-act en Python: ejecuta un único
# script Lua (reservar_oferta.lua) vía EVALSHA, que Redis corre de forma
# atómica en su hilo único. Eso es lo que garantiza "no sobreventa" bajo
# concurrencia, sin locks de aplicación ni WATCH/MULTI.
#
# Nota de arquitectura: esta oferta vive enteramente en Redis y es
# independiente de sp_procesar_checkout (Postgres) y del catálogo de Mongo.
# No descuenta el stock "real" de ningún lado; es un cupo aparte pensado para
# la mecánica de flash sale de la Entrega 2.

_RUTA_SCRIPT_LUA = os.path.join(os.path.dirname(__file__), "..", "lua", "reservar_oferta.lua")
with open(_RUTA_SCRIPT_LUA, "r", encoding="utf-8") as _f:
    _CODIGO_SCRIPT_RESERVAR = _f.read()

# Se carga una sola vez al importar el módulo. Si Redis pierde la caché de
# scripts (p.ej. reinicio, FLUSHALL, o simplemente porque este proceso lo
# cargó y otro la limpió), _ejecutar_reserva lo recarga y reintenta.
_sha_script_reservar = redis_client.script_load(_CODIGO_SCRIPT_RESERVAR)

ROLES_VALIDOS = ("vendedor", "administrador")


def _clave_stock(producto_id):
    return f"oferta:{producto_id}:stock"


def _clave_limite(producto_id):
    return f"oferta:{producto_id}:limite"


def _es_entero_positivo(valor):
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def _ejecutar_reserva(clave_stock, cantidad):
    global _sha_script_reservar
    try:
        return redis_client.evalsha(_sha_script_reservar, 1, clave_stock, cantidad)
    except redis.exceptions.NoScriptError:
        _sha_script_reservar = redis_client.script_load(_CODIGO_SCRIPT_RESERVAR)
        return redis_client.evalsha(_sha_script_reservar, 1, clave_stock, cantidad)


@bp.route("/api/ofertas", methods=["POST"])
def crear_oferta():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "El cuerpo de la petición debe ser JSON válido"}), 400

    producto_id = data.get("producto_id")
    if not isinstance(producto_id, str) or not producto_id.strip():
        return jsonify({"error": "producto_id debe ser un string no vacío"}), 400

    cantidad_limite = data.get("cantidad_limite")
    if not _es_entero_positivo(cantidad_limite):
        return jsonify({"error": "cantidad_limite debe ser un entero positivo"}), 400

    rol_solicitante = data.get("rol_solicitante")
    if rol_solicitante not in ROLES_VALIDOS:
        return jsonify({"error": "rol_solicitante debe ser 'vendedor' o 'administrador'"}), 403

    clave_stock = _clave_stock(producto_id)
    clave_limite = _clave_limite(producto_id)

    try:
        creada = redis_client.set(clave_stock, cantidad_limite, nx=True)
        if not creada:
            return jsonify({"error": "Ya existe una oferta activa para este producto"}), 409

        redis_client.set(clave_limite, cantidad_limite)

        return jsonify({
            "mensaje": "Oferta creada",
            "producto_id": producto_id,
            "cantidad_limite": cantidad_limite,
        }), 201
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al crear la oferta: {str(e)}"}), 500


@bp.route("/api/ofertas/<producto_id>", methods=["GET"])
def obtener_oferta(producto_id):
    clave_stock = _clave_stock(producto_id)
    clave_limite = _clave_limite(producto_id)

    try:
        stock_raw, limite_raw = redis_client.mget(clave_stock, clave_limite)
        if stock_raw is None:
            return jsonify({"error": "No hay oferta activa para este producto"}), 404

        return jsonify({
            "producto_id": producto_id,
            "stock_restante": int(stock_raw),
            "cantidad_limite": int(limite_raw) if limite_raw is not None else None,
        }), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al consultar la oferta: {str(e)}"}), 500


@bp.route("/api/ofertas/<producto_id>/reservar", methods=["POST"])
def reservar_oferta(producto_id):
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "El cuerpo de la petición debe ser JSON válido"}), 400

    id_usuario = data.get("id_usuario")
    if not isinstance(id_usuario, int) or isinstance(id_usuario, bool):
        return jsonify({"error": "id_usuario debe ser un entero"}), 400

    cantidad = data.get("cantidad")
    if not _es_entero_positivo(cantidad):
        return jsonify({"error": "cantidad debe ser un entero positivo"}), 400

    clave_stock = _clave_stock(producto_id)

    try:
        resultado = _ejecutar_reserva(clave_stock, cantidad)

        if resultado == -1:
            return jsonify({"error": "No hay oferta activa para este producto"}), 404
        if resultado == -2:
            return jsonify({"error": "Stock insuficiente en la oferta"}), 409

        return jsonify({"mensaje": "Reserva confirmada", "stock_restante": resultado}), 201
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al reservar la oferta: {str(e)}"}), 500


@bp.route("/api/ofertas/<producto_id>", methods=["DELETE"])
def finalizar_oferta(producto_id):
    data = request.get_json(silent=True) or {}
    rol_solicitante = data.get("rol_solicitante") or request.args.get("rol_solicitante")

    if rol_solicitante not in ROLES_VALIDOS:
        return jsonify({"error": "rol_solicitante debe ser 'vendedor' o 'administrador'"}), 403

    try:
        redis_client.delete(_clave_stock(producto_id), _clave_limite(producto_id))
        return jsonify({"mensaje": "Oferta finalizada"}), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al finalizar la oferta: {str(e)}"}), 500
