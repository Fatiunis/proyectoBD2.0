"""Acceso a Redis para las ofertas relámpago y sus reservas temporales.

Lo usan tres blueprints (ofertas, carrito y checkout), por eso vive fuera de
ellos: así ninguno importa a otro y no hay imports circulares.

Keys de una oferta (las cuatro primeras con TTL = duración de la oferta):
  - oferta:{pid}:stock    -> cupo SIN VENDER. No baja al reservar: solo baja
                             cuando un checkout consume la reserva.
  - oferta:{pid}:limite   -> límite original ("Quedan X de Y").
  - oferta:{pid}:precio   -> precio de oferta, fijo; solo se escribe al crear.
  - oferta:{pid}:id       -> id único de esta oferta concreta (ver crear_oferta.lua).
  - oferta:{pid}:reservas -> hash id_usuario -> reserva JSON. TTL = lo que
                             queda de la oferta + la duración de una reserva.

Contabilidad (para la oferta vigente):
  stock_restante      = cupo_sin_vender - reservas activas
  unidades_reservadas = reservas activas + reservas "en_pago"
  unidades_vendidas   = limite - cupo_sin_vender - reservas "en_pago"
  (las tres suman el límite).

Todo cambio de estado de una reserva se hace con un script Lua (EVALSHA), que
Redis ejecuta de forma atómica: no hay check-then-act en Python ni locks de
aplicación.
"""

import math
import os
import uuid
from datetime import datetime, timedelta

import redis

from .config import RESERVA_OFERTA_TTL_SEGUNDOS
from .extensions import redis_client, ZONA_GUATEMALA

PREFIJO_LINEA_OFERTA = "oferta:"

# Cuánto puede quedar una reserva en estado "en_pago" (consumida por un
# checkout que todavía no confirmó ni compensó). Solo importa si el proceso
# muere a mitad del checkout: pasado este margen la entrada se purga y sus
# unidades se quedan contadas como vendidas (opción conservadora: nunca
# sobreventa, a lo sumo alguna unidad sin vender).
MARGEN_PAGO_MS = 5 * 60 * 1000

_DIR_LUA = os.path.join(os.path.dirname(__file__), "lua")
_SCRIPTS = {}


def _script(nombre):
    if nombre not in _SCRIPTS:
        with open(os.path.join(_DIR_LUA, f"{nombre}.lua"), "r", encoding="utf-8") as f:
            _SCRIPTS[nombre] = {"codigo": f.read(), "sha": None}
    return _SCRIPTS[nombre]


def _ejecutar(nombre, keys, args):
    # script_load + evalsha. El script se carga en Redis la primera vez que se
    # usa (no al importar: así el servidor arranca aunque Redis esté caído, y
    # las rutas de Redis responden 500 hasta que vuelva). Si Redis perdió la
    # caché de scripts (reinicio, SCRIPT FLUSH) se recarga y se reintenta.
    s = _script(nombre)
    if s["sha"] is None:
        s["sha"] = redis_client.script_load(s["codigo"])
    try:
        return redis_client.evalsha(s["sha"], len(keys), *keys, *args)
    except redis.exceptions.NoScriptError:
        s["sha"] = redis_client.script_load(s["codigo"])
        return redis_client.evalsha(s["sha"], len(keys), *keys, *args)


# ---------------------------------------------------------------- keys


def clave_stock(pid):
    return f"oferta:{pid}:stock"


def clave_limite(pid):
    return f"oferta:{pid}:limite"


def clave_precio(pid):
    return f"oferta:{pid}:precio"


def clave_id(pid):
    return f"oferta:{pid}:id"


def clave_reservas(pid):
    return f"oferta:{pid}:reservas"


def claves_oferta(pid):
    return [clave_stock(pid), clave_limite(pid), clave_precio(pid), clave_id(pid), clave_reservas(pid)]


def campo_linea_oferta(pid):
    """Campo del hash del carrito para la línea de oferta de un producto."""
    return f"{PREFIJO_LINEA_OFERTA}{pid}"


def producto_de_campo(campo):
    """'oferta:PROD-0001' -> 'PROD-0001'; None si es una línea normal."""
    if campo.startswith(PREFIJO_LINEA_OFERTA):
        return campo[len(PREFIJO_LINEA_OFERTA):]
    return None


# ---------------------------------------------------------------- utilidades


def segundos_desde_ms(ms):
    return max(0, math.ceil(ms / 1000))


def iso_en_ms(ms):
    fin = datetime.now(ZONA_GUATEMALA) + timedelta(milliseconds=ms)
    return fin.replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- operaciones


def crear(pid, cantidad_limite, precio_str, segundos):
    """True si creó la oferta, False si ya había una activa."""
    creada = _ejecutar(
        "crear_oferta",
        [clave_stock(pid), clave_limite(pid), clave_precio(pid), clave_id(pid)],
        [cantidad_limite, precio_str, segundos, uuid.uuid4().hex],
    )
    return creada == 1


def finalizar(pid):
    redis_client.delete(*claves_oferta(pid))


def reservar(pid, id_usuario, cantidad):
    """Devuelve (codigo, datos). codigo: 'ok', 'sin_oferta', 'sin_stock', 'duplicada'."""
    r = _ejecutar(
        "reservar_oferta",
        [clave_stock(pid), clave_precio(pid), clave_id(pid), clave_reservas(pid)],
        [id_usuario, cantidad, RESERVA_OFERTA_TTL_SEGUNDOS * 1000],
    )
    codigo = int(r[0])
    if codigo == -1:
        return "sin_oferta", None
    if codigo == -2:
        return "sin_stock", None
    if codigo == -3:
        return "duplicada", None
    return "ok", {"stock_restante": int(r[1]), "precio_oferta": r[2], "ms_restantes": int(r[3])}


def consultar(pid, id_usuario=None):
    """None si no hay oferta activa; si no, dict con la contabilidad de la oferta."""
    r = _ejecutar(
        "consultar_oferta",
        claves_oferta(pid),
        ["" if id_usuario is None else str(id_usuario)],
    )
    if int(r[0]) == -1:
        return None
    cupo_sin_vender = int(r[1])
    limite = int(r[2]) if r[2] != "" else None
    activas = int(r[5])
    en_pago = int(r[6])
    reserva_usuario = None
    if int(r[7]) > 0:
        reserva_usuario = {
            "cantidad": int(r[7]),
            "precio_oferta": float(r[8]),
            "segundos_restantes": segundos_desde_ms(int(r[9])),
        }
    return {
        "cupo_sin_vender": cupo_sin_vender,
        "limite": limite,
        "precio_oferta": float(r[3]) if r[3] != "" else None,
        "ttl_ms": int(r[4]),
        "stock_restante": max(0, cupo_sin_vender - activas),
        "unidades_reservadas": activas + en_pago,
        "unidades_vendidas": (limite - cupo_sin_vender - en_pago) if limite is not None else None,
        "reserva_usuario": reserva_usuario,
    }


def estado_linea(pid, id_usuario, clave_carrito):
    """Estado de la reserva de una línea de oferta del carrito. Si venció o no
    existe, la línea se quita del carrito (atómicamente) y devuelve None."""
    r = _ejecutar(
        "estado_linea_oferta",
        [clave_reservas(pid), clave_carrito],
        [str(id_usuario), campo_linea_oferta(pid)],
    )
    if int(r[0]) == 0:
        return None
    return {"estado": r[1], "cantidad": int(r[2]), "precio_oferta": float(r[3]), "ms_restantes": int(r[4])}


def liberar(pid, id_usuario, clave_carrito):
    """Quita la línea de oferta del carrito y libera la reserva activa."""
    return _ejecutar(
        "liberar_reserva_oferta",
        [clave_reservas(pid), clave_carrito],
        [str(id_usuario), campo_linea_oferta(pid)],
    ) == 1


def consumir(pid, id_usuario):
    """Devuelve (codigo, consumo). codigo: 'ok', 'expirada', 'en_pago'."""
    r = _ejecutar(
        "consumir_reserva_oferta",
        [clave_stock(pid), clave_id(pid), clave_reservas(pid)],
        [str(id_usuario), MARGEN_PAGO_MS],
    )
    codigo = int(r[0])
    if codigo == -1:
        return "expirada", None
    if codigo == -2:
        return "en_pago", None
    return "ok", {
        "producto_id": pid,
        "cantidad": int(r[1]),
        "precio_oferta": r[2],
        "vence_ms": int(r[3]),
        "id_oferta": r[4],
        "descontado": int(r[5]),
    }


def compensar(id_usuario, consumo):
    pid = consumo["producto_id"]
    return _ejecutar(
        "compensar_reserva_oferta",
        [clave_stock(pid), clave_id(pid), clave_reservas(pid)],
        [str(id_usuario), consumo["cantidad"], consumo["id_oferta"], consumo["descontado"]],
    ) == 1


def confirmar(id_usuario, consumo):
    pid = consumo["producto_id"]
    return _ejecutar(
        "confirmar_reserva_oferta",
        [clave_reservas(pid)],
        [str(id_usuario), consumo["id_oferta"]],
    ) == 1
