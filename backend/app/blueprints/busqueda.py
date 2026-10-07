from elastic_transport import ConnectionError as ESConnectionError, ConnectionTimeout as ESConnectionTimeout
import math

from elasticsearch import ApiError, NotFoundError
from flask import Blueprint, request, jsonify

from .. import busqueda_es

bp = Blueprint("busqueda", __name__)

# ============================================================================
# BUSCADOR DEL CATÁLOGO (ELASTICSEARCH - ENTREGA 3)
# ============================================================================
# El índice es una proyección de solo lectura de la colección Mongo
# "productos" (ver app/busqueda_es.py). Si Elasticsearch no está disponible se
# responde 503 con codigo BUSCADOR_NO_DISPONIBLE: el frontend entonces repite
# la búsqueda contra GET /api/productos?q= (índice de texto de Mongo, sin
# tolerancia a errores ni facetas) y se lo avisa al usuario. Buscar es una
# lectura: degradarse a una búsqueda más simple es mejor que no buscar.

MAX_LARGO_CONSULTA = 200

_ERRORES_MOTOR = (ESConnectionError, ESConnectionTimeout, ApiError)


def _es_error_de_solicitud(e):
    """True si Elasticsearch respondió y rechazó la consulta (400): el motor
    está arriba y caer al respaldo de Mongo no tiene sentido. El resto
    (conexión, timeout, 404 del índice/alias, 401/403, 429, 5xx) se trata como
    buscador no disponible."""
    return isinstance(e, ApiError) and getattr(e, "status_code", None) == 400


def _error_motor(e):
    if _es_error_de_solicitud(e):
        print(f"[busqueda] ADVERTENCIA: Elasticsearch rechazó la consulta: {e}")
        return jsonify({
            "error": "La búsqueda no es válida.",
            "codigo": "BUSQUEDA_NO_VALIDA",
        }), 400
    return _no_disponible(e)


def _no_disponible(e):
    detalle = "índice de productos no encontrado" if isinstance(e, NotFoundError) else type(e).__name__
    print(f"[busqueda] ADVERTENCIA: Elasticsearch no disponible ({detalle}): {e}")
    return jsonify({
        "error": "El buscador no está disponible en este momento.",
        "codigo": "BUSCADOR_NO_DISPONIBLE",
    }), 503


def _entero(nombre, minimo=None, maximo=None, defecto=None):
    valor = request.args.get(nombre)
    if valor in (None, ""):
        return defecto
    try:
        n = int(valor)
    except ValueError:
        raise ValueError(f"'{nombre}' debe ser un número entero")
    if minimo is not None:
        n = max(n, minimo)
    if maximo is not None:
        n = min(n, maximo)
    return n


def _decimal(nombre):
    valor = request.args.get(nombre)
    if valor in (None, ""):
        return None
    try:
        n = float(valor)
    except ValueError:
        raise ValueError(f"'{nombre}' debe ser un número")
    if not math.isfinite(n):
        raise ValueError(f"'{nombre}' debe ser un número finito")
    if n < 0:
        raise ValueError(f"'{nombre}' no puede ser negativo")
    return n


@bp.route("/api/busqueda", methods=["GET"])
def buscar_productos():
    """
    Búsqueda de texto libre con tolerancia a errores, relevancia y facetas.

    Parámetros (query string):
      q            texto a buscar (obligatorio, máx. 200 caracteres)
      categoria_id, marca, vendedor_id, precio_min, precio_max   filtros de faceta
      orden        relevancia (defecto) | precio_asc | precio_desc
      pagina, por_pagina   (24 por defecto, máximo 100)

    Respuesta: {items, total, pagina, por_pagina, total_paginas,
                facetas: {categorias, marcas, tiendas, precios},
                sugerencia, motor: "elasticsearch"}
    """
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "El parámetro 'q' es obligatorio"}), 400
    if len(q) > MAX_LARGO_CONSULTA:
        return jsonify({"error": f"La búsqueda no puede superar {MAX_LARGO_CONSULTA} caracteres"}), 400

    orden = request.args.get("orden") or "relevancia"
    if orden not in busqueda_es.ORDENES:
        return jsonify({"error": f"orden debe ser uno de: {', '.join(busqueda_es.ORDENES)}"}), 400

    try:
        params = {
            "q": q,
            "orden": orden,
            "categoria_id": _entero("categoria_id"),
            "vendedor_id": _entero("vendedor_id"),
            "marca": (request.args.get("marca") or "").strip() or None,
            "precio_min": _decimal("precio_min"),
            "precio_max": _decimal("precio_max"),
            "pagina": _entero("pagina", minimo=1, defecto=1),
            "por_pagina": _entero("por_pagina", minimo=1, maximo=busqueda_es.POR_PAGINA_MAXIMO,
                                  defecto=busqueda_es.POR_PAGINA_DEFECTO),
        }
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        return jsonify(busqueda_es.buscar(params))
    except _ERRORES_MOTOR as e:
        return _error_motor(e)


@bp.route("/api/busqueda/autocompletar", methods=["GET"])
def autocompletar_productos():
    """Sugerencias de producto mientras se escribe (mínimo 2 caracteres)."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    if len(q) > MAX_LARGO_CONSULTA:
        return jsonify({"error": f"La búsqueda no puede superar {MAX_LARGO_CONSULTA} caracteres"}), 400
    try:
        return jsonify(busqueda_es.autocompletar(q))
    except _ERRORES_MOTOR as e:
        return _error_motor(e)
