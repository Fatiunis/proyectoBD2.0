from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from ..extensions import db
from ..models import Usuario

bp = Blueprint("auth", __name__)

# ============================================================================
# MÓDULO DE AUTENTICACIÓN (POSTGRESQL, VÍA SQLALCHEMY)
# ============================================================================

def _usuario_a_dict(usuario, incluir_fecha=True):
    data = {
        "id_usuario": usuario.id_usuario,
        "nombre": usuario.nombre,
        "email": usuario.email,
        "rol": usuario.rol,
    }
    if incluir_fecha:
        data["fecha_registro"] = usuario.fecha_registro.isoformat()
    return data


@bp.route("/api/auth/register", methods=["POST"])
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
        if db.session.query(Usuario.id_usuario).filter_by(email=email).first():
            return jsonify({"error": "El correo electrónico ya se encuentra registrado"}), 409

        nuevo_usuario = Usuario(
            nombre=nombre,
            email=email,
            password_hash=password_hash,
            rol=rol,
            telefono=telefono,
        )
        db.session.add(nuevo_usuario)
        db.session.commit()

        usuario_dict = _usuario_a_dict(nuevo_usuario)
        return jsonify({"mensaje": "Usuario registrado exitosamente", "usuario": usuario_dict}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


@bp.route("/api/usuarios", methods=["GET"])
def listar_usuarios():
    try:
        usuarios = (
            db.session.query(Usuario)
            .order_by(Usuario.id_usuario)
            .all()
        )
        return jsonify([
            {
                "id_usuario": u.id_usuario,
                "nombre": u.nombre,
                "email": u.email,
                "rol": u.rol,
                "telefono": u.telefono,
                "fecha_registro": u.fecha_registro.isoformat(),
            }
            for u in usuarios
        ])
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


@bp.route("/api/usuarios/<int:id_usuario>", methods=["PUT"])
def actualizar_usuario(id_usuario):
    data = request.get_json() or {}

    if data.get("rol_solicitante") != "administrador":
        return jsonify({"error": "Solo un administrador puede modificar usuarios."}), 403

    nuevo_rol = data.get("rol")
    if nuevo_rol not in ["comprador", "vendedor", "administrador"]:
        return jsonify({"error": "Rol inválido"}), 400

    try:
        usuario = db.session.get(Usuario, id_usuario)
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        usuario.rol = nuevo_rol
        db.session.commit()

        return jsonify({
            "mensaje": "Usuario actualizado con éxito",
            "usuario": {
                "id_usuario": usuario.id_usuario,
                "nombre": usuario.nombre,
                "email": usuario.email,
                "rol": usuario.rol,
                "telefono": usuario.telefono,
                "fecha_registro": usuario.fecha_registro.isoformat(),
            },
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


@bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email y contraseña requeridos"}), 400

    try:
        usuario = db.session.query(Usuario).filter_by(email=email).first()

        if not usuario or not check_password_hash(usuario.password_hash, password):
            return jsonify({"error": "Credenciales inválidas"}), 401

        # Sesión simulada para el portal
        return jsonify({
            "mensaje": "Inicio de sesión exitoso",
            "usuario": {
                "id_usuario": usuario.id_usuario,
                "nombre": usuario.nombre,
                "email": usuario.email,
                "rol": usuario.rol,
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500
