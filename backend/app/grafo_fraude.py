"""
Sincronización en mejor esfuerzo del grafo de fraude (Neo4j) desde el backend.

Lo usan resenas.py (al crear una reseña: Vendedor, VENDIDO_POR,
Producto.id_vendedor y CALIFICO.compra_verificada) y direcciones.py (al
crear/editar/borrar una dirección: (:Cuenta)-[:ENVIA_A]->(:Direccion)).

Mismo criterio que el resto del espejo Mongo -> Neo4j: no hay 2PC. Estas
funciones se llaman DESPUÉS del commit en la base que es fuente de verdad
(Mongo para reseñas, Postgres para direcciones); si Neo4j falla, el caller
captura la excepción, loguea y responde igual. El script
database/migrations/sincronizar_grafo_fraude.py reconstruye todo esto para
los datos existentes (idempotente), y sirve de backfill si alguna
sincronización se pierde.

La clave de una dirección DEBE calcularse igual que en
sincronizar_grafo_fraude.py (contrato del grafo de fraude ampliado):
    clave = normalizar(direccion_linea1) | normalizar(ciudad) | normalizar(codigo_postal)
    normalizar(s) = " ".join((s or "").lower().split())   (sin quitar tildes)
Así, dos cuentas que escriben la misma dirección con distinto uso de
mayúsculas o espacios caen en el mismo nodo (:Direccion).
"""

from .extensions import db, neo4j_driver
from .models import Direccion, LineaPedido, Pedido, Usuario


def normalizar(s):
    return " ".join((s or "").lower().split())


def clave_direccion(direccion_linea1, ciudad, codigo_postal):
    return normalizar(direccion_linea1) + "|" + normalizar(ciudad) + "|" + normalizar(codigo_postal)


def compra_verificada(id_usuario, id_sql_origen_producto):
    """
    True si el usuario tiene algún pedido con una línea de ese producto.

    Mismo criterio que resenas.get_resenas_producto usa para `verificada_compra`
    al listar: NO filtra por estado del pedido (un pedido cancelado también
    cuenta). Se mantiene idéntico a propósito para que el panel de reseñas y
    el grafo de fraude digan lo mismo sobre la misma reseña.
    """
    if id_sql_origen_producto is None:
        return False
    fila = (
        db.session.query(Pedido.id_pedido)
        .join(LineaPedido, LineaPedido.id_pedido == Pedido.id_pedido)
        .filter(Pedido.id_comprador == id_usuario, LineaPedido.id_producto == id_sql_origen_producto)
        .first()
    )
    return fila is not None


_Q_CUENTA = """
    MERGE (c:Cuenta {id_usuario: $id_usuario})
      ON CREATE SET c.nombre = $nombre, c.rol = $rol
"""

# Quita las relaciones a direcciones que la cuenta ya no tiene, y borra el
# nodo (:Direccion) solo si ninguna otra cuenta lo sigue usando.
_Q_QUITAR_VIEJAS = """
    MATCH (c:Cuenta {id_usuario: $id_usuario})-[e:ENVIA_A]->(d:Direccion)
    WHERE NOT d.clave IN $claves
    DELETE e
    WITH DISTINCT d
    WHERE NOT EXISTS { (d)<-[:ENVIA_A]-(:Cuenta) }
    DELETE d
"""

_Q_AGREGAR_ACTUALES = """
    MATCH (c:Cuenta {id_usuario: $id_usuario})
    UNWIND $direcciones AS dir
    MERGE (d:Direccion {clave: dir.clave})
      SET d.ciudad = dir.ciudad, d.departamento = dir.departamento
    MERGE (c)-[:ENVIA_A]->(d)
"""


def sincronizar_direcciones_cuenta(id_usuario):
    """
    Deja las relaciones ENVIA_A de la cuenta iguales al conjunto ACTUAL de
    sus direcciones en Postgres (lee la fuente de verdad en el momento de
    sincronizar, en vez de aplicar un delta). Es idempotente y sirve igual
    para crear, editar y borrar. Debe llamarse después del commit.

    Carrera conocida (mejor esfuerzo, sin 2PC): si dos cambios de direcciones
    del mismo usuario se confirman casi a la vez, la sincronización que lea
    primero puede escribir en Neo4j después que la otra y dejar un estado
    viejo; lo corrige la próxima edición o sincronizar_grafo_fraude.py.
    """
    usuario = db.session.get(Usuario, id_usuario)
    if usuario is None:
        db.session.rollback()
        return
    direcciones = db.session.query(Direccion).filter_by(id_usuario=id_usuario).all()
    por_clave = {}
    for d in direcciones:
        clave = clave_direccion(d.direccion_linea1, d.ciudad, d.codigo_postal)
        por_clave[clave] = {"clave": clave, "ciudad": d.ciudad, "departamento": d.departamento_estado}
    nombre, rol = usuario.nombre, usuario.rol
    db.session.commit()  # solo lectura; cierra la transacción de Postgres

    with neo4j_driver.session() as session:
        with session.begin_transaction() as tx:
            tx.run(_Q_QUITAR_VIEJAS, id_usuario=id_usuario, claves=list(por_clave)).consume()
            if por_clave:
                # La cuenta se crea aunque todavía no haya reseñado nada: así,
                # cuando reseñe, el vínculo por dirección ya está en el grafo.
                tx.run(_Q_CUENTA, id_usuario=id_usuario, nombre=nombre, rol=rol).consume()
                tx.run(_Q_AGREGAR_ACTUALES, id_usuario=id_usuario, direcciones=list(por_clave.values())).consume()
            tx.commit()
