"""Outbox transaccional del checkout y su proceso de relevo (Entrega 3).

Problema: tras confirmar un pedido en PostgreSQL quedan cosas por hacer en
otros motores (cerrar la reserva de oferta y limpiar el carrito en Redis,
copiar el stock final a MongoDB y a Elasticsearch). Esos motores pueden fallar
justo en ese momento, y no hay transacción distribuida (2PC) entre ellos.

Solución: el checkout inserta un evento por cada una de esas tareas en la
tabla eventos_sincronizacion, DENTRO de la misma transacción que el pedido.
Si el pedido se confirma, sus eventos también (y si se revierte, también se
revierten). Después del COMMIT se intenta ejecutarlos de inmediato; lo que
falle queda "pendiente" y este módulo lo reintenta con espera creciente.

Cada tipo de evento es IDEMPOTENTE, así que ejecutarlo dos veces (por un
reintento, o porque dos relevos lo tomaron) no cambia el resultado:
  - stock_mongo / stock_elasticsearch: FIJAN el stock al valor actual de
    inventario en PostgreSQL (fuente de verdad), leído al ejecutar el evento.
    No restan nada, así que repetir o desordenar eventos da el mismo valor.
  - confirmar_reserva_oferta: el script Lua solo borra la reserva si sigue
    "en_pago" de esa oferta; si ya no está, no hace nada.
  - limpiar_carrito: solo borra una línea si su valor sigue igual al pagado.
  - indexar_producto: reemplaza el documento entero (mismo _id) con el que
    está hoy en MongoDB.

Ventana de consistencia: entre el COMMIT y la ejecución exitosa del evento,
el catálogo (Mongo/Elasticsearch) puede mostrar un stock viejo y el carrito
puede seguir mostrando lo ya comprado. El checkout NUNCA vende de más en esa
ventana, porque valida el stock contra PostgreSQL.
"""

import os
import threading
import time
from datetime import datetime, timedelta

from .config import OUTBOX_INTERVALO_SEGUNDOS, OUTBOX_MAX_INTENTOS
from .extensions import db, redis_client, col_productos, ZONA_GUATEMALA
from .models import EventoSincronizacion, Inventario
from . import busqueda_es, ofertas_redis

TIPOS = (
    "confirmar_reserva_oferta",
    "limpiar_carrito",
    "stock_mongo",
    "stock_elasticsearch",
    "indexar_producto",
)

ESPERA_BASE_SEGUNDOS = 5
ESPERA_MAXIMA_SEGUNDOS = 300

with open(os.path.join(os.path.dirname(__file__), "lua", "limpiar_carrito_comprado.lua"), "r", encoding="utf-8") as _f:
    # register_script usa EVALSHA y recarga el script solo si Redis lo perdió.
    _limpiar_carrito_lua = redis_client.register_script(_f.read())


class FallaSimulada(Exception):
    """Falla inyectada a propósito para la prueba de falla (ver checkout.py)."""


# Qué tipos de evento "rompe" cada punto de falla simulada posterior al COMMIT.
TIPOS_AFECTADOS_POR_FALLA = {
    "redis_post_commit": ("confirmar_reserva_oferta", "limpiar_carrito"),
    "mongo_post_commit": ("stock_mongo",),
    "elasticsearch_post_commit": ("stock_elasticsearch",),
}


def _ahora():
    return datetime.now(ZONA_GUATEMALA)


def _espera(intentos):
    """Espera exponencial: 5 s, 10 s, 20 s, 40 s... hasta 5 minutos."""
    return timedelta(seconds=min(ESPERA_BASE_SEGUNDOS * 2 ** (intentos - 1), ESPERA_MAXIMA_SEGUNDOS))


# ---------------------------------------------------------------- registro


def registrar(tipo, payload, id_pedido=None):
    """Agrega un evento a la sesión actual SIN hacer commit: quien llama decide
    la transacción (en el checkout, la misma del pedido)."""
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de evento desconocido: {tipo}")
    evento = EventoSincronizacion(tipo=tipo, payload=payload, id_pedido=id_pedido)
    db.session.add(evento)
    return evento


# ---------------------------------------------------------------- ejecución


def _stock_actual(id_sql_origen):
    fila = db.session.query(Inventario.stock_disponible).filter_by(id_producto=id_sql_origen).first()
    if fila is None:
        raise LookupError(f"No existe inventario en PostgreSQL para el producto {id_sql_origen}")
    return fila[0]


def _ejecutar(evento):
    p = evento.payload
    if evento.tipo == "confirmar_reserva_oferta":
        ofertas_redis.confirmar(p["id_usuario"], {"producto_id": p["producto_id"], "id_oferta": p["id_oferta"]})
    elif evento.tipo == "limpiar_carrito":
        pares = [x for campo, valor in p["lineas"].items() for x in (campo, valor)]
        if pares:
            _limpiar_carrito_lua(keys=[f"carrito:{p['id_comprador']}"], args=pares)
    elif evento.tipo == "stock_mongo":
        stock = _stock_actual(p["id_sql_origen"])
        col_productos.update_one({"id_sql_origen": p["id_sql_origen"]}, {"$set": {"stock_disponible": stock}})
    elif evento.tipo == "stock_elasticsearch":
        busqueda_es.actualizar_stock(p["id_sql_origen"], _stock_actual(p["id_sql_origen"]))
    elif evento.tipo == "indexar_producto":
        doc = col_productos.find_one({"_id": p["producto_id"]})
        if doc is not None:
            busqueda_es.indexar_producto(doc)
    else:
        raise ValueError(f"Tipo de evento desconocido: {evento.tipo}")


def procesar(ids=None, limite=100, falla_simulada=None):
    """Ejecuta eventos pendientes y guarda el resultado de cada uno.

    ids: solo esos eventos (el checkout los procesa apenas confirma el pedido);
         si no se indica, todos los pendientes cuyo próximo intento ya llegó.
    falla_simulada: punto de falla de la prueba (solo desde el checkout).

    Los eventos se toman con SELECT ... FOR UPDATE SKIP LOCKED: si dos relevos
    corren a la vez (el hilo de fondo y un checkout), cada evento lo procesa
    uno solo. Aunque no fuera así, los eventos son idempotentes.

    Devuelve {"procesados": n, "pendientes": n, "fallidos": n, "errores": [...]}.
    """
    consulta = db.session.query(EventoSincronizacion).filter(EventoSincronizacion.estado == "pendiente")
    if ids is not None:
        if not ids:
            return {"procesados": 0, "pendientes": 0, "fallidos": 0, "errores": []}
        consulta = consulta.filter(EventoSincronizacion.id_evento.in_(ids))
    else:
        consulta = consulta.filter(EventoSincronizacion.proximo_intento <= _ahora())
    eventos = (
        consulta.order_by(EventoSincronizacion.id_evento)
        .limit(limite)
        .with_for_update(skip_locked=True)
        .all()
    )

    resumen = {"procesados": 0, "pendientes": 0, "fallidos": 0, "errores": []}
    tipos_rotos = TIPOS_AFECTADOS_POR_FALLA.get(falla_simulada, ())
    for evento in eventos:
        evento.intentos += 1
        try:
            if evento.tipo in tipos_rotos:
                raise FallaSimulada(f"Falla simulada ({falla_simulada}): el motor no respondió")
            _ejecutar(evento)
            evento.estado = "procesado"
            evento.procesado_en = _ahora()
            # ultimo_error se conserva: un evento procesado en el 2.º intento
            # sigue mostrando por qué falló el primero.
            resumen["procesados"] += 1
        except Exception as e:
            evento.ultimo_error = f"{type(e).__name__}: {e}"[:1000]
            if evento.intentos >= OUTBOX_MAX_INTENTOS:
                evento.estado = "fallido"
                resumen["fallidos"] += 1
            else:
                evento.proximo_intento = _ahora() + _espera(evento.intentos)
                resumen["pendientes"] += 1
            resumen["errores"].append({"id_evento": evento.id_evento, "tipo": evento.tipo,
                                       "error": evento.ultimo_error})
    db.session.commit()
    return resumen


# ---------------------------------------------------------------- relevo


def iniciar_relevo(app):
    """Hilo de fondo que reintenta los eventos pendientes cada
    OUTBOX_INTERVALO_SEGUNDOS. Se arranca una sola vez desde backend/main.py."""

    def bucle():
        while True:
            time.sleep(OUTBOX_INTERVALO_SEGUNDOS)
            with app.app_context():
                try:
                    r = procesar()
                    if r["procesados"] or r["fallidos"] or r["errores"]:
                        print(f"[relevo] procesados={r['procesados']} pendientes={r['pendientes']} "
                              f"fallidos={r['fallidos']}")
                except Exception as e:
                    db.session.rollback()
                    print(f"[relevo] ADVERTENCIA: no se pudieron procesar los eventos pendientes: {e}")
                finally:
                    db.session.remove()

    hilo = threading.Thread(target=bucle, name="relevo-outbox", daemon=True)
    hilo.start()
    print(f"[relevo] Relevo de eventos de sincronización activo (cada {OUTBOX_INTERVALO_SEGUNDOS} s).")
    return hilo
