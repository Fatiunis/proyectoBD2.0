import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient, ASCENDING
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)

# Configuración de conexiones
PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "tiendaya_db",
    "user": "postgres",
    "password": "1234"  # Ajusta a tu contraseña local
}

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["tiendaya_nosql"]
col_productos = db["productos"]
col_historial = db["historial_cambios_productos"]

def get_pg_connection():
    return psycopg2.connect(**PG_CONFIG)

# ============================================================================
# MÓDULO DE AUTENTICACIÓN (POSTGRESQL - FASE INICIAL)
# ============================================================================

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    nombre = data.get("nombre")
    email = data.get("email")
    password = data.get("password")
    rol = data.get("rol", "comprador")
    telefono = data.get("telefono", "")

    if not nombre or not email or not password:
        return jsonify({"error": "Nombre, email y contraseña son obligatorios"}), 400

    if rol not in ["comprador", "vendedor", "administrador"]:
        return jsonify({"error": "Rol inválido"}), 400

    password_hash = generate_password_hash(password)

    try:
        conn = get_pg_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Verificar si el email ya existe
        cur.execute("SELECT id_usuario FROM usuarios WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({"error": "El correo electrónico ya se encuentra registrado"}), 409

        # Insertar nuevo usuario
        cur.execute(
            """
            INSERT INTO usuarios (nombre, email, password_hash, rol, telefono)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id_usuario, nombre, email, rol, fecha_registro;
            """,
            (nombre, email, password_hash, rol, telefono)
        )
        nuevo_usuario = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        nuevo_usuario["fecha_registro"] = nuevo_usuario["fecha_registro"].isoformat()
        return jsonify({"mensaje": "Usuario registrado exitosamente", "usuario": nuevo_usuario}), 201

    except Exception as e:
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email y contraseña requeridos"}), 400

    try:
        conn = get_pg_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id_usuario, nombre, email, password_hash, rol FROM usuarios WHERE email = %s", (email,))
        usuario = cur.fetchone()
        cur.close()
        conn.close()

        if not usuario or not check_password_hash(usuario["password_hash"], password):
            return jsonify({"error": "Credenciales inválidas"}), 401

        # Sesión simulada para el portal
        return jsonify({
            "mensaje": "Inicio de sesión exitoso",
            "usuario": {
                "id_usuario": usuario["id_usuario"],
                "nombre": usuario["nombre"],
                "email": usuario["email"],
                "rol": usuario["rol"]
            }
        }), 200

    except Exception as e:
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


# ============================================================================
# MÓDULO DE CATÁLOGO & HISTORIAL (MONGODB - ENTREGA 1)
# ============================================================================

@app.route("/api/categorias", methods=["GET"])
def get_categorias():
    categorias = col_productos.distinct("categoria")
    return jsonify(categorias)


@app.route("/api/productos", methods=["GET"])
def get_productos():
    cat_id = request.args.get("categoria_id")
    query = {"activo": True}
    if cat_id:
        try:
            query["categoria.id_categoria"] = int(cat_id)
        except ValueError:
            pass

    docs = list(col_productos.find(
        query,
        {"_id": 1, "sku": 1, "nombre": 1, "precio_base": 1, "categoria": 1, "atributos": 1, "imagenes": 1}
    ).sort("precio_base", ASCENDING))

    for d in docs:
        d["_id"] = str(d["_id"])
    return jsonify(docs)


@app.route("/api/productos/<producto_id>", methods=["GET"])
def get_producto_detalle(producto_id):
    doc = col_productos.find_one({"_id": producto_id})
    if not doc:
        return jsonify({"error": "Producto no encontrado"}), 404
    doc["_id"] = str(doc["_id"])
    return jsonify(doc)


@app.route("/api/productos", methods=["POST"])
def crear_o_actualizar_producto():
    data = request.get_json()
    if not data or "sku" not in data:
        return jsonify({"error": "Datos inválidos"}), 400

    doc_id = f"PROD-{data['sku'].replace(' ', '-').upper()}"
    now = datetime.now(timezone.utc)

    nuevo_doc = {
        "_id": doc_id,
        "sku": data["sku"],
        "nombre": data["nombre"],
        "descripcion": data["descripcion"],
        "precio_base": float(data["precio_base"]),
        "activo": True,
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
        "imagenes": data.get("imagenes", [{"url": "https://via.placeholder.com/300", "es_portada": True, "orden": 1}]),
        "atributos": data.get("atributos", {}),
        "ultima_actualizacion": now.isoformat()
    }

    col_productos.update_one({"_id": doc_id}, {"$set": nuevo_doc}, upsert=True)

    evento = {
        "producto_id": doc_id,
        "tipo_evento": "ACTUALIZACION_PANEL_ADMIN",
        "fecha_evento": now,
        "usuario_responsable": {
            "id_usuario": data.get("id_vendedor", 2),
            "nombre": data.get("nombre_vendedor", "TechStore"),
            "rol": "administrador"
        },
        "estado_resultante": {
            "nombre": data["nombre"],
            "descripcion": data["descripcion"],
            "precio_base": float(data["precio_base"]),
            "activo": True,
            "atributos": data.get("atributos", {})
        }
    }
    col_historial.insert_one(evento)

    return jsonify({"mensaje": "Producto guardado con éxito", "producto_id": doc_id}), 201


@app.route("/api/historial/<producto_id>", methods=["GET"])
def reconstruir_historial(producto_id):
    fecha_corte = request.args.get("fecha_corte")
    if not fecha_corte:
        return jsonify({"error": "Parámetro fecha_corte requerido"}), 400

    try:
        dt_corte = datetime.fromisoformat(fecha_corte.replace("Z", "+00:00"))
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Usar ISO 8601"}), 400

    pipeline = [
        {"$match": {"producto_id": producto_id, "fecha_evento": {"$lte": dt_corte}}},
        {"$sort": {"fecha_evento": -1}},
        {"$limit": 1},
        {
            "$project": {
                "_id": 0,
                "producto_id": 1,
                "fecha_vigencia_evento": "$fecha_evento",
                "tipo_evento": 1,
                "responsable": "$usuario_responsable.nombre",
                "estado_en_esa_fecha": "$estado_resultante"
            }
        }
    ]

    res = list(col_historial.aggregate(pipeline))
    if not res:
        return jsonify({"error": "No existe estado registrado previo a la fecha especificada."}), 404

    res[0]["fecha_vigencia_evento"] = res[0]["fecha_vigencia_evento"].isoformat()
    return jsonify(res[0])


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)