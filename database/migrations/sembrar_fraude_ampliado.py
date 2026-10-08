"""
Siembra de escenarios de fraude AMPLIADO (Mongo + Neo4j + Postgres) para la Entrega 3.

Propósito
---------
sembrar_resenas_fraude.py (Entrega 2) deja ruido legítimo, un anillo de fraude y un
anillo débil de control para la consulta original de anillos. Los 4 tipos de fraude
ampliado (cuenta_rafaga, grupo_coordinado, sesgo_vendedor_sin_compra y
cuentas_vinculadas) necesitan sus propios casos: este script siembra, para cada tipo, un
escenario POSITIVO (que el detector debe encontrar) y un CONTROL negativo (parecido, pero
bajo el umbral), para demostrar en el informe que cada umbral separa el fraude del
comportamiento normal. Hay casos con reseñas buenas Y malas.

| escenario             | tipo que prueba            | qué siembra                                        |
|-----------------------|----------------------------|----------------------------------------------------|
| promotor              | sesgo_vendedor (positivo)  | 1 cuenta, 5★ sin compra a 4 productos de UN        |
|                       |                            | vendedor, repartidas en 3 semanas                  |
| promotor_control      |                            | 1 cuenta, 5★ a solo 2 productos de un vendedor     |
| detractor             | sesgo_vendedor (negativo)  | 1 cuenta, 1★ sin compra a 4 productos de UN        |
|                       |                            | vendedor, repartidas en 3 semanas                  |
| detractor_control     |                            | 1 cuenta, 1★ a solo 2 productos de un vendedor     |
| vinculadas            | cuentas_vinculadas         | 3 cuentas con la MISMA dirección nueva (escrita    |
|                       |                            | con distintas mayúsculas/espacios, la clave        |
|                       |                            | normalizada las une), 5★ a los mismos 3 productos, |
|                       |                            | cada cuenta en un día distinto (> 6 h entre sí):   |
|                       |                            | ni el anillo original ni grupo_coordinado las ven  |
| vinculadas_control    |                            | 2 cuentas, misma dirección (familia), productos    |
|                       |                            | distintos                                          |
| grupo_negativo        | grupo_coordinado (neg.)    | 5 cuentas, 1★ a los mismos 3 productos (de 3       |
|                       |                            | vendedores distintos) en menos de 3 h              |
| grupo_positivo        | grupo_coordinado (pos.)    | 4 cuentas, 5★ a los mismos 2 productos en < 3 h;   |
|                       |                            | NO forma tríos del anillo original (pide 3)        |
| grupo_control         |                            | 4 cuentas, 5★ a los mismos 2 productos, en 2       |
|                       |                            | semanas (fuera de la ventana de 6 h)               |
| cuenta_rafaga         | cuenta_rafaga              | 1 cuenta, 8 reseñas variadas sin compra, en 40 min |
| cuenta_rafaga_control |                            | 1 cuenta, 8 reseñas variadas en 3 semanas          |

Las fechas y los productos están elegidos para que ningún escenario dispare OTRO tipo sin
querer (p. ej. los 3 productos de grupo_negativo son de vendedores distintos, para que las
3 reseñas 1★ de una misma cuenta no sean un sesgo_vendedor).

Cuentas: los escenarios usan 24 cuentas sin historial previo (si una cuenta del ruido
original participara, sus reseñas de ruido se sumarían a las del escenario y los
controles dejarían de ser controles). Por eso el script crea compradores REALES en
Postgres (contraseña `Tiendaya123!`, correos `@fraude-demo.tiendaya.gt`) con
`ON CONFLICT (email) DO NOTHING` y los busca después por email, nunca por ID fijo. No
toca a las cuentas de los anillos de sembrar_resenas_fraude.py. (Versiones anteriores de
este script sembraban 4 escenarios más con otras 15 cuentas @fraude-demo; esas cuentas
siguen en Postgres si ya se habían creado, pero sin reseñas: no se borran usuarios.)

Productos: reales y activos del catálogo de Mongo, elegidos en orden de (id_vendedor, _id)
entre los vendedores que todavía no tienen reseñas fuera de esta semilla (así el ruido
original no se mezcla con los escenarios "por vendedor"). Cada necesidad usa un vendedor
distinto.

Aditivo e idempotente
---------------------
NO borra `resenas` completa ni el subgrafo de la semilla original. Al inicio borra SOLO
lo suyo: reseñas de Mongo con `semilla: "fraude_ampliado"` (de cualquier escenario,
incluidos los que ya no se siembran), relaciones CALIFICO con `r.semilla =
"fraude_ampliado"` (y los nodos Producto/Vendedor/Cuenta que queden huérfanos por eso),
direcciones de Postgres cuya `direccion_linea2` empieza con `[semilla fraude_ampliado]`
y sus ENVIA_A. Los usuarios no se borran (se reutilizan).
Fechas relativas a "ahora" (últimos 30 días) con desplazamientos fijos y textos con
semilla fija: dos corridas seguidas dejan los mismos conteos.

Las reseñas de la semilla no tienen compra (estos usuarios no tienen pedidos), así que
quedan con compra_verificada = false. Al final corre sincronizar_grafo_fraude.py
(importado) para dejar Vendedor/VENDIDO_POR, compra_verificada y Direccion/ENVIA_A al día.

Orden si se vuelve a sembrar todo: sembrar_resenas_fraude.py (borra TODAS las reseñas,
incluidas estas) -> sincronizar_grafo_fraude.py -> sembrar_fraude_ampliado.py.

Uso:
    venv/Scripts/python database/migrations/sembrar_fraude_ampliado.py
"""
import os
import sys
import random
from datetime import datetime, timedelta, timezone

from psycopg2.extras import RealDictCursor

# sincronizar_grafo_fraude.py vive en esta misma carpeta (no es un paquete). Al
# importarlo también se cargan el .env y la salida UTF-8 de la consola.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sincronizar_grafo_fraude import (  # noqa: E402
    conectar_todo,
    clave_direccion,
    contar_grafo,
    imprimir_conteos,
    sincronizar_grafo,
)

# Guatemala usa UTC-6 fijo todo el año (mismo criterio que el resto de los scripts).
ZONA_GUATEMALA = timezone(timedelta(hours=-6))

SEMILLA = "fraude_ampliado"
MARCA_DIRECCION = "[semilla fraude_ampliado]"

# Mismo hash scrypt de "Tiendaya123!" que datos_semilla_usuarios.sql.
PASSWORD_HASH_SEMILLA = (
    "scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855"
    "f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64"
)

# Generador con semilla fija (solo para elegir textos): mismo resultado en cada corrida.
azar = random.Random(20261007)

# ============================================================================
# CUENTAS DE LOS ESCENARIOS (24 compradores nuevos, buscados por email)
# ============================================================================
CUENTAS_POR_ESCENARIO = {
    "promotor": [("Kevin Barrios", "kevin.barrios")],
    "promotor_control": [("Lucia Chinchilla", "lucia.chinchilla")],
    "vinculadas": [
        ("Julio Recinos", "julio.recinos"),
        ("Rosa Recinos", "rosa.recinos"),
        ("Mario Ajanel", "mario.ajanel"),
    ],
    "vinculadas_control": [
        ("Elena Batres", "elena.batres"),
        ("Tomas Batres", "tomas.batres"),
    ],
    "detractor": [("Gerson Alvarado", "gerson.alvarado")],
    "detractor_control": [("Patricia Solares", "patricia.solares")],
    "grupo_negativo": [
        ("Edgar Tzul", "edgar.tzul"),
        ("Yesenia Cabrera", "yesenia.cabrera"),
        ("Victor Hernandez", "victor.hernandez"),
        ("Leticia Xicara", "leticia.xicara"),
        ("Samuel Orellana", "samuel.orellana"),
    ],
    "grupo_positivo": [
        ("Fabiola Rosales", "fabiola.rosales"),
        ("Cristian Pac", "cristian.pac"),
        ("Monica Juarez", "monica.juarez"),
        ("Alejandro Funes", "alejandro.funes"),
    ],
    "grupo_control": [
        ("Wendy Paz", "wendy.paz"),
        ("Rene Sandoval", "rene.sandoval"),
        ("Gloria Cuxil", "gloria.cuxil"),
        ("Esteban Morales", "esteban.morales"),
    ],
    "cuenta_rafaga": [("Jonathan Ixcoy", "jonathan.ixcoy")],
    "cuenta_rafaga_control": [("Beatriz Ordonez", "beatriz.ordonez")],
}
DOMINIO_CORREO = "fraude-demo.tiendaya.gt"

# Direcciones compartidas. La de `vinculadas` se escribe distinto en cada cuenta
# (mayúsculas, espacios dobles) para demostrar que la clave normalizada las une.
DIRECCION_VINCULADAS = [
    "13 Calle 4-56 Zona 10",
    "13 calle 4-56  zona 10",
    "13 CALLE 4-56 Zona 10 ",
]
DIRECCION_VINCULADAS_DATOS = {"ciudad": "Guatemala", "departamento_estado": "Guatemala",
                              "codigo_postal": "01010", "linea2": "Apartamento 3B"}
DIRECCION_FAMILIA = "Calle Real 3-20 Lote 8, Colonia El Naranjo"
DIRECCION_FAMILIA_DATOS = {"ciudad": "Mixco", "departamento_estado": "Guatemala",
                           "codigo_postal": "01057", "linea2": "Casa familiar"}

LIMITE_DIRECCIONES = 3  # mismo límite que backend/app/blueprints/direcciones.py

# ============================================================================
# TEXTOS
# ============================================================================
TEXTOS = {
    "promotor": ["¡El mejor vendedor de Guatemala!", "Producto perfecto, compren aquí.",
                 "10/10, esta tienda nunca falla.", "Excelente, recomiendo toda la tienda."],
    "promotor_control": ["Muy buen producto, llegó a tiempo.", "Me gustó mucho, buena calidad."],
    "vinculadas": ["Excelente producto, súper recomendado.", "Muy bueno, cinco estrellas.",
                   "Me encantó, lo volvería a comprar."],
    "vinculadas_control": ["Buen producto, cumple lo prometido.", "Está bien por el precio.",
                           "Llegó bien, algo tardado el envío."],
    "detractor": ["Esta tienda es un fraude.", "No le compren a este vendedor.",
                  "Pésimo como todo lo de esta tienda.", "Malo, malo, malo."],
    "detractor_control": ["No me gustó, esperaba más.", "Se dañó pronto, no lo recomiendo."],
    "grupo_negativo": ["Horrible, no sirve.", "Basura, no lo compren.", "Pésimo producto.",
                       "Cero estrellas si se pudiera."],
    "grupo_positivo": ["¡Buenísimo!", "Excelente, 5 estrellas.", "Lo recomiendo 100%.",
                       "Perfecto, cómprenlo."],
    "grupo_control": ["Muy contento con la compra.", "Buen producto, llegó bien.",
                      "Excelente relación calidad-precio."],
    "cuenta_rafaga": ["Bueno.", "Regular.", "Malo.", "Está bien.", "No me gustó.", "Excelente."],
    "cuenta_rafaga_control": ["Buen producto, lo uso a diario.", "Regular, cumple lo básico.",
                              "No era lo que esperaba.", "Muy buena compra."],
}


def texto(escenario):
    return azar.choice(TEXTOS[escenario])


# ============================================================================
# LIMPIEZA (solo lo de esta semilla)
# ============================================================================
def limpiar_semilla_previa(pg_conn, mongo_db, neo4j_driver):
    """Borra SOLO lo sembrado por una corrida anterior de este script."""
    borradas = mongo_db["resenas"].delete_many({"semilla": SEMILLA}).deleted_count
    print(f"[*] Limpieza Mongo: {borradas} reseña(s) previas de la semilla '{SEMILLA}' eliminadas")

    with neo4j_driver.session() as session:
        fila = session.run("""
            MATCH (c:Cuenta)-[r:CALIFICO {semilla: $semilla}]->(p:Producto)
            WITH collect(DISTINCT c.id_usuario) AS cuentas, collect(DISTINCT p.id_producto) AS productos,
                 collect(r) AS rels
            FOREACH (r IN rels | DELETE r)
            RETURN cuentas, productos, size(rels) AS n
        """, semilla=SEMILLA).single()
        cuentas = fila["cuentas"] if fila else []
        productos = fila["productos"] if fila else []
        n_rels = fila["n"] if fila else 0

        # Productos que quedaron sin ninguna reseña por la limpieza: los trajo esta semilla.
        vendedores = [r["id"] for r in session.run("""
            MATCH (p:Producto)-[:VENDIDO_POR]->(v:Vendedor)
            WHERE p.id_producto IN $productos AND NOT (p)<-[:CALIFICO]-()
            RETURN DISTINCT v.id_vendedor AS id
        """, productos=productos)]
        n_productos = session.run("""
            MATCH (p:Producto) WHERE p.id_producto IN $productos AND NOT (p)<-[:CALIFICO]-()
            DETACH DELETE p
            RETURN count(*) AS n
        """, productos=productos).single()["n"]
        n_vendedores = session.run("""
            MATCH (v:Vendedor) WHERE v.id_vendedor IN $vendedores AND NOT (v)<-[:VENDIDO_POR]-()
            DELETE v
            RETURN count(*) AS n
        """, vendedores=vendedores).single()["n"]
        n_cuentas = session.run("""
            MATCH (c:Cuenta) WHERE c.id_usuario IN $cuentas AND NOT (c)-[:CALIFICO]->()
            DETACH DELETE c
            RETURN count(*) AS n
        """, cuentas=cuentas).single()["n"]
    print(f"[*] Limpieza Neo4j: {n_rels} CALIFICO de la semilla eliminadas; nodos huérfanos eliminados: "
          f"{n_productos} Producto, {n_vendedores} Vendedor, {n_cuentas} Cuenta")

    cursor = pg_conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT d.id_direccion, d.id_usuario, d.direccion_linea1, d.ciudad, d.codigo_postal,
               EXISTS (SELECT 1 FROM pedidos p WHERE p.id_direccion_envio = d.id_direccion) AS usada
        FROM direcciones d
        WHERE d.direccion_linea2 LIKE %s
        ORDER BY d.id_direccion
    """, (MARCA_DIRECCION + "%",))
    direcciones = [dict(f) for f in cursor.fetchall()]
    borrables = [d for d in direcciones if not d["usada"]]
    usadas = [d for d in direcciones if d["usada"]]
    if borrables:
        cursor.execute("DELETE FROM direcciones WHERE id_direccion = ANY(%s)",
                       ([d["id_direccion"] for d in borrables],))
    pg_conn.commit()
    if usadas:
        print(f"[*] {len(usadas)} dirección(es) de la semilla ya se usaron en un pedido: se conservan")

    # Quita las ENVIA_A de esas direcciones, salvo que la cuenta conserve otra dirección
    # con la misma clave; y el nodo Direccion si ya ninguna cuenta lo usa.
    ids = list({d["id_usuario"] for d in borrables})
    restantes = set()
    if ids:
        cursor.execute("SELECT id_usuario, direccion_linea1, ciudad, codigo_postal FROM direcciones "
                       "WHERE id_usuario = ANY(%s)", (ids,))
        restantes = {(f["id_usuario"], clave_direccion(f["direccion_linea1"], f["ciudad"], f["codigo_postal"]))
                     for f in cursor.fetchall()}
    cursor.close()
    quitar = []
    for d in borrables:
        par = (d["id_usuario"], clave_direccion(d["direccion_linea1"], d["ciudad"], d["codigo_postal"]))
        if par not in restantes:
            quitar.append({"id_usuario": par[0], "clave": par[1]})
    with neo4j_driver.session() as session:
        session.run("""
            UNWIND $quitar AS q
            MATCH (:Cuenta {id_usuario: q.id_usuario})-[e:ENVIA_A]->(:Direccion {clave: q.clave})
            DELETE e
        """, quitar=quitar).consume()
        session.run("""
            MATCH (d:Direccion) WHERE d.clave IN $claves AND NOT (d)<-[:ENVIA_A]-()
            DELETE d
        """, claves=[q["clave"] for q in quitar]).consume()
    print(f"[*] Limpieza Postgres: {len(borrables)} dirección(es) de la semilla eliminadas "
          f"({len(quitar)} ENVIA_A quitadas del grafo)")


# ============================================================================
# CUENTAS
# ============================================================================
def asegurar_cuentas(pg_conn):
    """Crea (si faltan) los 24 compradores de los escenarios y devuelve {escenario: [cuentas]}."""
    cursor = pg_conn.cursor(cursor_factory=RealDictCursor)
    numero = 0
    for cuentas in CUENTAS_POR_ESCENARIO.values():
        for nombre, usuario in cuentas:
            numero += 1
            cursor.execute("""
                INSERT INTO usuarios (nombre, email, password_hash, rol, telefono)
                VALUES (%s, %s, %s, 'comprador', %s)
                ON CONFLICT (email) DO NOTHING
            """, (nombre, f"{usuario}@{DOMINIO_CORREO}", PASSWORD_HASH_SEMILLA, f"+5025557{numero:04d}"))
    pg_conn.commit()

    resultado = {}
    for escenario, cuentas in CUENTAS_POR_ESCENARIO.items():
        resultado[escenario] = []
        for _, usuario in cuentas:
            cursor.execute("SELECT id_usuario, nombre, rol FROM usuarios WHERE email = %s",
                           (f"{usuario}@{DOMINIO_CORREO}",))
            fila = cursor.fetchone()
            if fila is None or fila["rol"] != "comprador":
                print(f"[X] La cuenta {usuario}@{DOMINIO_CORREO} no existe o no es comprador")
                sys.exit(1)
            resultado[escenario].append(dict(fila))
    cursor.close()
    return resultado


def autores_fuera_de_la_semilla(mongo_db):
    """id_usuario de todos los autores de reseñas que no son de esta semilla (ruido, anillos, pruebas)."""
    return set(mongo_db["resenas"].distinct("autor.id_usuario", {"semilla": {"$ne": SEMILLA}}))


# ============================================================================
# PRODUCTOS
# ============================================================================
def elegir_productos(mongo_db):
    """
    Elige, en orden determinístico (id_vendedor, _id), los productos de cada escenario
    entre los vendedores que no tienen reseñas fuera de esta semilla, un vendedor
    distinto por escenario. Devuelve {clave: [productos]}.
    """
    resenados = set(mongo_db["resenas"].distinct("producto_id", {"semilla": {"$ne": SEMILLA}}))
    productos = list(mongo_db["productos"].find(
        {"activo": True},
        {"_id": 1, "nombre": 1, "sku": 1, "id_sql_origen": 1, "vendedor": 1},
    ).sort("_id", 1))

    vendedores_con_resenas = {(p.get("vendedor") or {}).get("id_vendedor") for p in productos
                              if p["_id"] in resenados}
    por_vendedor = {}
    for p in productos:
        id_v = (p.get("vendedor") or {}).get("id_vendedor")
        if id_v is None or id_v in vendedores_con_resenas:
            continue
        por_vendedor.setdefault(id_v, []).append(p)

    # Un vendedor distinto por cada necesidad, en orden de id_vendedor.
    necesidades = [
        ("promotor", 4),
        ("promotor_control", 2),
        ("vinculadas_1", 1),
        ("vinculadas_2", 1),
        ("vinculadas_3", 1),
        ("vinculadas_control_1", 2),
        ("vinculadas_control_2", 2),
        ("detractor", 4),
        ("detractor_control", 2),
        ("grupo_negativo_1", 1),
        ("grupo_negativo_2", 1),
        ("grupo_negativo_3", 1),
        ("grupo_positivo", 2),
        ("grupo_control", 2),
        ("cuenta_rafaga_1", 2),
        ("cuenta_rafaga_2", 2),
        ("cuenta_rafaga_3", 2),
        ("cuenta_rafaga_4", 2),
        ("cuenta_rafaga_control_1", 2),
        ("cuenta_rafaga_control_2", 2),
        ("cuenta_rafaga_control_3", 2),
        ("cuenta_rafaga_control_4", 2),
    ]
    elegidos = {}
    restantes = sorted(por_vendedor)
    for clave, cantidad in necesidades:
        id_v = next((v for v in restantes if len(por_vendedor[v]) >= cantidad), None)
        if id_v is None:
            print(f"[X] No hay vendedores sin reseñas suficientes para '{clave}'.")
            sys.exit(1)
        restantes.remove(id_v)
        elegidos[clave] = por_vendedor[id_v][:cantidad]

    # Los 3 productos de `vinculadas` son de 3 vendedores distintos a propósito: así
    # ninguna de esas cuentas suma 3 reseñas 5★ a un mismo vendedor (no es promotor).
    elegidos["vinculadas"] = elegidos.pop("vinculadas_1") + elegidos.pop("vinculadas_2") + elegidos.pop("vinculadas_3")
    # grupo_negativo: 3 vendedores distintos, para que 3 reseñas 1★ de una misma cuenta no
    # sumen a un mismo vendedor (no es un sesgo_vendedor).
    elegidos["grupo_negativo"] = [p for k in (1, 2, 3) for p in elegidos.pop(f"grupo_negativo_{k}")]
    # cuenta_rafaga(_control): 8 productos de 4 vendedores (2 por vendedor < mínimo de 3 del
    # sesgo_vendedor, y además con calificaciones mezcladas).
    for base in ("cuenta_rafaga", "cuenta_rafaga_control"):
        elegidos[base] = [p for k in (1, 2, 3, 4) for p in elegidos.pop(f"{base}_{k}")]
    return elegidos


# ============================================================================
# DIRECCIONES
# ============================================================================
def insertar_direccion(pg_conn, id_usuario, linea1, datos):
    """Agrega una dirección marcada, respetando el máximo de 3 por usuario."""
    cursor = pg_conn.cursor()
    linea2 = f"{MARCA_DIRECCION} {datos['linea2']}"
    cursor.execute("SELECT count(*) FROM direcciones WHERE id_usuario = %s", (id_usuario,))
    cantidad = cursor.fetchone()[0]
    cursor.execute("""
        SELECT 1 FROM direcciones
        WHERE id_usuario = %s AND direccion_linea1 = %s AND direccion_linea2 = %s
    """, (id_usuario, linea1, linea2))
    if cursor.fetchone():
        cursor.close()
        return  # quedó conservada (se usó en un pedido)
    if cantidad >= LIMITE_DIRECCIONES:
        print(f"[X] id_usuario={id_usuario} ya tiene {LIMITE_DIRECCIONES} direcciones; se omite la sembrada")
        cursor.close()
        return
    cursor.execute("""
        INSERT INTO direcciones (id_usuario, direccion_linea1, direccion_linea2, ciudad,
                                 departamento_estado, codigo_postal, es_principal)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (id_usuario, linea1, linea2, datos["ciudad"], datos["departamento_estado"],
          datos["codigo_postal"], cantidad == 0))
    pg_conn.commit()
    cursor.close()


# ============================================================================
# RESEÑAS
# ============================================================================
def insertar_resena(mongo_db, neo4j_driver, *, escenario, producto, cuenta, calificacion, fecha):
    """Inserta en Mongo y espeja en Neo4j con el mismo MERGE que resenas.py, más semilla/escenario."""
    if mongo_db["resenas"].find_one({"producto_id": producto["_id"], "autor.id_usuario": cuenta["id_usuario"]}):
        print(f"[X] Par ya reseñado fuera de la semilla, se omite: {producto['_id']} / {cuenta['id_usuario']}")
        return False
    doc = {
        "producto_id": producto["_id"],
        "id_sql_origen_producto": producto.get("id_sql_origen"),
        "autor": {"id_usuario": cuenta["id_usuario"], "nombre": cuenta["nombre"], "rol": "comprador"},
        "calificacion": calificacion,
        "texto": texto(escenario),
        "fecha_creacion": fecha,
        "semilla": SEMILLA,
        "escenario": escenario,
    }
    resultado = mongo_db["resenas"].insert_one(doc)
    with neo4j_driver.session() as session:
        session.run("""
            MERGE (c:Cuenta {id_usuario: $id_usuario})
              SET c.nombre = $nombre, c.rol = 'comprador'
            MERGE (p:Producto {id_producto: $producto_id})
              SET p.nombre = $nombre_producto, p.sku = $sku
            MERGE (c)-[r:CALIFICO]->(p)
              SET r.calificacion = $calificacion, r.fecha = $fecha, r.id_resena = $id_resena,
                  r.compra_verificada = false, r.semilla = $semilla, r.escenario = $escenario
        """, id_usuario=cuenta["id_usuario"], nombre=cuenta["nombre"], producto_id=producto["_id"],
            nombre_producto=producto.get("nombre"), sku=producto.get("sku"), calificacion=calificacion,
            fecha=fecha.isoformat(), id_resena=str(resultado.inserted_id), semilla=SEMILLA,
            escenario=escenario).consume()
    return True


def a_las(ahora, dias_atras, hora, minuto=0):
    """Hace `dias_atras` días, a la hora indicada (hora de Guatemala)."""
    return (ahora - timedelta(days=dias_atras)).replace(hour=hora, minute=minuto, second=0, microsecond=0)


def planificar(cuentas, productos, ahora):
    """Lista (escenario, producto, cuenta, calificacion, fecha) de todas las reseñas de la semilla."""
    plan = []

    # promotor: 4 productos del vendedor promovido, 5★, repartidas en 3 semanas.
    for producto, dias in zip(productos["promotor"], [26, 19, 12, 5]):
        plan.append(("promotor", producto, cuentas["promotor"][0], 5, a_las(ahora, dias, 10, 15)))

    # promotor_control: solo 2 productos de un vendedor (bajo el mínimo de 3).
    for producto, dias in zip(productos["promotor_control"], [22, 9]):
        plan.append(("promotor_control", producto, cuentas["promotor_control"][0], 5, a_las(ahora, dias, 16, 40)))

    # vinculadas: misma dirección, los mismos 3 productos con 5★; cada cuenta en su propio
    # día (7 días entre cuentas, mucho más que 6 h), así ni el anillo original ni
    # grupo_coordinado las unen.
    for cuenta, dias, hora in zip(cuentas["vinculadas"], [24, 17, 10], [9, 15, 20]):
        for i, producto in enumerate(productos["vinculadas"]):
            plan.append(("vinculadas", producto, cuenta, 5, a_las(ahora, dias, hora, 10 * i)))

    # vinculadas_control: familia en la misma casa que califica productos distintos.
    for cuenta, clave, dias, notas in zip(cuentas["vinculadas_control"],
                                          ["vinculadas_control_1", "vinculadas_control_2"],
                                          [(27, 13), (20, 6)], [(5, 4), (4, 3)]):
        for producto, d, nota in zip(productos[clave], dias, notas):
            plan.append(("vinculadas_control", producto, cuenta, nota, a_las(ahora, d, 19, 45)))

    # detractor: 1★ sin compra a 4 productos de UN vendedor, repartidas en 3 semanas.
    for producto, dias in zip(productos["detractor"], [27, 20, 13, 6]):
        plan.append(("detractor", producto, cuentas["detractor"][0], 1, a_las(ahora, dias, 18, 20)))

    # detractor_control: 1★ a solo 2 productos de un vendedor (bajo el mínimo de 3).
    for producto, dias in zip(productos["detractor_control"], [23, 11]):
        plan.append(("detractor_control", producto, cuentas["detractor_control"][0], 1, a_las(ahora, dias, 8, 50)))

    # grupo_negativo: 5 cuentas, 1★ a los mismos 3 productos. Cuenta i, producto j a los
    # i*40 + j*5 minutos: todo en 170 min (< 3 h); cada cuenta hace solo 3 reseñas (no es
    # una cuenta_rafaga, que pide 5).
    base = a_las(ahora, 4, 14, 0)
    for i, cuenta in enumerate(cuentas["grupo_negativo"]):
        for j, producto in enumerate(productos["grupo_negativo"]):
            plan.append(("grupo_negativo", producto, cuenta, 1, base + timedelta(minutes=40 * i + 5 * j)))

    # grupo_positivo: 4 cuentas, 5★ a los mismos 2 productos, cuenta i a los i*45 (+10)
    # minutos: 145 min en total. Solo 2 productos en común: la consulta original de
    # anillos (que pide 3) no lo ve.
    base = a_las(ahora, 6, 10, 0)
    for i, cuenta in enumerate(cuentas["grupo_positivo"]):
        for j, producto in enumerate(productos["grupo_positivo"]):
            plan.append(("grupo_positivo", producto, cuenta, 5, base + timedelta(minutes=45 * i + 10 * j)))

    # grupo_control: 4 cuentas, 5★ a los mismos 2 productos, una cuenta cada ~4 días.
    for cuenta, dias in zip(cuentas["grupo_control"], [15, 11, 7, 2]):
        for j, producto in enumerate(productos["grupo_control"]):
            plan.append(("grupo_control", producto, cuenta, 5, a_las(ahora, dias, 12, 20 * j)))

    # cuenta_rafaga: 8 reseñas variadas sin compra a 8 productos en 39 minutos.
    for producto, minuto, nota in zip(productos["cuenta_rafaga"], [0, 5, 9, 15, 21, 26, 33, 39],
                                      [5, 3, 1, 4, 2, 5, 4, 3]):
        plan.append(("cuenta_rafaga", producto, cuentas["cuenta_rafaga"][0], nota,
                     a_las(ahora, 1, 22, 0) + timedelta(minutes=minuto)))

    # cuenta_rafaga_control: 8 reseñas variadas repartidas en 3 semanas.
    for producto, dias, nota in zip(productos["cuenta_rafaga_control"], [21, 18, 15, 12, 9, 6, 4, 2],
                                    [4, 5, 3, 2, 5, 4, 1, 3]):
        plan.append(("cuenta_rafaga_control", producto, cuentas["cuenta_rafaga_control"][0], nota,
                     a_las(ahora, dias, 17, 0)))

    return plan


# ============================================================================
# PRINCIPAL
# ============================================================================
def ejecutar_siembra():
    print("==================================================================")
    print(" SIEMBRA DE ESCENARIOS DE FRAUDE AMPLIADO (Mongo + Neo4j + Postgres)")
    print("==================================================================")
    pg_conn, mongo_client, mongo_db, neo4j_driver = conectar_todo()
    try:
        imprimir_conteos(contar_grafo(neo4j_driver), "Grafo ANTES")

        # --- Paso 1: limpiar solo lo de una corrida anterior ---
        limpiar_semilla_previa(pg_conn, mongo_db, neo4j_driver)

        # --- Paso 2: cuentas y productos (reales, por email / en orden) ---
        cuentas = asegurar_cuentas(pg_conn)
        con_historial = autores_fuera_de_la_semilla(mongo_db)
        chocan = [c["id_usuario"] for lista in cuentas.values() for c in lista if c["id_usuario"] in con_historial]
        if chocan:
            print(f"[X] ADVERTENCIA: cuentas de la semilla con reseñas fuera de ella "
                  f"(pueden alterar los controles): {chocan}")
        productos = elegir_productos(mongo_db)

        # --- Paso 3: direcciones compartidas ---
        for cuenta, linea1 in zip(cuentas["vinculadas"], DIRECCION_VINCULADAS):
            insertar_direccion(pg_conn, cuenta["id_usuario"], linea1, DIRECCION_VINCULADAS_DATOS)
        for cuenta in cuentas["vinculadas_control"]:
            insertar_direccion(pg_conn, cuenta["id_usuario"], DIRECCION_FAMILIA, DIRECCION_FAMILIA_DATOS)

        # --- Paso 4: reseñas (Mongo + Neo4j) ---
        insertadas = {}
        for escenario, producto, cuenta, calificacion, fecha in planificar(
                cuentas, productos, datetime.now(ZONA_GUATEMALA)):
            if insertar_resena(mongo_db, neo4j_driver, escenario=escenario, producto=producto,
                               cuenta=cuenta, calificacion=calificacion, fecha=fecha):
                insertadas[escenario] = insertadas.get(escenario, 0) + 1

        # --- Paso 5: completar el grafo (Vendedor, compra_verificada, Direccion) ---
        print("[*] Sincronizando el grafo (lógica de sincronizar_grafo_fraude.py)...")
        conteos = sincronizar_grafo(pg_conn, mongo_db, neo4j_driver)

        print("==================================================================")
        print(" RESUMEN DE LA SIEMBRA")
        print("==================================================================")
        productos_por_escenario = {
            "promotor": productos["promotor"],
            "promotor_control": productos["promotor_control"],
            "vinculadas": productos["vinculadas"],
            "vinculadas_control": productos["vinculadas_control_1"] + productos["vinculadas_control_2"],
            "detractor": productos["detractor"],
            "detractor_control": productos["detractor_control"],
            "grupo_negativo": productos["grupo_negativo"],
            "grupo_positivo": productos["grupo_positivo"],
            "grupo_control": productos["grupo_control"],
            "cuenta_rafaga": productos["cuenta_rafaga"],
            "cuenta_rafaga_control": productos["cuenta_rafaga_control"],
        }
        for escenario, lista in cuentas.items():
            print(f"[*] {escenario}: {insertadas.get(escenario, 0)} reseña(s)")
            print(f"      cuentas: {', '.join(str(c['id_usuario']) + ' ' + c['nombre'] for c in lista)}")
            for p in productos_por_escenario[escenario]:
                v = p.get("vendedor") or {}
                print(f"      - {p['_id']} (vendedor {v.get('id_vendedor')} {v.get('nombre_comercial')}): {p.get('nombre')}")
        print(f"[*] Reseñas de la semilla en Mongo: {mongo_db['resenas'].count_documents({'semilla': SEMILLA})}; "
              f"reseñas totales: {mongo_db['resenas'].count_documents({})}")
        imprimir_conteos(conteos, "Grafo DESPUÉS")
        print("[OK] Siembra completada")
    finally:
        pg_conn.close()
        mongo_client.close()
        neo4j_driver.close()


if __name__ == "__main__":
    ejecutar_siembra()
