import json
import re
import uuid
from datetime import datetime

import redis
from flask import Blueprint, request, jsonify
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from .. import ofertas_redis, sincronizacion
from ..config import PERMITIR_FALLAS_SIMULADAS
from ..extensions import db, redis_client, ZONA_GUATEMALA
from ..models import CheckoutIdempotencia, EventoSincronizacion
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
# ESTRATEGIA DE CONSISTENCIA (Entrega 3). Detalle completo, con cada punto de
# falla y su mitigación, en docs/estrategia-consistencia-checkout.md. Resumen:
#
#   PostgreSQL es la fuente de verdad del pedido, el pago y el inventario, y
#   la ÚNICA transacción ACID del flujo. Todo lo demás se ordena alrededor de
#   ella, sin 2PC:
#
#   1. Clave de idempotencia (clave_idempotencia en el body o el header
#      Idempotency-Key): si ya existe un pedido con esa clave, se devuelve ese
#      mismo pedido (200, "repetido": true) sin tocar nada. Cubre el caso más
#      peligroso: el cliente no recibe la respuesta (timeout, se cae la red) y
#      reintenta un pago que en realidad SÍ se confirmó.
#   2. Lectura del carrito en Redis. Antes se aplica la limpieza de carrito
#      que haya quedado pendiente de un pedido anterior del mismo comprador,
#      para no volver a cobrar lo que ya se pagó. Si Redis falla -> 503 y no
#      se toca nada.
#   3. Consumo atómico (Lua) de las reservas de oferta relámpago: pasan a
#      "en_pago" y se descuenta el cupo. Si algo falla de aquí en adelante y
#      antes del COMMIT, se COMPENSAN (las unidades vuelven a la oferta).
#   4. UNA transacción en PostgreSQL: fila de idempotencia + sp_procesar_checkout
#      (pedido, líneas, pago, inventario) + eventos de sincronización (outbox).
#      O se confirma todo o nada. Si falla por un error de negocio (stock
#      insuficiente, dirección ajena...) -> 400; si falla la base de datos ->
#      503, el usuario puede reintentar con la misma clave sin riesgo.
#   5. Después del COMMIT el pedido es válido pase lo que pase. Lo que queda
#      en otros motores (cerrar reservas y limpiar el carrito en Redis, copiar
#      el stock a MongoDB y a Elasticsearch) son eventos del outbox: se
#      intentan de inmediato y, si fallan, el relevo de app/sincronizacion.py
#      los reintenta con espera creciente. Todos son idempotentes. El cliente
#      recibe 201 igual, con "sincronizacion_pendiente": true si quedó algo.
#
# Líneas de oferta relámpago (campo "oferta:{pid}" del carrito):
#   - Se mandan al SP como {"id_producto", "cantidad", "precio_unitario"}.
#     Cantidad y precio salen de la RESERVA en Redis (oferta:{pid}:reservas),
#     no de la línea del carrito: la línea es solo una copia para mostrar.
#   - consumir_reserva_oferta.lua comprueba (con el reloj de Redis) que la
#     reserva exista y no haya vencido, la pasa a "en_pago" y descuenta sus
#     unidades del cupo sin vender, todo atómico. Un segundo checkout
#     simultáneo del mismo usuario encuentra la reserva "en_pago" y se rechaza
#     (409), así la misma reserva no se paga dos veces.
#   - Si alguna reserva ya venció: se compensan las que sí se consumieron, se
#     quitan del carrito las vencidas y se responde 409 RESERVA_OFERTA_EXPIRADA
#     sin llamar al SP.
#   - Si el proceso muere entre consumir y confirmar/compensar, la entrada
#     "en_pago" se purga tras ofertas_redis.MARGEN_PAGO_MS y sus unidades
#     quedan como vendidas: se prefiere dejar alguna unidad sin vender antes
#     que sobrevender.

PATRON_CLAVE_IDEMPOTENCIA = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# Fallas simuladas para la prueba de falla (solo con PERMITIR_FALLAS_SIMULADAS=1).
PUNTOS_DE_FALLA = {
    "redis_lectura_carrito": "Redis no responde al leer el carrito (antes de tocar nada).",
    "postgres_antes_commit": "PostgreSQL se cae después de ejecutar el procedimiento y antes del COMMIT.",
    "redis_post_commit": "Redis no responde después de confirmar el pedido (cerrar reservas y limpiar el carrito).",
    "mongo_post_commit": "MongoDB no responde al copiar el stock después de confirmar el pedido.",
    "elasticsearch_post_commit": "Elasticsearch no responde al copiar el stock después de confirmar el pedido.",
}


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


def _falla_simulada(data):
    """Punto de falla pedido en el body, solo si las fallas simuladas están
    habilitadas en el .env; en cualquier otro caso se ignora."""
    punto = data.get("simular_falla")
    if PERMITIR_FALLAS_SIMULADAS and punto in PUNTOS_DE_FALLA:
        print(f"[checkout] FALLA SIMULADA activa: {punto}")
        return punto
    return None


def _respuesta_repetida(registro):
    """Respuesta a un reintento de un checkout que ya se había confirmado.
    Aprovecha para reintentar los eventos pendientes de ese pedido (por
    ejemplo, limpiar el carrito si Redis había fallado la primera vez)."""
    pendientes = [
        e.id_evento for e in db.session.query(EventoSincronizacion.id_evento)
        .filter_by(id_pedido=registro.id_pedido, estado="pendiente").all()
    ]
    resumen = {"procesados": 0, "pendientes": 0}
    try:
        resumen = sincronizacion.procesar(ids=pendientes)
    except Exception as e:
        db.session.rollback()
        print(f"[checkout] ADVERTENCIA: no se pudieron reintentar los eventos del pedido {registro.id_pedido}: {e}")
    return jsonify({
        "mensaje": "Este pedido ya se había confirmado; no se volvió a cobrar.",
        "id_pedido": registro.id_pedido,
        "referencia_pago": registro.referencia_pago,
        "repetido": True,
        "sincronizacion_pendiente": resumen.get("pendientes", 0) > 0,
    }), 200


def _id_entero(valor):
    """Normaliza un id que puede llegar como número o como string ("12").
    Devuelve el int (> 0) o None si no es un entero válido. Hace falta para
    comparar con lo guardado en checkout_idempotencia (INTEGER): 12 != "12"."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor > 0 else None
    if isinstance(valor, str) and valor.strip().isascii() and valor.strip().isdecimal():
        n = int(valor.strip())
        return n if n > 0 else None
    return None


@bp.route("/api/checkout/fallas-simuladas", methods=["GET"])
def fallas_simuladas():
    """Le dice al frontend si puede ofrecer el selector de falla simulada."""
    return jsonify({
        "habilitadas": PERMITIR_FALLAS_SIMULADAS,
        "puntos": [{"punto": k, "descripcion": v} for k, v in PUNTOS_DE_FALLA.items()]
        if PERMITIR_FALLAS_SIMULADAS else [],
    })


@bp.route("/api/checkout", methods=["POST"])
def procesar_checkout():
    data = request.get_json(silent=True) or {}
    id_comprador = data.get("id_comprador")
    id_direccion = data.get("id_direccion")
    metodo_pago = data.get("metodo_pago")
    # La referencia de pago la genera SIEMPRE el backend; si el cliente manda
    # "referencia_pago" se ignora a propósito.
    clave_idempotencia = data.get("clave_idempotencia") or request.headers.get("Idempotency-Key")
    falla = _falla_simulada(data)

    if not all([id_comprador, id_direccion, metodo_pago]):
        return jsonify({"error": "id_comprador, id_direccion y metodo_pago son obligatorios"}), 400
    # A partir de aquí id_comprador es siempre int (la comparación con la clave
    # de idempotencia, la clave del carrito y el SP ven el mismo valor).
    id_comprador = _id_entero(id_comprador)
    if id_comprador is None:
        return jsonify({"error": "id_comprador debe ser un número entero positivo"}), 400
    if clave_idempotencia is not None and not (
        isinstance(clave_idempotencia, str) and PATRON_CLAVE_IDEMPOTENCIA.match(clave_idempotencia)
    ):
        return jsonify({"error": "clave_idempotencia debe tener entre 8 y 64 caracteres (letras, números, - o _)"}), 400

    # ---- 1. ¿Es un reintento de un pago ya confirmado? ---------------------
    if clave_idempotencia:
        try:
            registro = db.session.get(CheckoutIdempotencia, clave_idempotencia)
        except Exception as e:
            db.session.rollback()
            print(f"[checkout] ADVERTENCIA: no se pudo consultar la clave de idempotencia: {e}")
            return jsonify({
                "error": "No pudimos procesar tu pago en este momento. No se realizó ningún cobro; intenta de nuevo.",
                "codigo": "SERVICIO_NO_DISPONIBLE",
            }), 503
        if registro is not None:
            if registro.id_comprador != id_comprador:
                return jsonify({"error": "La clave de idempotencia pertenece a otro comprador",
                                "codigo": "CLAVE_IDEMPOTENCIA_AJENA"}), 409
            return _respuesta_repetida(registro)
        db.session.rollback()

    clave = _clave_carrito(id_comprador)

    # ---- 2. Carrito en Redis -------------------------------------------------
    # Si un pedido anterior de este comprador dejó pendiente la limpieza de su
    # carrito (Redis falló justo después del COMMIT), se aplica ANTES de leer:
    # si no, lo que ya se pagó seguiría en el carrito y un nuevo checkout (con
    # otra clave de idempotencia, p. ej. tras recargar la página) lo cobraría
    # otra vez.
    try:
        limpiezas = [
            e.id_evento for e in db.session.query(EventoSincronizacion.id_evento).filter(
                EventoSincronizacion.estado == "pendiente",
                EventoSincronizacion.tipo == "limpiar_carrito",
                EventoSincronizacion.payload["id_comprador"].astext == str(id_comprador),
            ).all()
        ]
        if limpiezas:
            r = sincronizacion.procesar(ids=limpiezas)
            if r["pendientes"] or r["fallidos"]:
                return jsonify({
                    "error": "Todavía estamos terminando de registrar tu compra anterior. "
                             "Intenta de nuevo en unos segundos; no se realizó ningún cobro.",
                    "codigo": "CARRITO_NO_DISPONIBLE",
                }), 503
        else:
            db.session.rollback()
    except Exception as e:
        db.session.rollback()
        print(f"[checkout] ADVERTENCIA: no se pudo revisar la limpieza pendiente del carrito de {id_comprador}: {e}")
        return jsonify({
            "error": "No pudimos procesar tu pago en este momento. No se realizó ningún cobro; intenta de nuevo.",
            "codigo": "SERVICIO_NO_DISPONIBLE",
        }), 503

    try:
        if falla == "redis_lectura_carrito":
            raise redis.exceptions.ConnectionError("Falla simulada: Redis no responde")
        crudo = redis_client.hgetall(clave)
    except redis.exceptions.RedisError:
        return jsonify({
            "error": "No pudimos leer tu carrito en este momento. No se realizó ningún cobro; intenta de nuevo en unos segundos.",
            "codigo": "CARRITO_NO_DISPONIBLE",
        }), 503

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

    # ---- 3. Consumo atómico de las reservas de oferta (antes del SP) ----------
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
        return jsonify({
            "error": "No pudimos apartar tu oferta en este momento. No se realizó ningún cobro; intenta de nuevo.",
            "codigo": "CARRITO_NO_DISPONIBLE",
        }), 503

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

    # ---- 4. Una sola transacción en PostgreSQL -------------------------------
    # 4a. La clave de idempotencia va primero: si otra petición con la misma
    # clave está en curso, este INSERT espera a que termine (índice único) y
    # luego falla, en vez de cobrar dos veces.
    if clave_idempotencia:
        try:
            db.session.add(CheckoutIdempotencia(clave=clave_idempotencia, id_comprador=id_comprador))
            db.session.flush()
        except IntegrityError as e:
            db.session.rollback()
            _compensar_consumos(id_comprador, consumos)
            restriccion = getattr(getattr(e.orig, "diag", None), "constraint_name", None)
            if restriccion != "checkout_idempotencia_pkey":
                return jsonify({"error": f"El usuario comprador {id_comprador} no existe"}), 400
            registro = db.session.get(CheckoutIdempotencia, clave_idempotencia)
            if registro is not None and registro.id_comprador == id_comprador:
                return _respuesta_repetida(registro)
            return jsonify({"error": "Ya hay un pago en curso con esta clave", "codigo": "PAGO_EN_CURSO"}), 409
        except Exception as e:
            db.session.rollback()
            _compensar_consumos(id_comprador, consumos)
            print(f"[checkout] ADVERTENCIA: no se pudo registrar la clave de idempotencia: {e}")
            return jsonify({
                "error": "No pudimos procesar tu pago en este momento. No se realizó ningún cobro; intenta de nuevo.",
                "codigo": "PAGO_NO_CONFIRMADO",
            }), 503

    try:
        # 4b. Pedido, líneas, pago e inventario (sp_procesar_checkout).
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

        if falla == "postgres_antes_commit":
            raise OperationalError("COMMIT", {}, Exception("Falla simulada: se perdió la conexión con PostgreSQL"))

        # 4c. Clave de idempotencia apuntando al pedido.
        if clave_idempotencia:
            registro = db.session.get(CheckoutIdempotencia, clave_idempotencia)
            registro.id_pedido = id_pedido
            registro.referencia_pago = referencia_pago

        # 4d. Outbox: lo que hay que hacer en los otros motores tras confirmar.
        eventos = []
        for consumo in consumos:
            eventos.append(sincronizacion.registrar("confirmar_reserva_oferta", {
                "producto_id": consumo["producto_id"],
                "id_usuario": id_comprador,
                "id_oferta": consumo["id_oferta"],
            }, id_pedido))
        eventos.append(sincronizacion.registrar("limpiar_carrito", {
            "id_comprador": id_comprador,
            "lineas": crudo,
        }, id_pedido))
        for id_sql_origen in sorted({it["id_producto"] for it in items}):
            eventos.append(sincronizacion.registrar("stock_mongo", {"id_sql_origen": id_sql_origen}, id_pedido))
            eventos.append(sincronizacion.registrar("stock_elasticsearch", {"id_sql_origen": id_sql_origen}, id_pedido))

        db.session.commit()
    except OperationalError as e:
        # La base de datos no respondió o se cortó la conexión: no se confirmó
        # nada. Es un error de infraestructura (reintentable), no de negocio.
        db.session.rollback()
        _compensar_consumos(id_comprador, consumos)
        print(f"[checkout] ERROR: PostgreSQL no confirmó el pedido: {e}")
        return jsonify({
            "error": "No pudimos confirmar tu pago. No se realizó ningún cobro y tu carrito sigue intacto; intenta de nuevo.",
            "codigo": "PAGO_NO_CONFIRMADO",
        }), 503
    except DBAPIError as e:
        # Error de negocio levantado por el SP (stock insuficiente, dirección
        # ajena, producto inactivo...): el mensaje del SP es para el usuario.
        db.session.rollback()
        _compensar_consumos(id_comprador, consumos)
        diag = getattr(e.orig, "diag", None)
        mensaje_error = (diag.message_primary if diag else None) or str(e.orig).strip()
        return jsonify({"error": mensaje_error}), 400
    except Exception as e:
        db.session.rollback()
        _compensar_consumos(id_comprador, consumos)
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500

    # ---- 5. Pedido confirmado: sincronización inmediata (mejor esfuerzo) -----
    # Lo que falle aquí queda "pendiente" en el outbox y lo reintenta el relevo;
    # el pedido ya es válido y el cliente recibe 201 igual.
    ids_eventos = [e.id_evento for e in eventos]
    resumen = {"procesados": 0, "pendientes": len(ids_eventos)}
    try:
        resumen = sincronizacion.procesar(ids=ids_eventos, falla_simulada=falla)
        for err in resumen["errores"]:
            print(f"[checkout] ADVERTENCIA: pedido {id_pedido} confirmado; evento {err['id_evento']} "
                  f"({err['tipo']}) quedó pendiente: {err['error']}")
    except Exception as e:
        db.session.rollback()
        print(f"[checkout] ADVERTENCIA: pedido {id_pedido} confirmado, pero no se pudieron procesar sus "
              f"eventos de sincronización (los reintentará el relevo): {e}")

    pendientes = resumen.get("pendientes", 0) + resumen.get("fallidos", 0)
    return jsonify({
        "mensaje": mensaje,
        "id_pedido": id_pedido,
        "referencia_pago": referencia_pago,
        "sincronizacion_pendiente": pendientes > 0,
        "eventos_sincronizacion": {"procesados": resumen.get("procesados", 0), "pendientes": pendientes},
    }), 201
