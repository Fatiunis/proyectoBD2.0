"""
Sincroniza el grafo de fraude de Neo4j con el modelo ampliado (después de la Entrega 3, 2026-10-07).

Propósito
---------
La detección de fraude ampliada (patrones cuenta_rafaga, grupo_coordinado,
sesgo_vendedor_sin_compra y cuentas_vinculadas) necesita en el grafo datos que la Entrega 2 no
guardaba. Este script los completa para los nodos y relaciones que YA existen:

1. (:Vendedor {id_vendedor, nombre}) y (:Producto)-[:VENDIDO_POR]->(:Vendedor), más
   Producto.id_vendedor, para cada Producto del grafo (leyendo `vendedor` del documento
   del producto en Mongo; nombre = vendedor.nombre_comercial).
2. CALIFICO.compra_verificada (bool) de cada reseña: true si el autor tiene en Postgres un
   pedido con una línea de ese producto (pedidos + lineas_pedido, por id_sql_origen del
   producto). Es el mismo criterio que backend/app/blueprints/resenas.py usa para
   `verificada_compra` al listar reseñas, que NO filtra por estado del pedido (un pedido
   cancelado también cuenta); se usa igual aquí para que la API y el grafo coincidan.
3. (:Direccion {clave, ciudad, departamento}) y (:Cuenta)-[:ENVIA_A]->(:Direccion) para
   las cuentas que ya están en el grafo y tienen direcciones en Postgres. La clave se
   normaliza con `clave_direccion` (misma función que usa el backend).

Idempotente y NO destructivo: solo MERGE/SET (no borra nodos ni relaciones, no toca
Mongo ni Postgres). Correrlo varias veces deja el mismo grafo. No crea nodos Cuenta ni
Producto nuevos: solo enriquece los que ya existen por las reseñas.

También asegura (IF NOT EXISTS) las constraints de database/neo4j/02_fraude_ampliado.cypher.

Uso:
    venv/Scripts/python database/migrations/sincronizar_grafo_fraude.py

La lógica está en `sincronizar_grafo(pg_conn, mongo_db, neo4j_driver)`, que importa
sembrar_fraude_ampliado.py para dejar el grafo completo al final de su siembra.
"""
import os
import sys

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from pymongo import MongoClient
from neo4j import GraphDatabase

# La consola de Windows no usa UTF-8 por defecto; forzamos la codificación de
# salida para que el script corra igual en todo el equipo.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# ============================================================================
# CONFIGURACIÓN DE CONEXIONES (mismo patrón que sembrar_resenas_fraude.py)
# ============================================================================
PG_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DBNAME", "tiendaya_db"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "root"),
}

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "tiendaya_nosql")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "tiendaya123")

# Mismas sentencias que database/neo4j/02_fraude_ampliado.cypher (idempotentes).
CONSTRAINTS_FRAUDE_AMPLIADO = [
    "CREATE CONSTRAINT vendedor_id IF NOT EXISTS FOR (v:Vendedor) REQUIRE v.id_vendedor IS UNIQUE",
    "CREATE CONSTRAINT direccion_clave IF NOT EXISTS FOR (d:Direccion) REQUIRE d.clave IS UNIQUE",
]


# ============================================================================
# NORMALIZACIÓN DE DIRECCIONES (idéntica en backend y database)
# ============================================================================
def normalizar(s):
    """Minúsculas y espacios colapsados; NO quita tildes ni puntuación."""
    return " ".join((s or "").lower().split())


def clave_direccion(direccion_linea1, ciudad, codigo_postal):
    """Clave del nodo :Direccion; dos direcciones con la misma clave son la misma."""
    return normalizar(direccion_linea1) + "|" + normalizar(ciudad) + "|" + normalizar(codigo_postal)


# ============================================================================
# CONEXIONES
# ============================================================================
def conectar_todo():
    """Abre las tres conexiones (Postgres, Mongo, Neo4j) y valida que respondan."""
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        print("[OK] Conectado a PostgreSQL")
    except Exception as e:
        print(f"[X] Error conectando a PostgreSQL: {e}")
        sys.exit(1)

    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command("ping")
        mongo_db = mongo_client[MONGO_DB_NAME]
        print("[OK] Conectado a MongoDB")
    except Exception as e:
        print(f"[X] Error conectando a MongoDB: {e}")
        sys.exit(1)

    try:
        # notifications_min_severity="OFF": en un grafo recién sembrado, Neo4j avisa
        # "property key does not exist" al contar propiedades/relaciones que todavía no
        # existen (p. ej. VENDIDO_POR antes de la primera corrida); no son errores.
        neo4j_driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), notifications_min_severity="OFF"
        )
        neo4j_driver.verify_connectivity()
        print("[OK] Conectado a Neo4j")
    except Exception as e:
        print(f"[X] Error conectando a Neo4j: {e}")
        sys.exit(1)

    return pg_conn, mongo_client, mongo_db, neo4j_driver


def _leer(session, query, **params):
    return [record.data() for record in session.run(query, **params)]


# ============================================================================
# PASOS DE LA SINCRONIZACIÓN
# ============================================================================
def asegurar_constraints(neo4j_driver):
    with neo4j_driver.session() as session:
        for sentencia in CONSTRAINTS_FRAUDE_AMPLIADO:
            session.run(sentencia).consume()
    print("[OK] Constraints Vendedor.id_vendedor y Direccion.clave aseguradas")


def leer_productos_mongo(mongo_db, ids_producto):
    """Devuelve {id_producto: {id_sql_origen, id_vendedor, nombre_vendedor}} desde Mongo."""
    info = {}
    cursor = mongo_db["productos"].find(
        {"_id": {"$in": list(ids_producto)}},
        {"_id": 1, "id_sql_origen": 1, "vendedor": 1},
    )
    for doc in cursor:
        vendedor = doc.get("vendedor") or {}
        info[doc["_id"]] = {
            "id_sql_origen": doc.get("id_sql_origen"),
            "id_vendedor": vendedor.get("id_vendedor"),
            "nombre_vendedor": vendedor.get("nombre_comercial"),
        }
    return info


def sincronizar_vendedores(neo4j_driver, info_productos, ids_producto):
    filas = []
    for id_producto in sorted(ids_producto):
        datos = info_productos.get(id_producto)
        if not datos or datos["id_vendedor"] is None:
            continue
        filas.append({
            "id_producto": id_producto,
            "id_vendedor": int(datos["id_vendedor"]),
            "nombre_vendedor": datos["nombre_vendedor"],
        })
    query = """
        UNWIND $filas AS fila
        MATCH (p:Producto {id_producto: fila.id_producto})
        MERGE (v:Vendedor {id_vendedor: fila.id_vendedor})
          SET v.nombre = fila.nombre_vendedor
        SET p.id_vendedor = fila.id_vendedor
        MERGE (p)-[:VENDIDO_POR]->(v)
    """
    with neo4j_driver.session() as session:
        session.run(query, filas=filas).consume()
    sin_datos = len(ids_producto) - len(filas)
    print(f"[*] VENDIDO_POR asegurada para {len(filas)} producto(s)"
          + (f"; {sin_datos} sin documento/vendedor en Mongo (se omiten)" if sin_datos else ""))


def leer_compras_postgres(pg_conn):
    """Conjunto de (id_comprador, id_producto_sql) con al menos un pedido (cualquier estado)."""
    cursor = pg_conn.cursor()
    cursor.execute("""
        SELECT DISTINCT p.id_comprador, lp.id_producto
        FROM pedidos p
        JOIN lineas_pedido lp ON lp.id_pedido = p.id_pedido
    """)
    compras = {(fila[0], fila[1]) for fila in cursor.fetchall()}
    cursor.close()
    return compras


def sincronizar_compra_verificada(neo4j_driver, info_productos, compras):
    with neo4j_driver.session() as session:
        pares = _leer(session, """
            MATCH (c:Cuenta)-[r:CALIFICO]->(p:Producto)
            RETURN c.id_usuario AS id_usuario, p.id_producto AS id_producto
        """)
        filas = []
        for par in pares:
            datos = info_productos.get(par["id_producto"]) or {}
            id_sql = datos.get("id_sql_origen")
            verificada = id_sql is not None and (par["id_usuario"], id_sql) in compras
            filas.append({**par, "verificada": verificada})
        session.run("""
            UNWIND $filas AS fila
            MATCH (:Cuenta {id_usuario: fila.id_usuario})-[r:CALIFICO]->(:Producto {id_producto: fila.id_producto})
            SET r.compra_verificada = fila.verificada
        """, filas=filas).consume()
    verificadas = sum(1 for f in filas if f["verificada"])
    print(f"[*] compra_verificada recalculada en {len(filas)} reseña(s): "
          f"{verificadas} con compra, {len(filas) - verificadas} sin compra")


def leer_direcciones_postgres(pg_conn, ids_usuario):
    if not ids_usuario:
        return []
    cursor = pg_conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT id_usuario, direccion_linea1, ciudad, departamento_estado, codigo_postal
        FROM direcciones
        WHERE id_usuario = ANY(%s)
        ORDER BY id_usuario, id_direccion
    """, (list(ids_usuario),))
    filas = [dict(f) for f in cursor.fetchall()]
    cursor.close()
    return filas


def sincronizar_direcciones(neo4j_driver, direcciones):
    filas = [{
        "id_usuario": d["id_usuario"],
        "clave": clave_direccion(d["direccion_linea1"], d["ciudad"], d["codigo_postal"]),
        # Tal cual vienen de Postgres (mismo criterio que backend/app/grafo_fraude.py).
        "ciudad": d["ciudad"],
        "departamento": d["departamento_estado"],
    } for d in direcciones]
    query = """
        UNWIND $filas AS fila
        MATCH (c:Cuenta {id_usuario: fila.id_usuario})
        MERGE (d:Direccion {clave: fila.clave})
          SET d.ciudad = fila.ciudad, d.departamento = fila.departamento
        MERGE (c)-[:ENVIA_A]->(d)
    """
    with neo4j_driver.session() as session:
        session.run(query, filas=filas).consume()
    print(f"[*] ENVIA_A asegurada para {len(filas)} dirección(es) de cuentas del grafo")


def contar_grafo(neo4j_driver):
    consultas = {
        "Cuenta": "MATCH (n:Cuenta) RETURN count(n) AS n",
        "Producto": "MATCH (n:Producto) RETURN count(n) AS n",
        "Vendedor": "MATCH (n:Vendedor) RETURN count(n) AS n",
        "Direccion": "MATCH (n:Direccion) RETURN count(n) AS n",
        "CALIFICO": "MATCH ()-[r:CALIFICO]->() RETURN count(r) AS n",
        "CALIFICO con compra": "MATCH ()-[r:CALIFICO]->() WHERE r.compra_verificada = true RETURN count(r) AS n",
        "CALIFICO sin compra_verificada": "MATCH ()-[r:CALIFICO]->() WHERE r.compra_verificada IS NULL RETURN count(r) AS n",
        "VENDIDO_POR": "MATCH ()-[r:VENDIDO_POR]->() RETURN count(r) AS n",
        "ENVIA_A": "MATCH ()-[r:ENVIA_A]->() RETURN count(r) AS n",
    }
    with neo4j_driver.session() as session:
        return {nombre: session.run(q).single()["n"] for nombre, q in consultas.items()}


def imprimir_conteos(conteos, titulo):
    print(f"[*] {titulo}:")
    for nombre, valor in conteos.items():
        print(f"      {nombre}: {valor}")


def sincronizar_grafo(pg_conn, mongo_db, neo4j_driver):
    """Ejecuta los tres pasos de sincronización y devuelve los conteos finales del grafo."""
    asegurar_constraints(neo4j_driver)

    with neo4j_driver.session() as session:
        ids_producto = {f["id"] for f in _leer(session, "MATCH (p:Producto) RETURN p.id_producto AS id")}
        ids_cuenta = {f["id"] for f in _leer(session, "MATCH (c:Cuenta) RETURN c.id_usuario AS id")}
    print(f"[*] Grafo actual: {len(ids_cuenta)} cuenta(s), {len(ids_producto)} producto(s)")

    info_productos = leer_productos_mongo(mongo_db, ids_producto)
    sincronizar_vendedores(neo4j_driver, info_productos, ids_producto)

    compras = leer_compras_postgres(pg_conn)
    sincronizar_compra_verificada(neo4j_driver, info_productos, compras)

    direcciones = leer_direcciones_postgres(pg_conn, ids_cuenta)
    sincronizar_direcciones(neo4j_driver, direcciones)

    return contar_grafo(neo4j_driver)


def ejecutar():
    print("==================================================================")
    print(" SINCRONIZACIÓN DEL GRAFO DE FRAUDE AMPLIADO (Neo4j)")
    print("==================================================================")
    pg_conn, mongo_client, mongo_db, neo4j_driver = conectar_todo()
    try:
        imprimir_conteos(contar_grafo(neo4j_driver), "Conteos ANTES")
        conteos = sincronizar_grafo(pg_conn, mongo_db, neo4j_driver)
        imprimir_conteos(conteos, "Conteos DESPUÉS")
        print("[OK] Sincronización completada")
    finally:
        pg_conn.close()
        mongo_client.close()
        neo4j_driver.close()


if __name__ == "__main__":
    ejecutar()
