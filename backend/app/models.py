"""
Modelos SQLAlchemy para las tablas de PostgreSQL que hoy consumen los
blueprints migrados (auth, catalogo -> /api/categorias, vendedores).

Los nombres de tabla (`__tablename__`) apuntan a las tablas reales creadas
por `database/postgres/ddl_tiendaya.sql`; no se generan tablas nuevas.
Solo se modelan las columnas que los endpoints actuales necesitan leer o
escribir, para mantener el cambio acotado a esta sub-fase de migración.

`checkout.py` NO usa estos modelos: sigue invocando `sp_procesar_checkout`
directamente (ver ese blueprint), porque la lógica transaccional vive
intencionalmente en la base de datos.
"""
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB

from .extensions import db


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id_usuario = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False)
    telefono = db.Column(db.String(20))
    # server_default refleja el DEFAULT CURRENT_TIMESTAMP real de la columna en
    # el DDL: si no se asigna explícitamente, SQLAlchemy omite la columna del
    # INSERT (en vez de mandar NULL) y deja que Postgres calcule el valor, que
    # luego se recupera automáticamente vía RETURNING.
    fecha_registro = db.Column(db.DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class Categoria(db.Model):
    __tablename__ = "categorias"

    id_categoria = db.Column(db.Integer, primary_key=True)
    nombre_categoria = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.Text)
    id_categoria_padre = db.Column(db.Integer, db.ForeignKey("categorias.id_categoria"))
    esquema_atributos = db.Column(JSONB, nullable=False, default=list)


class Producto(db.Model):
    __tablename__ = "productos"

    id_producto = db.Column(db.Integer, primary_key=True)
    id_vendedor = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    id_categoria = db.Column(db.Integer, db.ForeignKey("categorias.id_categoria"), nullable=False)
    sku = db.Column(db.String(60), nullable=False, unique=True)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    precio_base = db.Column(db.Numeric(12, 2), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class Inventario(db.Model):
    __tablename__ = "inventario"

    id_inventario = db.Column(db.Integer, primary_key=True)
    id_producto = db.Column(db.Integer, db.ForeignKey("productos.id_producto"), nullable=False, unique=True)
    stock_disponible = db.Column(db.Integer, nullable=False)
    stock_reservado = db.Column(db.Integer, nullable=False, default=0, server_default=text("0"))
    ultima_actualizacion = db.Column(db.DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class Pedido(db.Model):
    __tablename__ = "pedidos"

    id_pedido = db.Column(db.Integer, primary_key=True)
    id_comprador = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    id_direccion_envio = db.Column(db.Integer, db.ForeignKey("direcciones.id_direccion"), nullable=False)
    fecha_pedido = db.Column(db.DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    estado = db.Column(db.String(30), nullable=False)
    total = db.Column(db.Numeric(12, 2), nullable=False)


class LineaPedido(db.Model):
    __tablename__ = "lineas_pedido"

    id_linea = db.Column(db.Integer, primary_key=True)
    id_pedido = db.Column(db.Integer, db.ForeignKey("pedidos.id_pedido"), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey("productos.id_producto"), nullable=False)
    nombre_producto_historico = db.Column(db.String(200), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario_historico = db.Column(db.Numeric(12, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
