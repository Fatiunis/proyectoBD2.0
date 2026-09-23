import json

import redis
from flask import Blueprint, request, jsonify

from .. import ofertas_redis
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
#
# Líneas de oferta relámpago: POST /api/ofertas/<pid>/reservar agrega una
# línea aparte con el campo "oferta:{pid}" (una línea normal del mismo
# producto usa el campo "{pid}"; ambas pueden convivir). Esa línea depende de
# una reserva en oferta:{pid}:reservas que dura RESERVA_OFERTA_TTL_SEGUNDOS:
#   - GET: si la reserva venció, la línea se quita (atómicamente, en Lua) y su
#     nombre se informa en "ofertas_expiradas".
#   - PUT: la cantidad de una línea de oferta no se puede cambiar (400).
#   - DELETE de la línea o del carrito completo: libera la reserva en el acto.
# Cada ítem de la respuesta trae precio_unitario (precio de oferta o
# precio_base) para que el frontend sume con un solo campo.


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
        ofertas_expiradas = []
        for id_item, valor_json in crudo.items():
            item = json.loads(valor_json)
            item["id_item"] = id_item
            producto_oferta = ofertas_redis.producto_de_campo(id_item)

            if producto_oferta is None:
                item["id_producto"] = id_item
                item["es_oferta"] = False
                item["precio_unitario"] = item.get("precio_base")
                items.append(item)
                continue

            # Línea de oferta: la reserva en Redis es la fuente de verdad de
            # cantidad, precio y vencimiento. Si ya no existe, el script la
            # quita del carrito en la misma operación.
            reserva = ofertas_redis.estado_linea(producto_oferta, id_usuario, clave)
            if reserva is None:
                ofertas_expiradas.append(item.get("nombre") or producto_oferta)
                continue
            item["id_producto"] = producto_oferta
            item["es_oferta"] = True
            item["cantidad"] = reserva["cantidad"]
            item["precio_unitario"] = reserva["precio_oferta"]
            item["segundos_restantes"] = ofertas_redis.segundos_desde_ms(reserva["ms_restantes"])
            items.append(item)

        cantidad_total = sum(item["cantidad"] for item in items)
        total_pagar = round(sum(item["cantidad"] * item["precio_unitario"] for item in items), 2)

        return jsonify({
            "items": items,
            "cantidad_total": cantidad_total,
            "total_pagar": total_pagar,
            "ofertas_expiradas": ofertas_expiradas,
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
    if ofertas_redis.producto_de_campo(id_producto) is not None:
        return jsonify({"error": "Las líneas de oferta se agregan con POST /api/ofertas/<producto_id>/reservar"}), 400

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
        item_respuesta["id_item"] = id_producto
        item_respuesta["es_oferta"] = False
        item_respuesta["precio_unitario"] = item.get("precio_base")
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

    if ofertas_redis.producto_de_campo(id_producto) is not None:
        return jsonify({"error": "La cantidad de una oferta relámpago no se puede cambiar"}), 400

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
        item_respuesta["id_item"] = id_producto
        item_respuesta["es_oferta"] = False
        item_respuesta["precio_unitario"] = item.get("precio_base")
        return jsonify({"mensaje": "Cantidad actualizada", "item": item_respuesta}), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al actualizar el carrito: {str(e)}"}), 500


@bp.route("/api/carrito/<int:id_usuario>/items/<id_producto>", methods=["DELETE"])
def eliminar_item(id_usuario, id_producto):
    clave = _clave_carrito(id_usuario)
    try:
        producto_oferta = ofertas_redis.producto_de_campo(id_producto)
        if producto_oferta is not None:
            # Quita la línea y libera la reserva en una sola operación Lua:
            # las unidades vuelven a estar disponibles en la oferta ya mismo.
            ofertas_redis.liberar(producto_oferta, id_usuario, clave)
        else:
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
        # Primero se liberan las reservas de las líneas de oferta (si no, sus
        # unidades quedarían apartadas hasta que venza el minuto) y después se
        # borra el carrito. Si Redis cae entre ambos pasos, lo que quede se
        # arregla solo: las reservas vencen y el carrito expira por TTL.
        for campo in redis_client.hkeys(clave):
            producto_oferta = ofertas_redis.producto_de_campo(campo)
            if producto_oferta is not None:
                ofertas_redis.liberar(producto_oferta, id_usuario, clave)
        redis_client.delete(clave)
        return jsonify({"mensaje": "Carrito vaciado"}), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al vaciar el carrito: {str(e)}"}), 500
