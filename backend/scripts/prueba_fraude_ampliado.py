"""
Evidencia de la detección de fraude ampliada (Neo4j).

Standalone: se corre contra el servidor real (python backend/main.py) después
de sembrar los escenarios con database/migrations/sembrar_fraude_ampliado.py.
Lee de Mongo las reseñas con `semilla: "fraude_ampliado"` para saber qué
cuentas/productos tiene cada escenario (nunca IDs fijos) y verifica contra la
API:

Los 4 tipos de fraude son, en este orden: cuenta_rafaga, grupo_coordinado,
sesgo_vendedor_sin_compra y cuentas_vinculadas.

  F1  Cada escenario positivo aparece en su patrón (cuenta_rafaga; grupo_negativo
      y grupo_positivo en grupo_coordinado con su tamaño y signo; promotor y
      detractor en sesgo_vendedor_sin_compra con su signo; vinculadas en
      cuentas_vinculadas).
  F2  Cada control negativo NO aparece en su patrón.
  F3  Lo que agregan los patrones nuevos sobre el anillo de la Entrega 2: ni
      las cuentas `vinculadas` (reseñas espaciadas) ni el `grupo_positivo`
      (solo 2 productos en común) aparecen en los tríos de GET /api/fraude/alertas.
  F4  GET /api/fraude/alertas (Entrega 2) sigue igual: mismo formato y los
      tríos del anillo fuerte de la semilla original; además grupo_coordinado
      ve ese anillo como un solo grupo.
  F5  Errores: 403 sin rol administrador, 404 tipo inexistente (incluidos los
      eliminados promotor_sin_compra, anillo_resenas, ataque_competencia y
      rafaga_producto), 400 parámetro inválido. /patrones lista los 4 tipos
      en orden con sus defaults.
  F6  /resumen incluye las cuentas positivas, con nivel y sus patrones.
  F7  Crear una reseña por la API deja en Neo4j CALIFICO.compra_verificada
      (igual al verificada_compra del listado) y Producto-[:VENDIDO_POR]->
      Vendedor; el listado de reseñas sigue funcionando. Se limpia al final.
  F8  Crear/editar/borrar una dirección por la API sincroniza ENVIA_A
      (clave normalizada) y no deja nodos huérfanos. Se limpia al final.

Uso:
    venv\\Scripts\\python.exe backend/scripts/prueba_fraude_ampliado.py
"""

import os
import sys
import time
from itertools import combinations

import psycopg2
import requests
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pymongo import MongoClient
from bson import ObjectId

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

API = "http://127.0.0.1:8000/api"
ADMIN = {"rol_solicitante": "administrador"}
TIPOS = ["cuenta_rafaga", "grupo_coordinado", "sesgo_vendedor_sin_compra", "cuentas_vinculadas"]
TIPOS_ELIMINADOS = ["anillo_resenas", "ataque_competencia", "rafaga_producto", "promotor_sin_compra"]

ESCENARIOS = ["promotor", "promotor_control", "detractor", "detractor_control",
              "grupo_negativo", "grupo_positivo", "grupo_control", "cuenta_rafaga", "cuenta_rafaga_control",
              "vinculadas", "vinculadas_control"]

PG_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DBNAME", "tiendaya_db"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "root"),
}

# Textos del anillo fuerte de sembrar_resenas_fraude.py (Entrega 2): así se
# reconoce a sus cuentas sin depender de IDs fijos.
FRASES_ANILLO_E2 = {"Excelente producto!", "Muy recomendado, 100%", "Increíble calidad"}

resultados = []


def verificar(caso, descripcion, condicion, detalle=""):
    resultados.append((caso, descripcion, bool(condicion)))
    print(f"   [{'OK  ' if condicion else 'FALLA'}] {descripcion}" + (f"  ({detalle})" if detalle else ""))


def get(ruta, **params):
    return requests.get(f"{API}{ruta}", params=params, timeout=30)


def alertas(tipo):
    r = get(f"/fraude/alertas/{tipo}", **ADMIN)
    r.raise_for_status()
    return r.json()["alertas"]


def ids_cuentas(alerta):
    return {c["id_usuario"] for c in alerta["cuentas"]}


def ids_productos(alerta):
    return {p["id_producto"] for p in alerta["productos"]}


def normalizar(s):
    return " ".join((s or "").lower().split())


def escenarios_semilla(mongo_db):
    esc = {}
    for r in mongo_db["resenas"].find({"semilla": "fraude_ampliado"}):
        e = esc.setdefault(r["escenario"], {"cuentas": set(), "productos": set()})
        e["cuentas"].add(r["autor"]["id_usuario"])
        e["productos"].add(r["producto_id"])
    return esc


def anillo_e2(mongo_db):
    return {r["autor"]["id_usuario"] for r in mongo_db["resenas"].find(
        {"texto": {"$in": list(FRASES_ANILLO_E2)}, "semilla": {"$exists": False}})}


def trios_endpoint_original():
    r = get("/fraude/alertas", **ADMIN)
    r.raise_for_status()
    return [{c["id_usuario"] for c in a["cuentas_involucradas"]} for a in r.json()["alertas"]]


def caso_escenarios(mongo_db, esc):
    print("\n[F1/F2] Escenarios de la semilla: positivos detectados, controles no")
    faltan = [n for n in ESCENARIOS if n not in esc]
    verificar("F1", f"La semilla fraude_ampliado tiene los {len(ESCENARIOS)} escenarios", not faltan,
              f"faltan: {faltan}" if faltan else "")
    if faltan:
        return

    def detalle(hit):
        return f"score {hit[0]['score']} {hit[0]['nivel']}" if hit else ""

    # sesgo hacia un vendedor (promotor = positivo, detractor = negativo)
    a_ses = alertas("sesgo_vendedor_sin_compra")
    for nombre, signo in (("promotor", "positivo"), ("detractor", "negativo")):
        e = esc[nombre]
        hit = [a for a in a_ses if e["cuentas"] <= ids_cuentas(a) and e["productos"] <= ids_productos(a)
               and a["evidencia"]["signo"] == signo]
        verificar("F1", f"{nombre} aparece en sesgo_vendedor_sin_compra con signo {signo}", hit, detalle(hit))
        e = esc[f"{nombre}_control"]
        hit = [a for a in a_ses if e["cuentas"] & ids_cuentas(a) and e["productos"] & ids_productos(a)]
        verificar("F2", f"{nombre}_control (solo 2 reseñas) NO aparece en sesgo_vendedor_sin_compra", not hit)

    # grupos coordinados de cualquier tamaño
    a_gru = alertas("grupo_coordinado")
    for nombre, signo in (("grupo_negativo", "negativo"), ("grupo_positivo", "positivo")):
        e = esc[nombre]
        hit = [a for a in a_gru if e["cuentas"] <= ids_cuentas(a) and a["evidencia"]["signo"] == signo]
        verificar("F1", f"{nombre} aparece en grupo_coordinado como UN grupo de {len(e['cuentas'])} ({signo})",
                  hit and hit[0]["evidencia"]["tamano"] == len(e["cuentas"]),
                  (detalle(hit) + f", tamaño {hit[0]['evidencia']['tamano']}") if hit else "")
    e = esc["grupo_control"]
    hit = [a for a in a_gru if len(e["cuentas"] & ids_cuentas(a)) >= 2]
    verificar("F2", "grupo_control (mismos productos, repartido en semanas) NO aparece en grupo_coordinado", not hit)

    # una cuenta en ráfaga
    a_cra = alertas("cuenta_rafaga")
    e = esc["cuenta_rafaga"]
    hit = [a for a in a_cra if e["cuentas"] <= ids_cuentas(a)]
    verificar("F1", "cuenta_rafaga aparece en cuenta_rafaga", hit,
              (detalle(hit) + f", {hit[0]['evidencia']['resenas']} reseñas en "
               f"{hit[0]['evidencia']['ventana_real_minutos']} min") if hit else "")
    e = esc["cuenta_rafaga_control"]
    hit = [a for a in a_cra if e["cuentas"] & ids_cuentas(a)]
    verificar("F2", "cuenta_rafaga_control (repartida en semanas) NO aparece en cuenta_rafaga", not hit)

    # vinculadas
    a_vin = alertas("cuentas_vinculadas")
    e = esc["vinculadas"]
    hit = [a for a in a_vin if e["cuentas"] <= ids_cuentas(a)]
    verificar("F1", f"vinculadas ({len(e['cuentas'])} cuentas, misma dirección) aparece en cuentas_vinculadas", hit,
              f"score {hit[0]['score']} {hit[0]['nivel']}, {hit[0]['evidencia'].get('ciudad')}" if hit else "")
    e = esc["vinculadas_control"]
    hit = [a for a in a_vin if len(e["cuentas"] & ids_cuentas(a)) >= 2]
    verificar("F2", "vinculadas_control (familia, productos distintos) NO aparece en cuentas_vinculadas", not hit)

    print("\n[F3] Lo que agregan los patrones nuevos sobre el anillo original (GET /api/fraude/alertas)")
    trios = trios_endpoint_original()
    e = esc["vinculadas"]
    hit = [t for t in trios if len(e["cuentas"] & t) >= 2]
    verificar("F3", "las cuentas vinculadas NO aparecen juntas en el anillo original (reseñas espaciadas > 6 h)", not hit)
    e = esc["grupo_positivo"]
    hit = [t for t in trios if len(e["cuentas"] & t) >= 2]
    verificar("F3", "grupo_positivo NO aparece en el anillo original (comparte solo 2 productos)", not hit)


def caso_endpoint_original(mongo_db):
    print("\n[F4] GET /api/fraude/alertas (Entrega 2) sin cambios")
    r = get("/fraude/alertas", **ADMIN)
    verificar("F4", "responde 200", r.status_code == 200, str(r.status_code))
    if r.status_code != 200:
        return
    d = r.json()
    verificar("F4", "mismo formato {alertas, total, parametros}",
              set(d) == {"alertas", "total", "parametros"}
              and d["parametros"] == {"min_productos_compartidos": 3, "ventana_segundos": 21600}
              and all(set(a) == {"cuentas_involucradas", "productos_compartidos", "score_anomalia"} for a in d["alertas"]))
    trios_orig = {frozenset(c["id_usuario"] for c in a["cuentas_involucradas"]) for a in d["alertas"]}

    anillo = anillo_e2(mongo_db)
    esperados = {frozenset(t) for t in combinations(sorted(anillo), 3)} if len(anillo) >= 3 else set()
    verificar("F4", f"incluye los {len(esperados)} tríos del anillo fuerte de la semilla original",
              esperados and esperados <= trios_orig, f"cuentas del anillo: {sorted(anillo)}")

    hit = [a for a in alertas("grupo_coordinado") if anillo and anillo <= ids_cuentas(a)
           and a["evidencia"]["signo"] == "positivo"]
    verificar("F4", f"grupo_coordinado ve el anillo de la Entrega 2 ({len(anillo)} cuentas) como un solo grupo positivo",
              hit, f"score {hit[0]['score']}, tamaño {hit[0]['evidencia']['tamano']}" if hit else "")


def caso_errores():
    print("\n[F5] Contrato y errores")
    for ruta in ("/fraude/patrones", "/fraude/alertas/grupo_coordinado", "/fraude/resumen"):
        r1 = get(ruta)
        r2 = get(ruta, rol_solicitante="comprador")
        verificar("F5", f"{ruta} sin rol administrador -> 403", r1.status_code == 403 and r2.status_code == 403,
                  f"{r1.status_code}/{r2.status_code}")
    for tipo in ["no_existe"] + TIPOS_ELIMINADOS:
        r = get(f"/fraude/alertas/{tipo}", **ADMIN)
        verificar("F5", f"tipo '{tipo}' -> 404 con error", r.status_code == 404 and "error" in r.json(),
                  str(r.status_code))
    for valor in ("abc", "0", "-2", "1.5"):
        r = get("/fraude/alertas/sesgo_vendedor_sin_compra", min_resenas=valor, **ADMIN)
        verificar("F5", f"min_resenas={valor} -> 400", r.status_code == 400, str(r.status_code))
    for valor in ("0", "101"):
        r = get("/fraude/alertas/cuenta_rafaga", min_pct_sin_compra=valor, **ADMIN)
        verificar("F5", f"min_pct_sin_compra={valor} -> 400", r.status_code == 400, str(r.status_code))
    r = get("/fraude/alertas/cuenta_rafaga", min_resenas="9", ventana_segundos="60", **ADMIN)
    verificar("F5", "parámetros válidos se aplican y se devuelven (los omitidos con su default)",
              r.status_code == 200
              and r.json()["parametros"] == {"min_resenas": 9, "ventana_segundos": 60, "min_pct_sin_compra": 80})
    r = get("/fraude/patrones", **ADMIN)
    pats = r.json().get("patrones", []) if r.status_code == 200 else []
    verificar("F5", f"/patrones lista exactamente los {len(TIPOS)} tipos, en orden, con parámetros por defecto",
              [p["tipo"] for p in pats] == TIPOS and all(p["parametros"] and p["nombre"] and p["descripcion"] for p in pats))
    forma_ok = True
    for tipo in TIPOS:
        d = get(f"/fraude/alertas/{tipo}", **ADMIN).json()
        forma_ok &= set(d) == {"tipo", "alertas", "total", "parametros"} and d["tipo"] == tipo
        for a in d["alertas"]:
            forma_ok &= set(a) == {"tipo", "cuentas", "productos", "vendedor", "score", "nivel", "motivo", "evidencia"}
            forma_ok &= 0 <= a["score"] <= 100 and a["nivel"] == ("alto" if a["score"] >= 70 else "medio" if a["score"] >= 40 else "bajo")
        forma_ok &= [a["score"] for a in d["alertas"]] == sorted((a["score"] for a in d["alertas"]), reverse=True)
        forma_ok &= len(d["alertas"]) <= 50
    verificar("F5", "todas las alertas tienen la forma Alerta, score 0-100 coherente con nivel, orden desc", forma_ok)


def caso_resumen(esc):
    print("\n[F6] Resumen por cuenta")
    r = get("/fraude/resumen", **ADMIN)
    verificar("F6", "responde 200", r.status_code == 200, str(r.status_code))
    if r.status_code != 200:
        return
    d = r.json()
    verificar("F6", f"por_tipo trae los {len(TIPOS)} tipos y total_alertas es su suma",
              set(d["por_tipo"]) == set(TIPOS) and d["total_alertas"] == sum(d["por_tipo"].values()), str(d["por_tipo"]))
    por_id = {c["id_usuario"]: c for c in d["cuentas_riesgo"]}
    esperado = {"promotor": "sesgo_vendedor_sin_compra", "detractor": "sesgo_vendedor_sin_compra",
                "grupo_negativo": "grupo_coordinado", "grupo_positivo": "grupo_coordinado",
                "cuenta_rafaga": "cuenta_rafaga", "vinculadas": "cuentas_vinculadas"}
    for escenario, tipo in esperado.items():
        if escenario not in esc:
            continue
        ok = all(i in por_id and tipo in por_id[i]["patrones"] and por_id[i]["nivel"] in ("alto", "medio", "bajo")
                 for i in esc[escenario]["cuentas"])
        verificar("F6", f"cuentas de '{escenario}' están en cuentas_riesgo con '{tipo}' y nivel", ok)
    verificar("F6", "cuentas_riesgo solo menciona los 4 tipos y score_total está entre 0 y 100",
              all(set(c["patrones"]) <= set(TIPOS) and 0 <= c["score_total"] <= 100 for c in d["cuentas_riesgo"]))
    verificar("F6", "cuentas_riesgo ordenado por score_total desc",
              [c["score_total"] for c in d["cuentas_riesgo"]] == sorted((c["score_total"] for c in d["cuentas_riesgo"]), reverse=True))


def caso_resena_nueva(mongo_db, neo):
    print("\n[F7] Reseña nueva por la API -> grafo completo")
    usuarios = get("/usuarios").json()
    compradores = {u["id_usuario"]: u["nombre"] for u in usuarios if u["rol"] == "comprador"}
    productos = list(mongo_db["productos"].find({"activo": True, "vendedor.id_vendedor": {"$ne": None}},
                                                {"nombre": 1, "id_sql_origen": 1, "vendedor": 1}).sort("_id", 1))
    resenados = {(r["producto_id"], r["autor"]["id_usuario"]) for r in mongo_db["resenas"].find({}, {"producto_id": 1, "autor.id_usuario": 1})}

    # Preferimos un par con compra real (para probar compra_verificada = true).
    par = None
    try:
        pg = psycopg2.connect(**PG_CONFIG)
        cur = pg.cursor()
        cur.execute("SELECT DISTINCT p.id_comprador, l.id_producto FROM pedidos p "
                    "JOIN lineas_pedido l ON l.id_pedido = p.id_pedido ORDER BY 1, 2")
        compras = cur.fetchall()
        pg.close()
        por_sql = {p.get("id_sql_origen"): p for p in productos}
        for id_comprador, id_sql in compras:
            prod = por_sql.get(id_sql)
            if prod and id_comprador in compradores and (prod["_id"], id_comprador) not in resenados:
                par = (id_comprador, prod)
                break
    except Exception as e:
        print(f"   (sin Postgres para elegir un par con compra: {e})")
    if par is None:
        par = next(((c, p) for p in productos for c in compradores if (p["_id"], c) not in resenados), None)
    verificar("F7", "hay un par (comprador, producto) libre para la prueba", par)
    if par is None:
        return
    id_usuario, prod = par

    with neo.session() as s:
        existia_cuenta = s.run("MATCH (c:Cuenta {id_usuario: $id}) RETURN count(c) AS n", id=id_usuario).single()["n"] > 0
        existia_producto = s.run("MATCH (p:Producto {id_producto: $id}) RETURN count(p) AS n", id=prod["_id"]).single()["n"] > 0
        existia_vendedor = s.run("MATCH (v:Vendedor {id_vendedor: $id}) RETURN count(v) AS n",
                                 id=prod["vendedor"]["id_vendedor"]).single()["n"] > 0

    id_resena = None
    try:
        r = requests.post(f"{API}/resenas", json={
            "rol_solicitante": "comprador", "producto_id": prod["_id"], "id_usuario": id_usuario,
            "nombre_autor": compradores[id_usuario], "calificacion": 4,
            "texto": "Reseña temporal de prueba_fraude_ampliado.py",
        }, timeout=30)
        verificar("F7", "POST /api/resenas -> 201", r.status_code == 201, str(r.status_code))
        if r.status_code != 201:
            return
        id_resena = r.json()["resena"]["_id"]

        listado = get(f"/resenas/{prod['_id']}")
        mia = [x for x in listado.json().get("resenas", []) if x["_id"] == id_resena] if listado.status_code == 200 else []
        verificar("F7", "GET /api/resenas/<producto> lista la reseña nueva", mia, str(listado.status_code))
        verificada_api = mia[0]["verificada_compra"] if mia else None

        with neo.session() as s:
            fila = s.run("""
                MATCH (c:Cuenta {id_usuario: $u})-[r:CALIFICO {id_resena: $id}]->(p:Producto {id_producto: $p})
                OPTIONAL MATCH (p)-[:VENDIDO_POR]->(v:Vendedor)
                RETURN r.compra_verificada AS cv, r.calificacion AS cal, p.id_vendedor AS pv,
                       v.id_vendedor AS vid, v.nombre AS vnombre
            """, u=id_usuario, id=id_resena, p=prod["_id"]).single()
        verificar("F7", "CALIFICO creado en Neo4j", fila is not None and fila["cal"] == 4)
        if fila:
            verificar("F7", "CALIFICO.compra_verificada coincide con verificada_compra del listado",
                      isinstance(fila["cv"], bool) and fila["cv"] == verificada_api,
                      f"grafo={fila['cv']}, listado={verificada_api}")
            esperado = prod["vendedor"]["id_vendedor"]
            verificar("F7", "Producto-[:VENDIDO_POR]->Vendedor y Producto.id_vendedor correctos",
                      fila["vid"] == esperado and fila["pv"] == esperado
                      and fila["vnombre"] == prod["vendedor"].get("nombre_comercial"),
                      f"vendedor {fila['vid']} '{fila['vnombre']}'")
    finally:
        if id_resena:
            mongo_db["resenas"].delete_one({"_id": ObjectId(id_resena)})
            with neo.session() as s:
                s.run("MATCH ()-[r:CALIFICO {id_resena: $id}]->() DELETE r", id=id_resena).consume()
                if not existia_cuenta:
                    s.run("MATCH (c:Cuenta {id_usuario: $id}) WHERE NOT (c)--() DELETE c", id=id_usuario).consume()
                if not existia_producto:
                    s.run("MATCH (p:Producto {id_producto: $id}) DETACH DELETE p", id=prod["_id"]).consume()
                if not existia_vendedor:
                    s.run("MATCH (v:Vendedor {id_vendedor: $id}) WHERE NOT (v)--() DELETE v",
                          id=prod["vendedor"]["id_vendedor"]).consume()
            quedan = mongo_db["resenas"].count_documents({"_id": ObjectId(id_resena)})
            verificar("F7", "limpieza: la reseña temporal se borró de Mongo y Neo4j", quedan == 0)


def caso_direcciones(neo):
    print("\n[F8] Direcciones -> ENVIA_A")
    usuarios = get("/usuarios").json()
    elegido = None
    for u in sorted((u for u in usuarios if u["rol"] == "comprador"), key=lambda u: u["id_usuario"]):
        r = get(f"/usuarios/{u['id_usuario']}/direcciones")
        if r.status_code == 200 and len(r.json()) < 3:
            elegido = u["id_usuario"]
            break
    verificar("F8", "hay un comprador con espacio para una dirección más", elegido)
    if elegido is None:
        return

    marca = f"Prueba Fraude {int(time.time())}"
    cuerpo = {"direccion_linea1": f"  {marca}   Zona 10 ", "ciudad": "Guatemala", "departamento_estado": "Guatemala",
              "codigo_postal": "01010", "direccion_linea2": "[prueba_fraude_ampliado]"}
    clave1 = normalizar(cuerpo["direccion_linea1"]) + "|" + normalizar("Guatemala") + "|" + normalizar("01010")
    clave2 = normalizar(f"{marca} Zona 14") + "|" + normalizar("Mixco") + "|" + normalizar("01057")

    def enlaces(clave):
        with neo.session() as s:
            return s.run("""
                OPTIONAL MATCH (d:Direccion {clave: $clave})
                OPTIONAL MATCH (c:Cuenta {id_usuario: $u})-[e:ENVIA_A]->(d)
                RETURN count(DISTINCT d) AS nodos, count(e) AS rel, collect(DISTINCT d.ciudad) AS ciudades
            """, clave=clave, u=elegido).single()

    id_direccion = None
    try:
        r = requests.post(f"{API}/usuarios/{elegido}/direcciones", json=cuerpo, timeout=30)
        verificar("F8", "POST dirección -> 201", r.status_code == 201, str(r.status_code))
        if r.status_code != 201:
            return
        id_direccion = r.json()["id_direccion"]
        e = enlaces(clave1)
        verificar("F8", "crear: ENVIA_A a la Direccion con clave normalizada", e["rel"] == 1 and e["ciudades"] == ["Guatemala"],
                  clave1)

        cuerpo2 = dict(cuerpo, direccion_linea1=f"{marca} Zona 14", ciudad="Mixco", codigo_postal="01057")
        r = requests.put(f"{API}/usuarios/{elegido}/direcciones/{id_direccion}", json=cuerpo2, timeout=30)
        verificar("F8", "PUT dirección -> 200", r.status_code == 200, str(r.status_code))
        viejo, nuevo = enlaces(clave1), enlaces(clave2)
        verificar("F8", "editar: quita la relación vieja (y el nodo sin otras cuentas) y crea la nueva",
                  viejo["nodos"] == 0 and nuevo["rel"] == 1, f"viejo={viejo['nodos']} nodos, nuevo={nuevo['rel']} rel")

        r = requests.delete(f"{API}/usuarios/{elegido}/direcciones/{id_direccion}", timeout=30)
        verificar("F8", "DELETE dirección -> 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            id_direccion = None
        e = enlaces(clave2)
        verificar("F8", "borrar: sin ENVIA_A ni nodo Direccion huérfano", e["nodos"] == 0)
    finally:
        if id_direccion:
            requests.delete(f"{API}/usuarios/{elegido}/direcciones/{id_direccion}", timeout=30)


def main():
    print("=" * 74)
    print("EVIDENCIA DE LA DETECCIÓN DE FRAUDE AMPLIADA (NEO4J)")
    print("=" * 74)

    mongo_db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"), serverSelectionTimeoutMS=3000)[
        os.getenv("MONGO_DB_NAME", "tiendaya_nosql")]
    neo = GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                               auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "tiendaya123")))

    esc = escenarios_semilla(mongo_db)
    print("Escenarios en la semilla:", {k: (sorted(v["cuentas"]), sorted(v["productos"])) for k, v in sorted(esc.items())})

    caso_escenarios(mongo_db, esc)
    caso_endpoint_original(mongo_db)
    caso_errores()
    caso_resumen(esc)
    caso_resena_nueva(mongo_db, neo)
    caso_direcciones(neo)
    neo.close()

    fallas = [r for r in resultados if not r[2]]
    print("\n" + "=" * 74)
    print(f"{len(resultados) - len(fallas)}/{len(resultados)} verificaciones OK")
    for caso, desc, _ in fallas:
        print(f"   FALLA {caso}: {desc}")
    print("RESULTADO:", "PASS" if not fallas else "FAIL")
    sys.exit(0 if not fallas else 1)


if __name__ == "__main__":
    main()
