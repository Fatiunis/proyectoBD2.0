import json
import uuid
from datetime import datetime

import redis
from flask import Blueprint, request, jsonify
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .. import ofertas_redis
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
#
# Líneas de oferta relámpago (campo "oferta:{pid}" del carrito):
#   - Se mandan al SP como {"id_producto", "cantidad", "precio_unitario"}.
#     Cantidad y precio salen de la RESERVA en Redis (oferta:{pid}:reservas),
#     no de la línea del carrito: la línea es solo una copia para mostrar.
#   - Antes del SP, cada reserva se CONSUME con consumir_reserva_oferta.lua:
#     comprueba (con el reloj de Redis) que exista y no haya vencido, la pasa
#     a "en_pago" y descuenta sus unidades del cupo sin vender, todo atómico.
#     Como una reserva solo se crea si cabe en cupo_sin_vender - activas, y el
#     consumo resta del cupo lo mismo que quita de "activas", el cupo nunca
#     queda negativo: no hay sobreventa aunque haya muchos checkouts a la vez.
#     Un segundo checkout simultáneo del mismo usuario encuentra la reserva
#     "en_pago" y se rechaza (409), así la misma reserva no se paga dos veces.
#   - Si alguna reserva ya venció: se compensan las que sí se consumieron, se
#     quitan del carrito las vencidas y se responde 409
#     RESERVA_OFERTA_EXPIRADA sin llamar al SP.
#   - La reserva se respeta aunque la ventana de la oferta termine dentro de
#     su minuto: precio y cantidad viajan en la reserva.
#
# Fallos parciales Redis <-> Postgres (no hay 2PC; el orden los acota):
#   a. Falla Redis al consumir -> 503; se intentan compensar los consumos ya
#      hechos y no se toca Postgres.
#   b. Falla el SP -> rollback en Postgres y se COMPENSA cada consumo: las
#      unidades vuelven al cupo (si la misma oferta sigue viva) y la reserva
#      vuelve a "activa" con su vencimiento original (si no ha pasado).
#   c. El SP confirma -> las reservas se cierran (quedan como vendidas) y se
#      borra el carrito. Si Redis falla aquí el pedido YA es válido: solo se
#      registra una advertencia; la entrada "en_pago" se purga sola tras
#      ofertas_redis.MARGEN_PAGO_MS y sus unidades siguen contando como
#      vendidas, que es lo correcto.
#   d. Si el proceso muere entre consumir y confirmar/compensar, la entrada
#      "en_pago" también se purga tras el margen y sus unidades quedan como
#      vendidas: se prefiere dejar alguna unidad sin vender antes que sobrevender.
#   e. Si falla la compensación (Redis caído justo tras el fallo del SP), las
#      unidades se pierden para esta oferta (mismo criterio conservador).


def _generar_referencia_pago():
    """Referencia de pago automática: TY-{YYYYMMDDHHMMSS}-{6 hex en mayúsculas}.

    Usa la hora de Guatemala. Mide 24 caracteres (cabe en
    pagos.referencia_transaccion VARCHAR(100), que es UNIQUE). Si por azar
    colisionara, el SP falla, se hace rollback y el cliente puede reintentar.
    """
    marca = datetime.now(ZONA_GUATEMALA).strftime("%Y%m%d%H%M%S")
    return f"TY-{marca}-{uuid.uuid4().hex[:6].upper()}"


def _compensar_consumos(id_comprador, consumos):
    """Deshace los consumos de reservas de un checkout que no se completó."""
    for consumo in consumos:
        try:
            ofertas_redis.compensar(id_comprador, consumo)
        except Exception as e:
            print(f"[checkout] ADVERTENCIA: no se pudo compensar la reserva de "
                  f"{consumo['producto_id']} del usuario {id_comprador}: {e}")


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
    lineas_oferta = []  # (id_item, producto_id, nombre, id_sql_origen)
    for id_item, valor_json in crudo.items():
        try:
            item = json.loads(valor_json)
        except (TypeError, ValueError):
            return jsonify({"error": f"El item {id_item} del carrito está corrupto"}), 400

        id_sql_origen = item.get("id_sql_origen")
        if id_sql_origen is None:
            return jsonify({
                "error": f"El producto {id_item} no tiene id_sql_origen: no existe en el "
                         f"inventario transaccional (Postgres) y no se puede comprar. "
                         f"Quítalo del carrito para continuar."
            }), 400

        producto_oferta = ofertas_redis.producto_de_campo(id_item)
        if producto_oferta is not None:
            lineas_oferta.append((id_item, producto_oferta, item.get("nombre") or producto_oferta, id_sql_origen))
            continue

        items.append({"id_producto": id_sql_origen, "cantidad": item.get("cantidad")})

    # ---- Consumo atómico de las reservas de oferta (antes del SP) ----------
    consumos = []
    expiradas = []   # (producto_id, nombre)
    en_pago = []     # nombres con otro checkout en curso
    try:
        for id_item, producto_oferta, nombre, id_sql_origen in lineas_oferta:
            codigo, consumo = ofertas_redis.consumir(producto_oferta, id_comprador)
            if codigo == "expirada":
                expiradas.append((producto_oferta, nombre))
            elif codigo == "en_pago":
                en_pago.append(nombre)
            else:
                consumos.append(consumo)
                items.append({
                    "id_producto": id_sql_origen,
                    "cantidad": consumo["cantidad"],
                    # El SP exige un número JSON (no string).
                    "precio_unitario": float(consumo["precio_oferta"]),
                })
    except redis.exceptions.RedisError:
        _compensar_consumos(id_comprador, consumos)
        return jsonify({"error": "No se pudo reservar el pago de la oferta (Redis no disponible)"}), 503

    if expiradas or en_pago:
        _compensar_consumos(id_comprador, consumos)
        if expiradas:
            try:
                # estado_linea_oferta.lua quita la línea solo si su reserva ya
                # no existe: no borra una línea de una reserva nueva que el
                # usuario haya hecho entre el consumo fallido y este paso.
                for producto_oferta, _ in expiradas:
                    ofertas_redis.estado_linea(producto_oferta, id_comprador, clave)
            except redis.exceptions.RedisError as e:
                print(f"[checkout] ADVERTENCIA: no se pudieron quitar las ofertas vencidas de {clave}: {e}")
            nombres = ", ".join(nombre for _, nombre in expiradas)
            return jsonify({
                "error": f"Tu reserva de la oferta relámpago de {nombres} expiró y se quitó del carrito. "
                         f"Revisa tu carrito y vuelve a intentarlo.",
                "codigo": "RESERVA_OFERTA_EXPIRADA",
                "ofertas_expiradas": [nombre for _, nombre in expiradas],
            }), 409
        return jsonify({
            "error": f"Ya hay un pago en curso para la oferta de {', '.join(en_pago)}",
            "codigo": "PAGO_EN_CURSO",
        }), 409

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
        _compensar_consumos(id_comprador, consumos)
        diag = getattr(e.orig, "diag", None)
        mensaje_error = (diag.message_primary if diag else None) or str(e.orig).strip()
        return jsonify({"error": mensaje_error}), 400
    except Exception as e:
        db.session.rollback()
        _compensar_consumos(id_comprador, consumos)
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500

    for consumo in consumos:
        try:
            ofertas_redis.confirmar(id_comprador, consumo)
        except Exception as e:
            print(f"[checkout] ADVERTENCIA: pedido {id_pedido} confirmado, pero no se pudo cerrar la "
                  f"reserva de {consumo['producto_id']} en Redis (se purgará sola): {e}")

    try:
        redis_client.delete(clave)
    except Exception as e:
        print(f"[checkout] ADVERTENCIA: pedido {id_pedido} confirmado, pero no se pudo borrar {clave} en Redis: {e}")

    return jsonify({"mensaje": mensaje, "id_pedido": id_pedido, "referencia_pago": referencia_pago}), 201
