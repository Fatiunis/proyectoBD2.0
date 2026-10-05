from datetime import datetime

from flask import Blueprint, request, jsonify
from sqlalchemy import func

from .. import sincronizacion
from ..extensions import db, ZONA_GUATEMALA
from ..models import EventoSincronizacion

bp = Blueprint("sincronizacion", __name__)

# ============================================================================
# EVENTOS DE SINCRONIZACIÓN DEL CHECKOUT (OUTBOX - ENTREGA 3)
# ============================================================================
# Panel de observación del outbox (ver app/sincronizacion.py): cuántos eventos
# hay pendientes, procesados o fallidos, cuáles son, y la opción de procesarlos
# ya o de volver a poner en cola los fallidos. Solo administrador (mismo patrón
# de rol_solicitante que el resto del panel admin).


def _solo_admin(rol):
    if rol != "administrador":
        return jsonify({"error": "Solo un administrador puede ver la sincronización."}), 403
    return None


def _evento_a_dict(e):
    return {
        "id_evento": e.id_evento,
        "tipo": e.tipo,
        "payload": e.payload,
        "id_pedido": e.id_pedido,
        "estado": e.estado,
        "intentos": e.intentos,
        "ultimo_error": e.ultimo_error,
        "proximo_intento": e.proximo_intento.isoformat() if e.proximo_intento else None,
        "creado_en": e.creado_en.isoformat() if e.creado_en else None,
        "procesado_en": e.procesado_en.isoformat() if e.procesado_en else None,
    }


@bp.route("/api/sincronizacion/eventos", methods=["GET"])
def listar_eventos():
    """?rol_solicitante=administrador&estado=pendiente|procesado|fallido&id_pedido=&limite=50"""
    error = _solo_admin(request.args.get("rol_solicitante"))
    if error:
        return error

    try:
        resumen = {estado: 0 for estado in ("pendiente", "procesado", "fallido")}
        for estado, cantidad in (
            db.session.query(EventoSincronizacion.estado, func.count()).group_by(EventoSincronizacion.estado).all()
        ):
            resumen[estado] = cantidad

        consulta = db.session.query(EventoSincronizacion)
        estado = request.args.get("estado")
        if estado:
            consulta = consulta.filter(EventoSincronizacion.estado == estado)
        id_pedido = request.args.get("id_pedido")
        if id_pedido:
            consulta = consulta.filter(EventoSincronizacion.id_pedido == int(id_pedido))
        limite = min(max(int(request.args.get("limite", 50)), 1), 200)
        eventos = consulta.order_by(EventoSincronizacion.id_evento.desc()).limit(limite).all()

        return jsonify({"resumen": resumen, "eventos": [_evento_a_dict(e) for e in eventos]})
    except ValueError:
        return jsonify({"error": "id_pedido y limite deben ser enteros"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500


@bp.route("/api/sincronizacion/procesar", methods=["POST"])
def procesar_ahora():
    """Ejecuta ya los eventos pendientes (sin esperar al relevo de fondo)."""
    data = request.get_json(silent=True) or {}
    error = _solo_admin(data.get("rol_solicitante"))
    if error:
        return error

    try:
        # "Ahora" incluye a los que esperaban su próximo intento.
        db.session.query(EventoSincronizacion).filter(EventoSincronizacion.estado == "pendiente").update(
            {EventoSincronizacion.proximo_intento: datetime.now(ZONA_GUATEMALA)}, synchronize_session=False
        )
        db.session.commit()
        return jsonify(sincronizacion.procesar())
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"No se pudieron procesar los eventos: {str(e)}"}), 500


@bp.route("/api/sincronizacion/reintentar-fallidos", methods=["POST"])
def reintentar_fallidos():
    """Vuelve a poner en cola los eventos que agotaron sus intentos."""
    data = request.get_json(silent=True) or {}
    error = _solo_admin(data.get("rol_solicitante"))
    if error:
        return error

    try:
        n = db.session.query(EventoSincronizacion).filter(EventoSincronizacion.estado == "fallido").update(
            {
                EventoSincronizacion.estado: "pendiente",
                EventoSincronizacion.intentos: 0,
                EventoSincronizacion.proximo_intento: datetime.now(ZONA_GUATEMALA),
            },
            synchronize_session=False,
        )
        db.session.commit()
        return jsonify({"mensaje": f"{n} eventos vuelven a estar pendientes", "reencolados": n})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500
