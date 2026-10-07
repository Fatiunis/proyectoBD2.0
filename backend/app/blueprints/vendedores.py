from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import LineaPedido, Pedido, Producto

bp = Blueprint("vendedores", __name__)

# Mismos roles y mensajes que listar_ofertas_vendedor (ofertas.py); se copia la
# constante en vez de importarla para no acoplar blueprints entre sí.
ROLES_VALIDOS = ("vendedor", "administrador")


@bp.route("/api/vendedores/<int:id_vendedor>/ventas", methods=["GET"])
def get_ventas_vendedor(id_vendedor):
    """?rol_solicitante=vendedor|administrador&id_usuario=<int>
    Un vendedor solo ve sus propias ventas; el administrador puede consultar cualquiera."""
    rol_solicitante = request.args.get("rol_solicitante")
    if rol_solicitante not in ROLES_VALIDOS:
        return jsonify({"error": "rol_solicitante debe ser 'vendedor' o 'administrador'"}), 403

    try:
        id_usuario = int(request.args.get("id_usuario"))
    except (TypeError, ValueError):
        return jsonify({"error": "id_usuario es obligatorio y debe ser un entero"}), 400

    if rol_solicitante == "vendedor" and id_usuario != id_vendedor:
        return jsonify({"error": "Solo puedes ver tus propias ventas"}), 403

    try:
        filas = (
            db.session.query(LineaPedido, Pedido)
            .join(Producto, Producto.id_producto == LineaPedido.id_producto)
            .join(Pedido, Pedido.id_pedido == LineaPedido.id_pedido)
            .filter(Producto.id_vendedor == id_vendedor)
            .order_by(Pedido.fecha_pedido.desc())
            .all()
        )

        ventas = [
            {
                "id_linea": lp.id_linea,
                "id_producto": lp.id_producto,
                "nombre_producto_historico": lp.nombre_producto_historico,
                "cantidad": lp.cantidad,
                "precio_unitario_historico": float(lp.precio_unitario_historico),
                "subtotal": float(lp.subtotal),
                "id_pedido": pe.id_pedido,
                "fecha_pedido": pe.fecha_pedido.isoformat(),
                "estado": pe.estado,
            }
            for lp, pe in filas
        ]

        total_vendido = sum(v["subtotal"] for v in ventas if v["estado"] != "cancelado")
        unidades_vendidas = sum(v["cantidad"] for v in ventas if v["estado"] != "cancelado")

        return jsonify({
            "ventas": ventas,
            "resumen": {
                "total_vendido": total_vendido,
                "unidades_vendidas": unidades_vendidas,
                "numero_lineas": len(ventas)
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error en base de datos: {str(e)}"}), 500
