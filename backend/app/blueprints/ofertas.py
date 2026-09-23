import os
from datetime import datetime, timedelta

import redis
from flask import Blueprint, request, jsonify

from ..extensions import redis_client, col_productos, ZONA_GUATEMALA

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
#
# Ventana de tiempo: el enunciado exige que la oferta esté disponible solo
# durante una ventana determinada. En vez de guardar una fecha de fin y
# compararla en cada request (check-then-act otra vez), ambas keys se crean con
# EX = duracion_minutos*60 y es Redis quien las expira. Cuando vencen, el GET
# del script Lua devuelve nil -> -1 -> 404 "No hay oferta activa", sin lógica
# extra. DECRBY modifica el valor en sitio y NO borra el TTL de la key (solo
# los comandos que sobrescriben la key, como SET, lo descartan), así que las
# reservas no "extienden" ni "congelan" la ventana de la oferta.
#
# Propiedad: solo el vendedor dueño del producto (vendedor.id_vendedor en el
# documento de Mongo) o un administrador pueden crear/finalizar su oferta.

_RUTA_SCRIPT_LUA = os.path.join(os.path.dirname(__file__), "..", "lua", "reservar_oferta.lua")
with open(_RUTA_SCRIPT_LUA, "r", encoding="utf-8") as _f:
    _CODIGO_SCRIPT_RESERVAR = _f.read()

# Se carga una sola vez al importar el módulo. Si Redis pierde la caché de
# scripts (p.ej. reinicio, FLUSHALL, o simplemente porque este proceso lo
# cargó y otro la limpió), _ejecutar_reserva lo recarga y reintenta.
_sha_script_reservar = redis_client.script_load(_CODIGO_SCRIPT_RESERVAR)

ROLES_VALIDOS = ("vendedor", "administrador")

DURACION_MINIMA_MINUTOS = 1
DURACION_MAXIMA_MINUTOS = 10080  # 7 días


def _clave_stock(producto_id):
    return f"oferta:{producto_id}:stock"


def _clave_limite(producto_id):
    return f"oferta:{producto_id}:limite"


def _es_entero_positivo(valor):
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def _es_entero(valor):
    return isinstance(valor, int) and not isinstance(valor, bool)


def _fecha_fin_desde_ttl(segundos_restantes):
    # El TTL de Redis es la fuente de verdad; fecha_fin es solo una
    # conveniencia para el frontend, derivada de él con el offset de Guatemala.
    if segundos_restantes is None or segundos_restantes < 0:
        return None
    fin = datetime.now(ZONA_GUATEMALA) + timedelta(seconds=segundos_restantes)
    return fin.replace(microsecond=0).isoformat()


def _validar_propietario(producto_id, rol_solicitante, id_usuario):
    """Devuelve (respuesta, status) de error si el solicitante NO puede
    gestionar la oferta de este producto, o None si puede."""
    producto = col_productos.find_one({"_id": producto_id}, {"vendedor": 1})
    if producto is None:
        return jsonify({"error": "Producto no encontrado"}), 404

    if rol_solicitante == "administrador":
        return None

    id_vendedor = (producto.get("vendedor") or {}).get("id_vendedor")
    # Productos creados a mano desde el admin podrían traer id_vendedor como
    # string; se normaliza a int antes de comparar para no rechazar al dueño.
    try:
        id_vendedor = int(id_vendedor)
    except (TypeError, ValueError):
        id_vendedor = None

    if id_vendedor != id_usuario:
        return jsonify({"error": "Solo puedes gestionar ofertas de tus propios productos"}), 403
    return None


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

    duracion_minutos = data.get("duracion_minutos")
    if (not _es_entero(duracion_minutos)
            or not DURACION_MINIMA_MINUTOS <= duracion_minutos <= DURACION_MAXIMA_MINUTOS):
        return jsonify({
            "error": f"duracion_minutos es obligatorio y debe ser un entero entre "
                     f"{DURACION_MINIMA_MINUTOS} y {DURACION_MAXIMA_MINUTOS} (7 días)"
        }), 400

    rol_solicitante = data.get("rol_solicitante")
    if rol_solicitante not in ROLES_VALIDOS:
        return jsonify({"error": "rol_solicitante debe ser 'vendedor' o 'administrador'"}), 403

    id_usuario = data.get("id_usuario")
    if not _es_entero(id_usuario):
        return jsonify({"error": "id_usuario es obligatorio y debe ser un entero"}), 400

    clave_stock = _clave_stock(producto_id)
    clave_limite = _clave_limite(producto_id)
    segundos = duracion_minutos * 60

    try:
        error_propietario = _validar_propietario(producto_id, rol_solicitante, id_usuario)
        if error_propietario is not None:
            return error_propietario

        # SET NX EX en un solo comando: la creación y la expiración son
        # atómicas, no puede quedar una key de stock sin TTL entre dos llamadas.
        creada = redis_client.set(clave_stock, cantidad_limite, nx=True, ex=segundos)
        if not creada:
            return jsonify({"error": "Ya existe una oferta activa para este producto"}), 409

        try:
            # Mismo EX que el stock: ambas keys vencen juntas.
            redis_client.set(clave_limite, cantidad_limite, ex=segundos)
        except redis.exceptions.RedisError:
            # Si no se pudo guardar el límite, se deshace la oferta para no
            # dejar una oferta a medias (stock sin límite asociado).
            redis_client.delete(clave_stock)
            raise

        return jsonify({
            "mensaje": "Oferta creada",
            "producto_id": producto_id,
            "cantidad_limite": cantidad_limite,
            "duracion_minutos": duracion_minutos,
            "segundos_restantes": segundos,
            "fecha_fin": _fecha_fin_desde_ttl(segundos),
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
        # Pipeline transaccional (MULTI/EXEC): stock, límite y TTL se leen en el
        # mismo instante, sin que una reserva o la expiración se cuele en medio.
        pipe = redis_client.pipeline(transaction=True)
        pipe.get(clave_stock)
        pipe.get(clave_limite)
        pipe.ttl(clave_stock)
        stock_raw, limite_raw, ttl = pipe.execute()
        if stock_raw is None:
            return jsonify({"error": "No hay oferta activa para este producto"}), 404

        # TTL -1 = key sin expiración (oferta creada antes de existir la
        # ventana de tiempo); se reporta None en vez de un número engañoso.
        segundos_restantes = ttl if ttl is not None and ttl >= 0 else None

        return jsonify({
            "producto_id": producto_id,
            "stock_restante": int(stock_raw),
            "cantidad_limite": int(limite_raw) if limite_raw is not None else None,
            "segundos_restantes": segundos_restantes,
            "fecha_fin": _fecha_fin_desde_ttl(segundos_restantes),
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

    id_usuario = data.get("id_usuario")
    if id_usuario is None:
        id_usuario = request.args.get("id_usuario")
    # En query string llega como texto; se convierte a int si es numérico.
    if isinstance(id_usuario, str):
        try:
            id_usuario = int(id_usuario)
        except ValueError:
            id_usuario = None
    if not _es_entero(id_usuario):
        return jsonify({"error": "id_usuario es obligatorio y debe ser un entero"}), 400

    try:
        error_propietario = _validar_propietario(producto_id, rol_solicitante, id_usuario)
        if error_propietario is not None:
            return error_propietario

        redis_client.delete(_clave_stock(producto_id), _clave_limite(producto_id))
        return jsonify({"mensaje": "Oferta finalizada"}), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al finalizar la oferta: {str(e)}"}), 500
