from datetime import datetime

from flask import Blueprint, request, jsonify
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError

from ..extensions import col_productos, col_resenas, db, neo4j_driver, ZONA_GUATEMALA
from ..models import LineaPedido, Pedido

bp = Blueprint("resenas", __name__)

# ============================================================================
# MÓDULO DE RESEÑAS DE PRODUCTO (MONGODB + NEO4J - ENTREGA 2)
# ============================================================================
# Las reseñas se guardan en Mongo (col_resenas), igual que el resto del
# catálogo documental. Cada reseña exitosa se espeja además como una relación
# (:Cuenta)-[:CALIFICO]->(:Producto) en Neo4j, que alimentará la detección de
# fraude (tarea posterior). No hay 2PC entre Mongo y Neo4j: si Neo4j falla, la
# reseña en Mongo YA quedó confirmada y se responde 201 igual (mismo criterio
# que ya se usa entre Postgres y Mongo en catalogo.py) -- se pierde la
# sincronización con el grafo hasta un backfill manual, pero no se le niega al
# usuario su reseña ya persistida.

CALIFICACION_MIN = 1
CALIFICACION_MAX = 5
TEXTO_MAX_LONGITUD = 1000

# Índice único: una cuenta no puede reseñar el mismo producto dos veces.
# create_index es idempotente -- no falla si el índice ya existe.
col_resenas.create_index([("producto_id", 1), ("autor.id_usuario", 1)], unique=True)


def _es_entero(valor):
    return isinstance(valor, int) and not isinstance(valor, bool)


def _sincronizar_neo4j(*, id_usuario, nombre, rol, producto_id, nombre_producto, sku, calificacion, fecha, id_resena):
    """
    Espeja la reseña recién creada en Mongo como nodos/relación en Neo4j.
    Se llama DESPUÉS de que la reseña ya está confirmada en Mongo; si esto
    falla no se revierte nada (ver comentario del módulo) -- el caller debe
    capturar la excepción.
    """
    query = """
        MERGE (c:Cuenta {id_usuario: $id_usuario})
          SET c.nombre = $nombre, c.rol = $rol
        MERGE (p:Producto {id_producto: $producto_id})
          SET p.nombre = $nombre_producto, p.sku = $sku
        MERGE (c)-[r:CALIFICO]->(p)
          SET r.calificacion = $calificacion, r.fecha = $fecha, r.id_resena = $id_resena
    """
    with neo4j_driver.session() as session:
        session.run(
            query,
            id_usuario=id_usuario,
            nombre=nombre,
            rol=rol,
            producto_id=producto_id,
            nombre_producto=nombre_producto,
            sku=sku,
            calificacion=calificacion,
            fecha=fecha,
            id_resena=id_resena,
        )


@bp.route("/api/resenas", methods=["POST"])
def crear_resena():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "El cuerpo de la petición debe ser JSON válido"}), 400

    if data.get("rol_solicitante") != "comprador":
        return jsonify({"error": "Solo un comprador puede publicar reseñas"}), 403

    producto_id = data.get("producto_id")
    if not isinstance(producto_id, str) or not producto_id.strip():
        return jsonify({"error": "producto_id debe ser un string no vacío"}), 400

    id_usuario = data.get("id_usuario")
    if not _es_entero(id_usuario):
        return jsonify({"error": "id_usuario debe ser un entero"}), 400

    nombre_autor = (data.get("nombre_autor") or "").strip()
    if not nombre_autor:
        return jsonify({"error": "nombre_autor es obligatorio"}), 400

    calificacion = data.get("calificacion")
    if not _es_entero(calificacion) or not (CALIFICACION_MIN <= calificacion <= CALIFICACION_MAX):
        return jsonify({
            "error": f"calificacion debe ser un entero entre {CALIFICACION_MIN} y {CALIFICACION_MAX}"
        }), 400

    texto = (data.get("texto") or "").strip()
    if not texto:
        return jsonify({"error": "texto es obligatorio"}), 400
    if len(texto) > TEXTO_MAX_LONGITUD:
        return jsonify({"error": f"texto no puede superar {TEXTO_MAX_LONGITUD} caracteres"}), 400

    producto = col_productos.find_one({"_id": producto_id})
    if not producto:
        return jsonify({"error": "Producto no encontrado"}), 404

    now = datetime.now(ZONA_GUATEMALA)
    resena = {
        "producto_id": producto_id,
        "id_sql_origen_producto": producto.get("id_sql_origen"),
        "autor": {"id_usuario": id_usuario, "nombre": nombre_autor, "rol": "comprador"},
        "calificacion": calificacion,
        "texto": texto,
        "fecha_creacion": now,
    }

    try:
        resultado = col_resenas.insert_one(resena)
    except DuplicateKeyError:
        return jsonify({"error": "Ya reseñaste este producto"}), 409
    except Exception as e:
        return jsonify({"error": f"Error al guardar la reseña: {str(e)}"}), 500

    resena["_id"] = str(resultado.inserted_id)

    try:
        _sincronizar_neo4j(
            id_usuario=id_usuario,
            nombre=nombre_autor,
            rol="comprador",
            producto_id=producto_id,
            nombre_producto=producto.get("nombre"),
            sku=producto.get("sku"),
            calificacion=calificacion,
            fecha=now.isoformat(),
            id_resena=resena["_id"],
        )
    except Exception as e:
        # La reseña YA está confirmada en Mongo -- no se revierte. Solo se
        # loggea que el grafo de fraude quedó desincronizado (backfill manual
        # pendiente si esto llega a pasar).
        print(f"[resenas] ADVERTENCIA: no se pudo sincronizar la reseña {resena['_id']} a Neo4j: {e}")

    return jsonify({"mensaje": "Reseña publicada", "resena": resena}), 201


@bp.route("/api/resenas/<producto_id>", methods=["GET"])
def get_resenas_producto(producto_id):
    try:
        cursor = col_resenas.find({"producto_id": producto_id}).sort("fecha_creacion", DESCENDING)
        resenas = list(cursor)

        if not resenas:
            return jsonify({"resenas": [], "resumen": {"promedio": 0, "total": 0}})

        # Todas las reseñas de un mismo producto_id comparten el mismo
        # id_sql_origen_producto (se copia del documento Mongo al crearla);
        # basta con leerlo de la primera para no repetir la consulta.
        id_sql_origen_producto = resenas[0].get("id_sql_origen_producto")

        compradores_verificados = set()
        if id_sql_origen_producto is not None:
            filas = (
                db.session.query(Pedido.id_comprador)
                .join(LineaPedido, LineaPedido.id_pedido == Pedido.id_pedido)
                .filter(LineaPedido.id_producto == id_sql_origen_producto)
                .distinct()
                .all()
            )
            compradores_verificados = {id_comprador for (id_comprador,) in filas}

        resenas_out = []
        suma_calificaciones = 0
        for r in resenas:
            r["_id"] = str(r["_id"])
            r["verificada_compra"] = r.get("autor", {}).get("id_usuario") in compradores_verificados
            suma_calificaciones += r["calificacion"]
            resenas_out.append(r)

        total = len(resenas_out)
        promedio = round(suma_calificaciones / total, 2) if total else 0

        return jsonify({
            "resenas": resenas_out,
            "resumen": {"promedio": promedio, "total": total},
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500
