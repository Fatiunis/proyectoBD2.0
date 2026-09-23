from flask import Blueprint, jsonify

from ..extensions import db
from ..models import LineaPedido, Pedido

bp = Blueprint("compradores", __name__)


@bp.route("/api/compradores/<int:id_comprador>/pedidos", methods=["GET"])
def get_pedidos_comprador(id_comprador):
    try:
        pedidos = (
            db.session.query(Pedido)
            .filter_by(id_comprador=id_comprador)
            .order_by(Pedido.fecha_pedido.desc())
            .all()
        )
        ids_pedido = [p.id_pedido for p in pedidos]
        lineas = (
            db.session.query(LineaPedido)
            .filter(LineaPedido.id_pedido.in_(ids_pedido))
            .all()
            if ids_pedido else []
        )
        lineas_por_pedido = {}
        for l in lineas:
            lineas_por_pedido.setdefault(l.id_pedido, []).append({
                "nombre_producto_historico": l.nombre_producto_historico,
                "cantidad": l.cantidad,
                "precio_unitario_historico": float(l.precio_unitario_historico),
                "subtotal": float(l.subtotal),
            })

        pedidos_out = [{
            "id_pedido": p.id_pedido,
            "fecha_pedido": p.fecha_pedido.isoformat(),
            "estado": p.estado,
            "total": float(p.total),
            "lineas": lineas_por_pedido.get(p.id_pedido, []),
        } for p in pedidos]

        total_gastado = sum(p["total"] for p in pedidos_out if p["estado"] != "cancelado")

        return jsonify({
            "pedidos": pedidos_out,
            "resumen": {"total_gastado": total_gastado, "numero_pedidos": len(pedidos_out)},
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500
