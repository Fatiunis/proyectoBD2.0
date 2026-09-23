import json

import redis
from flask import Blueprint, request, jsonify

from ..config import CARRITO_TTL_SEGUNDOS
from ..extensions import redis_client

bp = Blueprint("carrito", __name__)

# ============================================================================
# MÓDULO DE CARRITO DE COMPRAS (REDIS - ENTREGA 2)
# ============================================================================
# El carrito vive en Redis como un hash "carrito:{id_usuario}": cada campo del
# hash es el id_producto (el _id de Mongo) y el valor es un string JSON con el
# resto del item (cantidad, precio, etc.). El TTL se renueva en cada lectura o
# escritura -- el carrito expira a los CARRITO_TTL_SEGUNDOS de INACTIVIDAD, no
# desde su creación.
#
# Redis es una dependencia nueva y menos estable que Postgres/Mongo en este
# entorno de desarrollo (puede no estar levantada), así que -a diferencia del
# resto del proyecto, que no valida conexión- acá sí se captura
# redis.exceptions.RedisError aparte para responder un 500 claro en vez de
# dejar que la excepción reviente sin manejar.


def _clave_carrito(id_usuario):
    return f"carrito:{id_usuario}"


def _es_entero_positivo(valor):
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


@bp.route("/api/carrito/<int:id_usuario>", methods=["GET"])
def get_carrito(id_usuario):
    clave = _clave_carrito(id_usuario)
    try:
        crudo = redis_client.hgetall(clave)
        redis_client.expire(clave, CARRITO_TTL_SEGUNDOS)

        items = []
        for id_producto, valor_json in crudo.items():
            item = json.loads(valor_json)
            item["id_producto"] = id_producto
            items.append(item)

        cantidad_total = sum(item["cantidad"] for item in items)
        total_pagar = sum(item["cantidad"] * item["precio_base"] for item in items)

        return jsonify({
            "items": items,
            "cantidad_total": cantidad_total,
            "total_pagar": total_pagar,
        })
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al leer el carrito: {str(e)}"}), 500


@bp.route("/api/carrito/<int:id_usuario>/items", methods=["POST"])
def agregar_item(id_usuario):
    clave = _clave_carrito(id_usuario)

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "El cuerpo de la petición debe ser JSON válido"}), 400

    campos_requeridos = [
        "id_producto", "id_sql_origen", "nombre", "precio_base",
        "id_categoria", "imagen_url", "stock_disponible",
    ]
    faltantes = [c for c in campos_requeridos if c not in data]
    if faltantes:
        return jsonify({"error": f"Faltan campos obligatorios: {', '.join(faltantes)}"}), 400

    id_producto = data.get("id_producto")
    if not isinstance(id_producto, str) or not id_producto.strip():
        return jsonify({"error": "id_producto debe ser un string no vacío"}), 400

    cantidad = data.get("cantidad", 1)
    if not _es_entero_positivo(cantidad):
        return jsonify({"error": "cantidad debe ser un entero positivo"}), 400

    stock_disponible = data.get("stock_disponible")
    if not isinstance(stock_disponible, int) or isinstance(stock_disponible, bool):
        return jsonify({"error": "stock_disponible debe ser un entero"}), 400

    try:
        raw_existente = redis_client.hget(clave, id_producto)
        if raw_existente is not None:
            # El producto ya está en el carrito: se suma la cantidad, clamped
            # contra el stock_disponible recibido en esta petición (igual que
            # agregar() en useCarrito.js). Los demás campos del item existente
            # no se tocan.
            item = json.loads(raw_existente)
            item["cantidad"] = min(item["cantidad"] + cantidad, stock_disponible)
        else:
            item = {
                "cantidad": min(max(cantidad, 1), stock_disponible),
                "id_sql_origen": data["id_sql_origen"],
                "nombre": data["nombre"],
                "precio_base": data["precio_base"],
                "id_categoria": data["id_categoria"],
                "imagen_url": data["imagen_url"],
                "stock_disponible": stock_disponible,
            }

        redis_client.hset(clave, id_producto, json.dumps(item))
        redis_client.expire(clave, CARRITO_TTL_SEGUNDOS)

        item_respuesta = dict(item)
        item_respuesta["id_producto"] = id_producto
        return jsonify({"mensaje": "Producto agregado al carrito", "item": item_respuesta}), 201
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al agregar el producto al carrito: {str(e)}"}), 500


@bp.route("/api/carrito/<int:id_usuario>/items/<id_producto>", methods=["PUT"])
def actualizar_item(id_usuario, id_producto):
    clave = _clave_carrito(id_usuario)

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "El cuerpo de la petición debe ser JSON válido"}), 400

    cantidad = data.get("cantidad")
    if not _es_entero_positivo(cantidad):
        return jsonify({"error": "cantidad debe ser un entero positivo"}), 400

    try:
        raw_existente = redis_client.hget(clave, id_producto)
        if raw_existente is None:
            return jsonify({"error": "El producto no está en el carrito"}), 404

        item = json.loads(raw_existente)
        stock_disponible = item.get("stock_disponible", cantidad)
        # Cantidad ABSOLUTA (no incremental), clamp entre 1 y el stock guardado.
        item["cantidad"] = max(1, min(cantidad, stock_disponible))

        redis_client.hset(clave, id_producto, json.dumps(item))
        redis_client.expire(clave, CARRITO_TTL_SEGUNDOS)

        item_respuesta = dict(item)
        item_respuesta["id_producto"] = id_producto
        return jsonify({"mensaje": "Cantidad actualizada", "item": item_respuesta}), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al actualizar el carrito: {str(e)}"}), 500


@bp.route("/api/carrito/<int:id_usuario>/items/<id_producto>", methods=["DELETE"])
def eliminar_item(id_usuario, id_producto):
    clave = _clave_carrito(id_usuario)
    try:
        redis_client.hdel(clave, id_producto)
        # Si el hash quedó vacío, Redis ya lo borró solo; EXPIRE sobre una key
        # inexistente simplemente no hace nada (no rompe nada).
        redis_client.expire(clave, CARRITO_TTL_SEGUNDOS)
        return jsonify({"mensaje": "Producto eliminado del carrito"}), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al eliminar el producto del carrito: {str(e)}"}), 500


@bp.route("/api/carrito/<int:id_usuario>", methods=["DELETE"])
def vaciar_carrito(id_usuario):
    clave = _clave_carrito(id_usuario)
    try:
        redis_client.delete(clave)
        return jsonify({"mensaje": "Carrito vaciado"}), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al vaciar el carrito: {str(e)}"}), 500
