import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import redis
from flask import Blueprint, request, jsonify

from .. import ofertas_redis
from ..config import RESERVA_OFERTA_TTL_SEGUNDOS
from ..extensions import redis_client, col_productos, ZONA_GUATEMALA
from .carrito import _clave_carrito, renovar_ttl_carrito

bp = Blueprint("ofertas", __name__)

# ============================================================================
# MÓDULO DE OFERTAS RELÁMPAGO CON RESERVA TEMPORAL (REDIS - ENTREGA 2)
# ============================================================================
# Una oferta pone a la venta un cupo limitado de unidades de un producto a un
# PRECIO DE OFERTA, durante una ventana de tiempo. El cupo es independiente del
# stock real de Postgres/Mongo. Keys y contabilidad: ver app/ofertas_redis.py.
#
# Ciclo de vida de una unidad de la oferta:
#   1. POST /reservar -> reservar_oferta.lua aparta las unidades (reserva
#      "activa" de RESERVA_OFERTA_TTL_SEGUNDOS) SIN descontar el cupo, y se
#      agrega una línea "oferta:{pid}" al carrito del comprador.
#   2a. Si la compra no se completa a tiempo, la reserva vence: la próxima
#       operación sobre la oferta la purga y las unidades vuelven a estar
#       disponibles. Quitar la línea del carrito la libera en el acto.
#   2b. POST /api/checkout -> consumir_reserva_oferta.lua pasa la reserva a
#       "en_pago" y descuenta el cupo; si el SP confirma, las unidades quedan
#       vendidas; si falla, compensar_reserva_oferta.lua lo deshace.
#
# Sin sobreventa: disponibilidad = cupo_sin_vender - reservas activas, y tanto
# la comprobación como el alta de la reserva ocurren dentro del MISMO script
# Lua, que Redis ejecuta atómicamente en su hilo único (sin locks de
# aplicación ni WATCH/MULTI). La hora de vencimiento sale de TIME de Redis.
#
# Ventana de tiempo: stock, límite, precio e id se crean con EX =
# duracion_minutos*60 y es Redis quien las expira. Una reserva hecha antes del
# final se respeta completa aunque la ventana termine dentro de su minuto
# (precio y cantidad viajan en la reserva); por eso el hash de reservas vive
# la ventana más la duración de una reserva.
#
# Precio de oferta: se fija SOLO al crear. No hay endpoint de edición; para
# cambiarlo se finaliza la oferta (DELETE) y se crea otra.
#
# Propiedad: solo el vendedor dueño del producto (vendedor.id_vendedor en el
# documento de Mongo) o un administrador pueden crear/finalizar su oferta.
# Solo un comprador puede reservar.
#
# Listados: GET /api/ofertas es PÚBLICO (sin autenticación) y devuelve todas
# las ofertas activas de productos activos para el sitio público; GET
# /api/vendedores/<id>/ofertas devuelve solo las del vendedor. Ambos salen de
# _ofertas_activas (SCAN de Redis + Mongo + consultar_oferta.lua por oferta).

ROLES_VALIDOS = ("vendedor", "administrador")

LIMITE_LISTADO_PUBLICO_MAXIMO = 100

DURACION_MINIMA_MINUTOS = 1
DURACION_MAXIMA_MINUTOS = 10080  # 7 días


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


def _validar_precio_oferta(valor, precio_base):
    """Devuelve (Decimal, None) si el precio es válido o (None, mensaje)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None, "precio_oferta es obligatorio y debe ser un número"
    try:
        # str() evita arrastrar el error binario del float (99.99 -> "99.99").
        precio = Decimal(str(valor))
    except InvalidOperation:
        return None, "precio_oferta debe ser un número válido"
    if not precio.is_finite():
        return None, "precio_oferta debe ser un número válido"
    if precio <= 0:
        return None, "precio_oferta debe ser mayor que 0"
    if precio.as_tuple().exponent < -2:
        return None, "precio_oferta admite como máximo 2 decimales"
    if precio_base is None:
        return None, "El producto no tiene precio_base: no se le puede crear una oferta"
    base = Decimal(str(precio_base))
    if precio >= base:
        return None, f"precio_oferta ({precio}) debe ser menor que el precio_base del producto ({base})"
    return precio.quantize(Decimal("0.01")), None


def _validar_propietario(producto, rol_solicitante, id_usuario):
    """Devuelve (respuesta, status) de error si el solicitante NO puede
    gestionar la oferta de este producto, o None si puede."""
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


def _descuento_pct(precio_oferta, precio_base):
    # Porcentaje entero redondeado sobre el precio_base de Mongo; None si no
    # hay base válida (no se puede calcular sin inventar un número).
    try:
        base = Decimal(str(precio_base))
        oferta = Decimal(str(precio_oferta))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not base.is_finite() or not oferta.is_finite() or base <= 0:
        return None
    # Piso 0: si el precio_base se editó por debajo del precio de oferta, no
    # se reporta un "descuento" negativo. Tope 99 (H-017): un descuento > 0
    # nunca se muestra como 100 % (p. ej. Q1 sobre Q12 500); coherente con
    # frontend/app/src/utils/descuento.js.
    return min(99, max(0, int(((base - oferta) / base * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))))


def _imagen_portada(producto):
    imagenes = producto.get("imagenes") or []
    for img in imagenes:
        if isinstance(img, dict) and img.get("es_portada"):
            return img.get("url")
    if imagenes and isinstance(imagenes[0], dict):
        return imagenes[0].get("url")
    return None


def _ofertas_activas(filtro_mongo, incluir_catalogo=False):
    """Arma la lista de ofertas activas cuyos productos cumplen filtro_mongo.

    Las ofertas activas son pocas: SCAN de oferta:*:id y luego un solo find
    en Mongo con los pids encontrados más el filtro del llamador. Con
    incluir_catalogo se agregan categoria y vendedor (listado público).
    Las RedisError se propagan para que el endpoint responda 500."""
    pids = ofertas_redis.pids_con_oferta_activa()
    if not pids:
        return []

    proyeccion = {"nombre": 1, "precio_base": 1, "imagenes": 1}
    if incluir_catalogo:
        proyeccion.update({"categoria": 1, "vendedor": 1})
    cursor = col_productos.find({**filtro_mongo, "_id": {"$in": pids}}, proyeccion)
    productos = {p["_id"]: p for p in cursor}

    ofertas = []
    for pid, producto in productos.items():
        # consultar_oferta.lua da la foto atómica (y purga reservas
        # vencidas). None = la oferta venció entre el SCAN y esta lectura.
        oferta = ofertas_redis.consultar(pid)
        if oferta is None:
            continue
        # TTL -1 = key sin expiración: se reporta None (ver obtener_oferta).
        ttl_ms = oferta["ttl_ms"]
        segundos_restantes = ofertas_redis.segundos_desde_ms(ttl_ms) if ttl_ms >= 0 else None
        precio_base = producto.get("precio_base")
        item = {
            "producto_id": pid,
            "nombre": producto.get("nombre"),
            "imagen_url": _imagen_portada(producto),
            "precio_base": float(precio_base) if precio_base is not None else None,
            "precio_oferta": oferta["precio_oferta"],
            "descuento_pct": _descuento_pct(oferta["precio_oferta"], precio_base),
            "cantidad_limite": oferta["limite"],
            "stock_restante": oferta["stock_restante"],
            "unidades_reservadas": oferta["unidades_reservadas"],
            "unidades_vendidas": oferta["unidades_vendidas"],
            "segundos_restantes": segundos_restantes,
            "fecha_fin": _fecha_fin_desde_ttl(segundos_restantes),
        }
        if incluir_catalogo:
            categoria = producto.get("categoria") if isinstance(producto.get("categoria"), dict) else None
            vendedor = producto.get("vendedor") if isinstance(producto.get("vendedor"), dict) else None
            item["categoria"] = {
                "id_categoria": categoria.get("id_categoria"),
                "nombre": categoria.get("nombre"),
            } if categoria else None
            # En Mongo el nombre del vendedor es nombre_comercial; se expone
            # como "nombre" (con nombre de respaldo por si un doc lo trae así).
            item["vendedor"] = {
                "id_vendedor": vendedor.get("id_vendedor"),
                "nombre": vendedor.get("nombre_comercial") or vendedor.get("nombre"),
            } if vendedor else None
        ofertas.append(item)
    return ofertas


def _clave_vencimiento(oferta):
    # Las que vencen antes primero; las sin TTL (None) al final.
    return (oferta["segundos_restantes"] is None,
            oferta["segundos_restantes"] or 0, oferta["producto_id"])


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

    if "precio_oferta" not in data:
        return jsonify({"error": "precio_oferta es obligatorio"}), 400

    rol_solicitante = data.get("rol_solicitante")
    if rol_solicitante not in ROLES_VALIDOS:
        return jsonify({"error": "rol_solicitante debe ser 'vendedor' o 'administrador'"}), 403

    id_usuario = data.get("id_usuario")
    if not _es_entero(id_usuario):
        return jsonify({"error": "id_usuario es obligatorio y debe ser un entero"}), 400

    segundos = duracion_minutos * 60

    try:
        producto = col_productos.find_one({"_id": producto_id}, {"vendedor": 1, "precio_base": 1})
        error_propietario = _validar_propietario(producto, rol_solicitante, id_usuario)
        if error_propietario is not None:
            return error_propietario

        precio_base = producto.get("precio_base")
        precio_oferta, error_precio = _validar_precio_oferta(data.get("precio_oferta"), precio_base)
        if error_precio:
            return jsonify({"error": error_precio}), 400

        # crear_oferta.lua escribe stock, límite, precio e id en un solo paso
        # atómico (todas con el mismo EX): o se crea la oferta completa o no
        # se crea nada. Reemplaza al SET NX + SET + DELETE compensatorio.
        creada = ofertas_redis.crear(producto_id, cantidad_limite, str(precio_oferta), segundos)
        if not creada:
            return jsonify({"error": "Ya existe una oferta activa para este producto"}), 409

        return jsonify({
            "mensaje": "Oferta creada",
            "producto_id": producto_id,
            "cantidad_limite": cantidad_limite,
            "precio_oferta": float(precio_oferta),
            "precio_base": float(precio_base),
            "descuento_pct": _descuento_pct(precio_oferta, precio_base),
            "duracion_minutos": duracion_minutos,
            "segundos_restantes": segundos,
            "fecha_fin": _fecha_fin_desde_ttl(segundos),
        }), 201
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al crear la oferta: {str(e)}"}), 500


@bp.route("/api/ofertas", methods=["GET"])
def listar_ofertas_publicas():
    # Listado PÚBLICO (sin autenticación) para el sitio: todas las ofertas
    # activas de productos activos. Mismo criterio que el catálogo público
    # (activo: True en Mongo, ver catalogo.py).
    limite_txt = request.args.get("limite")
    limite = LIMITE_LISTADO_PUBLICO_MAXIMO
    if limite_txt is not None:
        try:
            limite = int(limite_txt)
        except ValueError:
            limite = None
        if limite is None or not 1 <= limite <= LIMITE_LISTADO_PUBLICO_MAXIMO:
            return jsonify({
                "error": f"limite debe ser un entero entre 1 y {LIMITE_LISTADO_PUBLICO_MAXIMO}"
            }), 400

    try:
        ofertas = _ofertas_activas({"activo": True}, incluir_catalogo=True)
        # Primero las que aún tienen cupo; las agotadas al final (el frontend
        # las muestra como "Agotada"). Dentro de cada grupo, las que vencen antes.
        ofertas.sort(key=lambda o: (o["stock_restante"] <= 0, *_clave_vencimiento(o)))
        # total = ofertas activas antes de recortar por limite.
        return jsonify({"ofertas": ofertas[:limite], "total": len(ofertas)}), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al listar las ofertas: {str(e)}"}), 500


@bp.route("/api/ofertas/<producto_id>", methods=["GET"])
def obtener_oferta(producto_id):
    id_usuario = request.args.get("id_usuario")
    if id_usuario is not None:
        try:
            id_usuario = int(id_usuario)
        except ValueError:
            return jsonify({"error": "id_usuario debe ser un entero"}), 400

    try:
        # consultar_oferta.lua lee cupo, límite, precio, TTL y reservas en el
        # mismo instante (y purga las vencidas), sin que una reserva, un pago
        # o la expiración se cuelen en medio.
        oferta = ofertas_redis.consultar(producto_id, id_usuario)
        if oferta is None:
            return jsonify({"error": "No hay oferta activa para este producto"}), 404

        producto = col_productos.find_one({"_id": producto_id}, {"precio_base": 1}) or {}

        # TTL -1 = key sin expiración (oferta creada antes de existir la
        # ventana de tiempo); se reporta None en vez de un número engañoso.
        ttl_ms = oferta["ttl_ms"]
        segundos_restantes = ofertas_redis.segundos_desde_ms(ttl_ms) if ttl_ms >= 0 else None

        return jsonify({
            "producto_id": producto_id,
            "precio_oferta": oferta["precio_oferta"],
            "precio_base": producto.get("precio_base"),
            "descuento_pct": _descuento_pct(oferta["precio_oferta"], producto.get("precio_base")),
            "cantidad_limite": oferta["limite"],
            "stock_restante": oferta["stock_restante"],
            "unidades_reservadas": oferta["unidades_reservadas"],
            "unidades_vendidas": oferta["unidades_vendidas"],
            "segundos_restantes": segundos_restantes,
            "fecha_fin": _fecha_fin_desde_ttl(segundos_restantes),
            "reserva_usuario": oferta["reserva_usuario"],
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

    if data.get("rol_solicitante") != "comprador":
        return jsonify({"error": "Solo un comprador puede reservar una oferta"}), 403

    id_usuario = data.get("id_usuario")
    if not _es_entero(id_usuario):
        return jsonify({"error": "id_usuario debe ser un entero"}), 400

    cantidad = data.get("cantidad")
    if not _es_entero_positivo(cantidad):
        return jsonify({"error": "cantidad debe ser un entero positivo"}), 400

    clave_carrito = _clave_carrito(id_usuario)

    try:
        # Se lee Mongo ANTES de reservar: es solo lectura, y así un fallo de
        # Mongo no deja una reserva huérfana apartando unidades.
        producto = col_productos.find_one(
            {"_id": producto_id},
            {"nombre": 1, "precio_base": 1, "id_sql_origen": 1, "categoria": 1, "imagenes": 1},
        )
        if producto is None:
            return jsonify({"error": "Producto no encontrado"}), 404
        if producto.get("id_sql_origen") is None:
            return jsonify({
                "error": "El producto no existe en el inventario transaccional y no se puede comprar"
            }), 400

        codigo, reserva = ofertas_redis.reservar(producto_id, id_usuario, cantidad)
        if codigo == "sin_oferta":
            return jsonify({"error": "No hay oferta activa para este producto"}), 404
        if codigo == "duplicada":
            return jsonify({"error": "Ya tienes una reserva activa en esta oferta"}), 409
        if codigo == "sin_stock":
            return jsonify({"error": "Stock insuficiente en la oferta"}), 409

        precio_oferta = float(reserva["precio_oferta"])
        expira_en = ofertas_redis.iso_en_ms(reserva["ms_restantes"])

        # Línea de oferta SEPARADA en el carrito (campo "oferta:{pid}"), para
        # no mezclarla con una línea normal del mismo producto. El precio que
        # se cobra NO sale de aquí sino de la reserva (ver checkout.py).
        linea = {
            "es_oferta": True,
            "id_producto_catalogo": producto_id,
            "cantidad": cantidad,
            "id_sql_origen": producto.get("id_sql_origen"),
            "nombre": producto.get("nombre"),
            "precio_base": producto.get("precio_base"),
            "precio_unitario": precio_oferta,
            "id_categoria": (producto.get("categoria") or {}).get("id_categoria"),
            "imagen_url": _imagen_portada(producto),
            "expira_en": expira_en,
        }
        try:
            redis_client.hset(clave_carrito, ofertas_redis.campo_linea_oferta(producto_id), json.dumps(linea))
            renovar_ttl_carrito(clave_carrito)
        except redis.exceptions.RedisError:
            # Fallo parcial: la reserva existe pero no llegó al carrito. Se
            # libera para no apartar unidades que nadie puede comprar. Si
            # Redis tampoco responde para liberarla, vence sola en
            # RESERVA_OFERTA_TTL_SEGUNDOS.
            try:
                ofertas_redis.liberar(producto_id, id_usuario, clave_carrito)
            except redis.exceptions.RedisError:
                pass
            raise

        return jsonify({
            "mensaje": "Producto agregado al carrito con precio de oferta",
            "reserva": {
                "cantidad": cantidad,
                "precio_oferta": precio_oferta,
                "segundos_restantes": RESERVA_OFERTA_TTL_SEGUNDOS,
                "expira_en": expira_en,
            },
            "stock_restante": reserva["stock_restante"],
        }), 201
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
        producto = col_productos.find_one({"_id": producto_id}, {"vendedor": 1})
        error_propietario = _validar_propietario(producto, rol_solicitante, id_usuario)
        if error_propietario is not None:
            return error_propietario

        # Borra cupo, límite, precio, id y reservas. Las líneas de oferta que
        # queden en carritos se quitan solas al leer el carrito (su reserva ya
        # no existe) y el checkout las rechaza con RESERVA_OFERTA_EXPIRADA.
        # Un checkout que ya consumió su reserva ("en_pago") sigue adelante: el
        # precio viaja en la reserva consumida.
        ofertas_redis.finalizar(producto_id)
        return jsonify({"mensaje": "Oferta finalizada"}), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al finalizar la oferta: {str(e)}"}), 500


@bp.route("/api/vendedores/<int:id_vendedor>/ofertas", methods=["GET"])
def listar_ofertas_vendedor(id_vendedor):
    # Vive aquí (y no en vendedores.py) para reutilizar los helpers de ofertas
    # sin imports cruzados entre blueprints.
    rol_solicitante = request.args.get("rol_solicitante")
    if rol_solicitante not in ROLES_VALIDOS:
        return jsonify({"error": "rol_solicitante debe ser 'vendedor' o 'administrador'"}), 403

    try:
        id_usuario = int(request.args.get("id_usuario"))
    except (TypeError, ValueError):
        return jsonify({"error": "id_usuario es obligatorio y debe ser un entero"}), 400

    if rol_solicitante == "vendedor" and id_usuario != id_vendedor:
        return jsonify({"error": "Solo puedes ver tus propias ofertas"}), 403

    try:
        # Se filtra por dueño en Mongo. id_vendedor puede estar guardado como
        # int o como string (ver _validar_propietario), por eso se buscan ambas
        # formas. Sin filtro de activo: el vendedor ve también las de sus
        # productos desactivados.
        ofertas = _ofertas_activas(
            {"vendedor.id_vendedor": {"$in": [id_vendedor, str(id_vendedor)]}}
        )
        ofertas.sort(key=_clave_vencimiento)
        return jsonify({"ofertas": ofertas, "total": len(ofertas)}), 200
    except redis.exceptions.RedisError as e:
        return jsonify({"error": f"No se pudo conectar a Redis: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Error al listar las ofertas: {str(e)}"}), 500
