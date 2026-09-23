from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Usuario, Direccion

bp = Blueprint("direcciones", __name__)

# ============================================================================
# MÓDULO DE DIRECCIONES DE ENVÍO (POSTGRESQL, VÍA SQLALCHEMY)
# Las usa el checkout: sp_procesar_checkout valida que id_direccion pertenezca
# al comprador, por eso el frontend las lista/crea por usuario.
# ============================================================================

# Longitudes máximas según el DDL de la tabla `direcciones`.
_LONGITUDES = {
    "direccion_linea1": 255,
    "direccion_linea2": 255,
    "ciudad": 100,
    "departamento_estado": 100,
    "codigo_postal": 20,
    "pais": 100,
}

_OBLIGATORIOS = ["direccion_linea1", "ciudad", "departamento_estado", "codigo_postal"]

LIMITE_DIRECCIONES = 3


def _direccion_a_dict(d):
    return {
        "id_direccion": d.id_direccion,
        "direccion_linea1": d.direccion_linea1,
        "direccion_linea2": d.direccion_linea2,
        "ciudad": d.ciudad,
        "departamento_estado": d.departamento_estado,
        "codigo_postal": d.codigo_postal,
        "pais": d.pais,
        "es_principal": d.es_principal,
    }


@bp.route("/api/usuarios/<int:id_usuario>/direcciones", methods=["GET"])
def listar_direcciones(id_usuario):
    try:
        if not db.session.get(Usuario, id_usuario):
            return jsonify({"error": "Usuario no encontrado"}), 404

        direcciones = (
            db.session.query(Direccion)
            .filter_by(id_usuario=id_usuario)
            .order_by(Direccion.es_principal.desc(), Direccion.id_direccion.asc())
            .all()
        )
        resultado = [_direccion_a_dict(d) for d in direcciones]
        db.session.commit()
        return jsonify(resultado)
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


@bp.route("/api/usuarios/<int:id_usuario>/direcciones", methods=["POST"])
def crear_direccion(id_usuario):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo de la solicitud debe ser un objeto JSON"}), 400

    valores = {}
    for campo in _LONGITUDES:
        valor = data.get(campo)
        if valor is None:
            valores[campo] = None
            continue
        if not isinstance(valor, str):
            return jsonify({"error": f"El campo '{campo}' debe ser texto"}), 400
        valores[campo] = valor.strip()

    faltantes = [c for c in _OBLIGATORIOS if not valores.get(c)]
    if faltantes:
        return jsonify({"error": f"Campos obligatorios faltantes: {', '.join(faltantes)}"}), 400

    # Opcionales: cadena vacía se trata como no enviada.
    if not valores.get("direccion_linea2"):
        valores["direccion_linea2"] = None
    if not valores.get("pais"):
        valores["pais"] = "Guatemala"

    for campo, maximo in _LONGITUDES.items():
        if valores[campo] is not None and len(valores[campo]) > maximo:
            return jsonify({"error": f"El campo '{campo}' excede la longitud máxima de {maximo} caracteres"}), 400

    es_principal = data.get("es_principal", False)
    if es_principal is None:
        es_principal = False
    if not isinstance(es_principal, bool):
        return jsonify({"error": "El campo 'es_principal' debe ser booleano"}), 400

    try:
        # Bloquea la fila del usuario para serializar altas concurrentes de
        # direcciones del mismo usuario (evita dos "primeras" o dos principales).
        usuario = (
            db.session.query(Usuario)
            .filter_by(id_usuario=id_usuario)
            .with_for_update()
            .first()
        )
        if not usuario:
            db.session.rollback()
            return jsonify({"error": "Usuario no encontrado"}), 404

        cantidad_actual = (
            db.session.query(db.func.count(Direccion.id_direccion))
            .filter_by(id_usuario=id_usuario)
            .scalar()
        )
        if cantidad_actual >= LIMITE_DIRECCIONES:
            db.session.rollback()
            return jsonify({"error": f"Ya tienes el máximo de {LIMITE_DIRECCIONES} direcciones."}), 409

        tiene_direcciones = cantidad_actual > 0
        if not tiene_direcciones:
            es_principal = True

        if es_principal:
            db.session.query(Direccion).filter(
                Direccion.id_usuario == id_usuario,
                Direccion.es_principal.is_(True),
            ).update({Direccion.es_principal: False}, synchronize_session=False)

        nueva = Direccion(id_usuario=id_usuario, es_principal=es_principal, **valores)
        db.session.add(nueva)
        db.session.commit()

        return jsonify(_direccion_a_dict(nueva)), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


@bp.route("/api/usuarios/<int:id_usuario>/direcciones/<int:id_direccion>", methods=["PUT"])
def actualizar_direccion(id_usuario, id_direccion):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo de la solicitud debe ser un objeto JSON"}), 400

    valores = {}
    for campo in _LONGITUDES:
        valor = data.get(campo)
        if valor is None:
            valores[campo] = None
            continue
        if not isinstance(valor, str):
            return jsonify({"error": f"El campo '{campo}' debe ser texto"}), 400
        valores[campo] = valor.strip()

    faltantes = [c for c in _OBLIGATORIOS if not valores.get(c)]
    if faltantes:
        return jsonify({"error": f"Campos obligatorios faltantes: {', '.join(faltantes)}"}), 400

    # Opcionales: cadena vacía se trata como no enviada.
    if not valores.get("direccion_linea2"):
        valores["direccion_linea2"] = None
    if not valores.get("pais"):
        valores["pais"] = "Guatemala"

    for campo, maximo in _LONGITUDES.items():
        if valores[campo] is not None and len(valores[campo]) > maximo:
            return jsonify({"error": f"El campo '{campo}' excede la longitud máxima de {maximo} caracteres"}), 400

    es_principal = data.get("es_principal", False)
    if es_principal is None:
        es_principal = False
    if not isinstance(es_principal, bool):
        return jsonify({"error": "El campo 'es_principal' debe ser booleano"}), 400

    try:
        # Bloquea la fila del usuario para serializar ediciones concurrentes
        # de direcciones del mismo usuario (evita dos principales a la vez).
        usuario = (
            db.session.query(Usuario)
            .filter_by(id_usuario=id_usuario)
            .with_for_update()
            .first()
        )
        if not usuario:
            db.session.rollback()
            return jsonify({"error": "Usuario no encontrado"}), 404

        direccion = (
            db.session.query(Direccion)
            .filter_by(id_direccion=id_direccion, id_usuario=id_usuario)
            .first()
        )
        if not direccion:
            db.session.rollback()
            return jsonify({"error": "Dirección no encontrada"}), 404

        if es_principal:
            db.session.query(Direccion).filter(
                Direccion.id_usuario == id_usuario,
                Direccion.id_direccion != id_direccion,
                Direccion.es_principal.is_(True),
            ).update({Direccion.es_principal: False}, synchronize_session=False)

        for campo, valor in valores.items():
            setattr(direccion, campo, valor)
        direccion.es_principal = es_principal

        db.session.commit()
        return jsonify(_direccion_a_dict(direccion)), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


@bp.route("/api/usuarios/<int:id_usuario>/direcciones/<int:id_direccion>", methods=["DELETE"])
def eliminar_direccion(id_usuario, id_direccion):
    try:
        usuario = db.session.query(Usuario).filter_by(id_usuario=id_usuario).with_for_update().first()
        if not usuario:
            db.session.rollback()
            return jsonify({"error": "Usuario no encontrado"}), 404

        direccion = db.session.query(Direccion).filter_by(
            id_direccion=id_direccion, id_usuario=id_usuario
        ).first()
        if not direccion:
            db.session.rollback()
            return jsonify({"error": "Dirección no encontrada"}), 404

        era_principal = direccion.es_principal
        db.session.delete(direccion)
        db.session.flush()

        if era_principal:
            siguiente = (
                db.session.query(Direccion)
                .filter_by(id_usuario=id_usuario)
                .order_by(Direccion.id_direccion.asc())
                .first()
            )
            if siguiente:
                siguiente.es_principal = True

        db.session.commit()
        return jsonify({"mensaje": "Dirección eliminada"}), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "error": "No se puede eliminar: esta dirección ya se usó en un pedido anterior."
        }), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500
