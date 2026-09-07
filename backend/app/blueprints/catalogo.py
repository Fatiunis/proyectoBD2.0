from datetime import datetime

from flask import Blueprint, request, jsonify
from pymongo import ASCENDING
from sqlalchemy.exc import IntegrityError

from ..extensions import db, col_productos, col_historial, ZONA_GUATEMALA
from ..models import Categoria, Producto, Inventario

bp = Blueprint("catalogo", __name__)

# ============================================================================
# MÓDULO DE CATÁLOGO & HISTORIAL (MONGODB - ENTREGA 1)
# ============================================================================

@bp.route("/api/categorias", methods=["GET"])
def get_categorias():
    """
    Fuente de verdad: PostgreSQL (tabla "categorias"), no una agregación sobre
    los productos de Mongo. Así una categoría recién creada por el administrador
    aparece de inmediato en el catálogo y en el formulario de alta de producto,
    aunque todavía no tenga ningún producto asociado.
    """
    try:
        categorias = (
            db.session.query(Categoria)
            .order_by(Categoria.nombre_categoria)
            .all()
        )
        return jsonify([
            {
                "id_categoria": c.id_categoria,
                "nombre": c.nombre_categoria,
                "descripcion": c.descripcion,
                "id_categoria_padre": c.id_categoria_padre,
                "esquema_atributos": c.esquema_atributos,
            }
            for c in categorias
        ])
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


@bp.route("/api/categorias", methods=["POST"])
def crear_categoria():
    data = request.get_json() or {}

    if data.get("rol_solicitante") != "administrador":
        return jsonify({"error": "Solo un administrador puede crear categorías."}), 403

    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"error": "El nombre de la categoría es obligatorio"}), 400

    descripcion = data.get("descripcion", "")
    id_categoria_padre = data.get("id_categoria_padre") or None
    esquema_atributos = data.get("esquema_atributos", [])

    if not isinstance(esquema_atributos, list) or any(
        not isinstance(a, dict) or not a.get("clave") or not a.get("etiqueta") or a.get("tipo") not in ["texto", "numero"]
        for a in esquema_atributos
    ):
        return jsonify({"error": "esquema_atributos inválido: cada atributo necesita clave, etiqueta y tipo ('texto' o 'numero')"}), 400

    try:
        if db.session.query(Categoria.id_categoria).filter_by(nombre_categoria=nombre).first():
            return jsonify({"error": "Ya existe una categoría con ese nombre"}), 409

        nueva = Categoria(
            nombre_categoria=nombre,
            descripcion=descripcion,
            id_categoria_padre=id_categoria_padre,
            esquema_atributos=esquema_atributos,
        )
        db.session.add(nueva)
        db.session.commit()

        categoria_dict = {
            "id_categoria": nueva.id_categoria,
            "nombre": nueva.nombre_categoria,
            "descripcion": nueva.descripcion,
            "id_categoria_padre": nueva.id_categoria_padre,
            "esquema_atributos": nueva.esquema_atributos,
        }
        return jsonify({"mensaje": "Categoría creada con éxito", "categoria": categoria_dict}), 201
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({"error": str(e.orig).strip()}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


@bp.route("/api/categorias/<int:id_categoria>/filtros", methods=["GET"])
def get_filtros_categoria(id_categoria):
    """
    Descubre, a partir de los documentos reales, qué atributos son relevantes
    para filtrar dentro de una categoría (en vez de mantener una lista fija por
    categoría en el backend o el frontend). Usa $objectToArray + $unwind + $group
    para aplanar el objeto "atributos" -que varía de forma libre por documento- y
    reunir, por cada clave encontrada, todos los valores usados en la categoría.
    """
    pipeline = [
        {"$match": {"categoria.id_categoria": id_categoria, "activo": True}},
        {"$project": {"pares": {"$objectToArray": "$atributos"}}},
        {"$unwind": "$pares"},
        {"$group": {"_id": "$pares.k", "valores": {"$push": "$pares.v"}}}
    ]
    grupos = list(col_productos.aggregate(pipeline))

    filtros = []
    for g in grupos:
        clave = g["_id"]
        valores = g["valores"]

        # Los atributos de tipo lista (ej. "puertos") no son filtros directos; se descartan.
        if any(isinstance(v, list) for v in valores):
            continue

        es_numerico = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in valores)
        if es_numerico:
            # Si todos los productos comparten el mismo valor, el rango no discrimina nada; se descarta.
            if min(valores) != max(valores):
                filtros.append({
                    "clave": clave,
                    "tipo": "rango",
                    "min": min(valores),
                    "max": max(valores)
                })
            continue

        # Un atributo de texto solo sirve como filtro de selección si aparece con
        # más de un valor distinto entre productos (ej. "talla", "color"); si es
        # constante o todos los valores son únicos (ej. una descripción libre),
        # no aporta como filtro y se descarta.
        valores_texto = [str(v) for v in valores]
        distintos = sorted(set(valores_texto))
        if 2 <= len(distintos) < len(valores_texto):
            filtros.append({
                "clave": clave,
                "tipo": "seleccion",
                "valores": distintos
            })

    filtros.sort(key=lambda f: f["clave"])
    return jsonify(filtros)


@bp.route("/api/productos", methods=["GET"])
def get_productos():
    cat_id = request.args.get("categoria_id")
    vendedor_id = request.args.get("vendedor_id")
    texto_busqueda = (request.args.get("q") or "").strip()
    query = {"activo": True}
    if texto_busqueda:
        # Búsqueda de texto real de MongoDB (stemming en español + relevancia), no un
        # simple $regex — sobre idx_texto_busqueda (nombre, descripcion, sku). No sustituye
        # al motor de búsqueda dedicado (Elasticsearch/OpenSearch) de la Entrega 3 -- no hay
        # tolerancia a errores ortográficos ni autocompletado -- pero ya facilita encontrar
        # un producto por palabra suelta a medida que el catálogo crece.
        query["$text"] = {"$search": texto_busqueda, "$language": "es"}
    if cat_id:
        try:
            query["categoria.id_categoria"] = int(cat_id)
        except ValueError:
            pass
    if vendedor_id:
        try:
            query["vendedor.id_vendedor"] = int(vendedor_id)
        except ValueError:
            pass

    # Filtros dinámicos por atributo, según el esquema descubierto en /categorias/<id>/filtros:
    #   atributo_<clave>=valor           -> coincidencia exacta (atributos categóricos)
    #   atributo_<clave>_min / _max      -> rango numérico (atributos numéricos)
    condiciones_rango = {}
    for arg, valor in request.args.items():
        if not arg.startswith("atributo_") or not valor:
            continue
        nombre = arg[len("atributo_"):]

        if nombre.endswith("_min") or nombre.endswith("_max"):
            clave = nombre[:-4]
            operador = "$gte" if nombre.endswith("_min") else "$lte"
            try:
                condiciones_rango.setdefault(clave, {})[operador] = float(valor)
            except ValueError:
                pass
        else:
            query[f"atributos.{nombre}"] = valor

    for clave, condicion in condiciones_rango.items():
        query[f"atributos.{clave}"] = condicion

    proyeccion = {"_id": 1, "sku": 1, "nombre": 1, "precio_base": 1, "categoria": 1, "atributos": 1, "imagenes": 1, "vendedor": 1}

    if texto_busqueda:
        proyeccion["relevancia"] = {"$meta": "textScore"}
        cursor = col_productos.find(query, proyeccion).sort([("relevancia", {"$meta": "textScore"})])
    else:
        cursor = col_productos.find(query, proyeccion).sort("precio_base", ASCENDING)

    docs = list(cursor)

    for d in docs:
        d["_id"] = str(d["_id"])
    return jsonify(docs)


@bp.route("/api/productos/<producto_id>", methods=["GET"])
def get_producto_detalle(producto_id):
    doc = col_productos.find_one({"_id": producto_id})
    if not doc:
        return jsonify({"error": "Producto no encontrado"}), 404
    doc["_id"] = str(doc["_id"])
    return jsonify(doc)


@bp.route("/api/productos", methods=["POST"])
def crear_o_actualizar_producto():
    """
    Alta/edición de producto (upsert por SKU contra MongoDB).

    F1: cuando el producto es NUEVO (no existe todavía por SKU), además de
    escribir el documento en Mongo se crean las filas correspondientes en
    PostgreSQL ("productos" + "inventario", ver database/postgres/ddl_tiendaya.sql)
    usando los modelos SQLAlchemy. El "id_producto" resultante se guarda como
    "id_sql_origen" en el documento Mongo -- ese es el campo que el carrito y
    el checkout (sp_procesar_checkout, que opera SOLO sobre Postgres) necesitan
    para poder comprar el producto. Sin esto, un producto nuevo nunca podía
    completar un checkout.

    Orden de escritura (decisión explícita): primero se intenta el INSERT en
    Postgres y se hace commit; recién si eso tiene éxito se escribe el
    documento en Mongo. Si el INSERT en Postgres falla, se hace
    db.session.rollback() y se responde error sin tocar Mongo -- así nunca
    queda un documento Mongo "a medias" sin vínculo a Postgres. La contrapartida
    (aceptada para el alcance de este curso, sin 2PC) es que, si Postgres
    confirma pero la escritura a Mongo fallara justo después, quedaría una fila
    huérfana en productos/inventario sin documento Mongo asociado -- caso de
    borde no manejado, ya que ese fallo puntual (red/Mongo caído justo después
    de un commit exitoso en Postgres) no tiene forma de revertirse sin 2PC.

    Cuando el producto YA EXISTE (edición, con id_sql_origen ya presente), NO
    se vuelve a tocar Postgres: la limitación conocida de que el checkout usa
    precio/stock de Postgres y no de Mongo sigue igual (ver docs/STACK.md),
    fuera de alcance de este fix.

    F2: en edición se hace MERGE sobre el documento existente -- solo se
    sobrescriben los campos que efectivamente vienen en el payload; los que no
    vienen (imagenes, atributos, categoria, etc.) conservan su valor actual en
    Mongo en vez de resetearse a un default. Los defaults (imagenes: [], etc.)
    solo aplican al dar de alta un producto nuevo.
    """
    data = request.get_json()
    if not data or "sku" not in data:
        return jsonify({"error": "Datos inválidos"}), 400

    existente = col_productos.find_one({"sku": data["sku"]})
    es_nuevo = existente is None

    rol_solicitante = data.get("rol_solicitante")
    id_vendedor_solicitante = data.get("id_vendedor")
    if existente and rol_solicitante != "administrador":
        id_vendedor_actual = existente.get("vendedor", {}).get("id_vendedor")
        if id_vendedor_actual != id_vendedor_solicitante:
            return jsonify({"error": "No tienes permiso para editar un producto de otro vendedor."}), 403

    if es_nuevo:
        campos_requeridos = ["nombre", "descripcion", "precio_base"]
        faltantes = [c for c in campos_requeridos if c not in data]
        if faltantes:
            return jsonify({
                "error": f"Faltan campos obligatorios para dar de alta un producto nuevo: {', '.join(faltantes)}"
            }), 400

    doc_id = existente["_id"] if existente else f"PROD-{data['sku'].replace(' ', '-').upper()}"
    now = datetime.now(ZONA_GUATEMALA)

    # --- F1: producto nuevo -> crear también la fila en Postgres (productos + inventario) ---
    id_sql_origen = None
    if es_nuevo:
        try:
            nuevo_producto_pg = Producto(
                id_vendedor=int(data.get("id_vendedor", 2)),
                id_categoria=int(data.get("id_categoria", 1)),
                sku=data["sku"],
                nombre=data["nombre"],
                descripcion=data["descripcion"],
                precio_base=float(data["precio_base"]),
                activo=True,
            )
            db.session.add(nuevo_producto_pg)
            # flush (sin cerrar la transacción) para obtener el id_producto asignado por Postgres
            db.session.flush()

            nuevo_inventario_pg = Inventario(
                id_producto=nuevo_producto_pg.id_producto,
                stock_disponible=int(data.get("stock_disponible", 0)),
            )
            db.session.add(nuevo_inventario_pg)
            db.session.commit()

            id_sql_origen = nuevo_producto_pg.id_producto
        except Exception as e:
            db.session.rollback()
            return jsonify({
                "error": f"No se pudo crear el producto en PostgreSQL (productos/inventario): {str(e)}"
            }), 500

    # --- Construcción del documento Mongo: merge en edición, defaults solo en alta ---
    if es_nuevo:
        nuevo_doc = {
            "_id": doc_id,
            "sku": data["sku"],
            "nombre": data["nombre"],
            "descripcion": data["descripcion"],
            "precio_base": float(data["precio_base"]),
            "activo": True,
            "id_sql_origen": id_sql_origen,
            "categoria": {
                "id_categoria": data.get("id_categoria", 1),
                "nombre": data.get("nombre_categoria", "General")
            },
            "vendedor": {
                "id_vendedor": data.get("id_vendedor", 2),
                "nombre_comercial": data.get("nombre_vendedor", "TechStore"),
                "email_contacto": f"{data.get('nombre_vendedor', 'tech').lower().replace(' ', '')}@tiendaya.com"
            },
            "stock_disponible": int(data.get("stock_disponible", 0)),
            # Antes: placeholder de https://via.placeholder.com/300 (servicio dado de baja).
            # El frontend ya hace fallback a un ícono SVG cuando no hay imágenes, así que un
            # array vacío es el default correcto en vez de una URL rota.
            "imagenes": data.get("imagenes", []),
            "atributos": data.get("atributos", {}),
        }
    else:
        # Merge: partimos del documento existente y solo pisamos lo que vino en el payload.
        nuevo_doc = dict(existente)
        if "nombre" in data:
            nuevo_doc["nombre"] = data["nombre"]
        if "descripcion" in data:
            nuevo_doc["descripcion"] = data["descripcion"]
        if "precio_base" in data:
            nuevo_doc["precio_base"] = float(data["precio_base"])
        if "stock_disponible" in data:
            nuevo_doc["stock_disponible"] = int(data["stock_disponible"])
        if "imagenes" in data:
            nuevo_doc["imagenes"] = data["imagenes"]
        if "atributos" in data:
            nuevo_doc["atributos"] = data["atributos"]
        if "id_categoria" in data or "nombre_categoria" in data:
            categoria_actual = nuevo_doc.get("categoria", {})
            nuevo_doc["categoria"] = {
                "id_categoria": data.get("id_categoria", categoria_actual.get("id_categoria", 1)),
                "nombre": data.get("nombre_categoria", categoria_actual.get("nombre", "General"))
            }
        nuevo_doc["_id"] = doc_id
        nuevo_doc["sku"] = data["sku"]

    nuevo_doc["ultima_actualizacion"] = now.isoformat()

    col_productos.update_one({"_id": doc_id}, {"$set": nuevo_doc}, upsert=True)

    evento = {
        "producto_id": doc_id,
        "tipo_evento": "ACTUALIZACION_PANEL_ADMIN",
        "fecha_evento": now,
        "usuario_responsable": {
            "id_usuario": data.get("id_vendedor", 2),
            "nombre": data.get("nombre_vendedor", "TechStore"),
            "rol": rol_solicitante or "administrador"
        },
        "estado_resultante": {
            "nombre": nuevo_doc.get("nombre"),
            "descripcion": nuevo_doc.get("descripcion"),
            "precio_base": nuevo_doc.get("precio_base"),
            "activo": nuevo_doc.get("activo", True),
            "atributos": nuevo_doc.get("atributos", {})
        }
    }
    col_historial.insert_one(evento)

    return jsonify({"mensaje": "Producto guardado con éxito", "producto_id": doc_id}), 201
