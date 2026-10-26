from flask import Blueprint, request, jsonify
from sqlalchemy.exc import OperationalError, ProgrammingError

from .. import vectores
from ..extensions import col_productos

bp = Blueprint("recomendaciones", __name__)

# ============================================================================
# RECOMENDACIÓN Y BÚSQUEDA SEMÁNTICA (PGVECTOR - ENTREGA FINAL)
# ============================================================================
# pgvector solo devuelve ids de producto y su similitud; los datos que se
# muestran (nombre, precio, imagen...) se leen de MongoDB, la fuente de verdad
# del catálogo, en el orden que dio pgvector. Si el componente vectorial no
# responde se devuelve 503 con codigo VECTORES_NO_DISPONIBLE: el frontend
# simplemente oculta la sección de recomendaciones (es una ayuda, no una
# función crítica del portal).

MAX_LIMITE = 24
MAX_LARGO_CONSULTA = 200

PROYECCION_TARJETA = {
    "_id": 1, "sku": 1, "nombre": 1, "precio_base": 1, "categoria": 1,
    "atributos": 1, "imagenes": 1, "vendedor": 1, "activo": 1,
}


def _limite(defecto):
    try:
        return min(max(int(request.args.get("limite", defecto)), 1), MAX_LIMITE)
    except ValueError:
        return defecto


def _no_disponible(e):
    print(f"[recomendaciones] ADVERTENCIA: componente vectorial no disponible: {type(e).__name__}: {e}")
    return jsonify({
        "error": "Las recomendaciones no están disponibles en este momento.",
        "codigo": "VECTORES_NO_DISPONIBLE",
    }), 503


def _hidratar(pares):
    """[(producto_id, similitud)] -> tarjetas de producto desde Mongo, en el
    mismo orden. Un producto que pgvector todavía cree activo pero en Mongo ya
    está inactivo (o borrado) se salta: manda Mongo."""
    if not pares:
        return []
    docs = {
        d["_id"]: d
        for d in col_productos.find({"_id": {"$in": [pid for pid, _ in pares]}, "activo": True}, PROYECCION_TARJETA)
    }
    items = []
    for pid, similitud in pares:
        d = docs.get(pid)
        if d is None:
            continue
        d["_id"] = str(d["_id"])
        d["similitud"] = round(similitud, 4)
        items.append(d)
    return items


@bp.route("/api/productos/<producto_id>/relacionados", methods=["GET"])
def productos_relacionados(producto_id):
    """Productos parecidos por el significado de su nombre y descripción.

    ?limite=6               cuántos devolver (1..24)
    ?misma_categoria=1      restringe a la categoría del producto
    ?diversificar=0         no descarta variantes casi idénticas (por defecto sí)
    """
    limite = _limite(6)
    misma_categoria = request.args.get("misma_categoria") in ("1", "true")
    diversificar = request.args.get("diversificar") not in ("0", "false")
    try:
        # Se piden algunos de más por si Mongo descarta alguno inactivo.
        pares = vectores.relacionados(
            producto_id, limite + 4, misma_categoria=misma_categoria, diversificar=diversificar
        )
    except (OperationalError, ProgrammingError) as e:
        return _no_disponible(e)
    if pares is None:
        if col_productos.count_documents({"_id": producto_id}, limit=1) == 0:
            return jsonify({"error": "Producto no encontrado"}), 404
        # Existe en el catálogo pero aún no tiene embedding (p. ej. recién
        # creado con pgvector caído): sin recomendaciones, sin error.
        return jsonify({"producto_id": producto_id, "items": [], "sin_embedding": True}), 200
    return jsonify({"producto_id": producto_id, "items": _hidratar(pares)[:limite]}), 200


@bp.route("/api/busqueda/semantica", methods=["GET"])
def busqueda_semantica():
    """Búsqueda por significado: "algo para correr en la mañana" encuentra
    tenis y ropa deportiva aunque ninguna palabra coincida.

    ?q=texto  ?limite=12  ?categoria_id=N
    """
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "Falta el texto a buscar (q)."}), 400
    if len(q) > MAX_LARGO_CONSULTA:
        return jsonify({"error": f"La búsqueda no puede pasar de {MAX_LARGO_CONSULTA} caracteres."}), 400
    limite = _limite(12)
    try:
        id_categoria = int(request.args["categoria_id"]) if request.args.get("categoria_id") else None
    except ValueError:
        return jsonify({"error": "'categoria_id' debe ser un número entero"}), 400
    try:
        pares = vectores.buscar(q, limite + 4, id_categoria=id_categoria)
    except (OperationalError, ProgrammingError) as e:
        return _no_disponible(e)
    return jsonify({"q": q, "items": _hidratar(pares)[:limite]}), 200


@bp.route("/api/vectores/estado", methods=["GET"])
def estado_vectores():
    """Cuántos productos tienen embedding frente al catálogo (panel admin)."""
    try:
        e = vectores.estado()
    except (OperationalError, ProgrammingError) as ex:
        return _no_disponible(ex)
    e["productos_catalogo"] = col_productos.count_documents({})
    e["productos_activos_catalogo"] = col_productos.count_documents({"activo": True})
    return jsonify(e), 200
