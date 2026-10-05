"""
Prueba de fallas simuladas sobre el checkout distribuido (Entrega 3).

Standalone: NO es parte de la app Flask. Se corre contra un servidor real ya
levantado (python backend/main.py) con PostgreSQL, MongoDB, Redis y
Elasticsearch disponibles, y con PERMITIR_FALLAS_SIMULADAS=1 en el .env.

Cada escenario hace un checkout real (crea pedidos reales en la base local),
inyecta una falla en un punto distinto del flujo y verifica directamente en
cada motor que el sistema quedó en el estado que promete
docs/estrategia-consistencia-checkout.md:

  E0  Camino feliz + reintento con la misma clave de idempotencia
      -> un solo pedido; stock igual en PostgreSQL, MongoDB y Elasticsearch.
  E1  Redis cae al leer el carrito
      -> 503, no se crea pedido ni cambia el stock; el carrito queda intacto.
  E2  PostgreSQL cae antes del COMMIT, con una línea de oferta relámpago
      -> 503, no hay pedido, la reserva de oferta se COMPENSA (vuelve a
         "activa", 0 vendidas); reintentar con la misma clave sí compra.
  E3  Redis cae DESPUÉS del COMMIT (cerrar reservas / limpiar carrito)
      -> 201 igual (el pedido es válido); el carrito queda con lo comprado
         hasta que el relevo, un reintento con la misma clave (200,
         "repetido") o el siguiente checkout lo limpian; ni un reintento con
         la misma clave ni un checkout nuevo con otra clave crean un segundo
         pedido.
  E4  MongoDB cae al copiar el stock después del COMMIT
      -> 201; Mongo queda con el stock viejo y el relevo lo corrige solo
         (consistencia eventual, ventana acotada).
  E5  (opcional, --caida-real) Elasticsearch se DETIENE de verdad
      (docker compose stop) -> el checkout no se entera (201), el buscador
      responde 503; al volver a levantarlo, el relevo pone el stock al día.

Comprador: maria.torres@email.com (semilla de usuarios), o el primer comprador
con dirección. Productos: los primeros de la semilla con stock >= 30.

Uso:
    venv\\Scripts\\python.exe backend/scripts/prueba_fallas_checkout.py
    venv\\Scripts\\python.exe backend/scripts/prueba_fallas_checkout.py --caida-real
"""

import argparse
import os
import subprocess
import sys
import time
import uuid

import psycopg2
import redis
import requests
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from pymongo import MongoClient

load_dotenv()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000/api"
EMAIL_COMPRADOR = "maria.torres@email.com"
ID_ADMIN = 1
ESPERA_RELEVO_SEGUNDOS = 90
ESPERA_CAIDA_REAL_SEGUNDOS = 300
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

pg = psycopg2.connect(
    host=os.getenv("PG_HOST"), port=os.getenv("PG_PORT"), dbname=os.getenv("PG_DBNAME"),
    user=os.getenv("PG_USER"), password=os.getenv("PG_PASSWORD"),
)
pg.autocommit = True
mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))["tiendaya_nosql"]["productos"]
rds = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
es = Elasticsearch(os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"), request_timeout=5)
ALIAS = os.getenv("ES_ALIAS_PRODUCTOS", "productos")

resultados = []  # (escenario, verificación, ok, detalle)


# ---------------------------------------------------------------- utilidades


def sql(consulta, *params):
    with pg.cursor() as cur:
        cur.execute(consulta, params)
        return cur.fetchall() if cur.description else None


def verificar(escenario, descripcion, condicion, detalle=""):
    resultados.append((escenario, descripcion, bool(condicion), detalle))
    marca = "OK  " if condicion else "FALLA"
    print(f"   [{marca}] {descripcion}" + (f"  ({detalle})" if detalle else ""))
    return condicion


def contar_pedidos(id_comprador):
    return sql("SELECT count(*) FROM pedidos WHERE id_comprador = %s", id_comprador)[0][0]


def stock_pg(id_sql):
    return sql("SELECT stock_disponible FROM inventario WHERE id_producto = %s", id_sql)[0][0]


def stock_mongo(id_sql):
    return mongo.find_one({"id_sql_origen": id_sql}, {"stock_disponible": 1}).get("stock_disponible")


def stock_es(id_sql):
    es.indices.refresh(index=ALIAS)
    hits = es.search(index=ALIAS, query={"term": {"id_sql_origen": id_sql}}, size=1)["hits"]["hits"]
    return hits[0]["_source"].get("stock_disponible") if hits else None


def carrito(id_usuario):
    return rds.hgetall(f"carrito:{id_usuario}")


def eventos_pedido(id_pedido):
    return sql("SELECT tipo, estado, intentos, ultimo_error FROM eventos_sincronizacion "
               "WHERE id_pedido = %s ORDER BY id_evento", id_pedido)


def existe_clave(clave):
    return bool(sql("SELECT 1 FROM checkout_idempotencia WHERE clave = %s", clave))


def esperar(condicion, segundos, cada=2):
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            if condicion():
                return True
        except Exception:
            pass
        time.sleep(cada)
    return False


def agregar_al_carrito(id_usuario, producto, cantidad=1):
    p = requests.get(f"{BASE_URL}/productos/{producto['_id']}", timeout=5).json()
    r = requests.post(f"{BASE_URL}/carrito/{id_usuario}/items", json={
        "id_producto": p["_id"], "id_sql_origen": p["id_sql_origen"], "nombre": p["nombre"],
        "precio_base": p["precio_base"], "id_categoria": p["categoria"]["id_categoria"],
        "imagen_url": (p.get("imagenes") or [{}])[0].get("url", ""),
        "stock_disponible": p["stock_disponible"], "cantidad": cantidad,
    }, timeout=5)
    r.raise_for_status()


def checkout(id_usuario, id_direccion, clave, falla=None):
    cuerpo = {"id_comprador": id_usuario, "id_direccion": id_direccion,
              "metodo_pago": "tarjeta_credito", "clave_idempotencia": clave}
    if falla:
        cuerpo["simular_falla"] = falla
    r = requests.post(f"{BASE_URL}/checkout", json=cuerpo, timeout=30)
    return r.status_code, r.json()


def vaciar_carrito(id_usuario):
    requests.delete(f"{BASE_URL}/carrito/{id_usuario}", timeout=5)


def nueva_clave():
    return f"prueba-{uuid.uuid4().hex[:20]}"


# ---------------------------------------------------------------- preparación


def preparar():
    print("=" * 74)
    print("PRUEBA DE FALLAS SIMULADAS - CHECKOUT DISTRIBUIDO")
    print("=" * 74)
    habilitadas = requests.get(f"{BASE_URL}/checkout/fallas-simuladas", timeout=5).json()
    if not habilitadas.get("habilitadas"):
        sys.exit("El servidor no tiene PERMITIR_FALLAS_SIMULADAS=1 en el .env. Agrégalo y reinicia el backend.")

    fila = sql("""
        SELECT u.id_usuario, d.id_direccion FROM usuarios u
        JOIN direcciones d ON d.id_usuario = u.id_usuario
        WHERE u.rol = 'comprador'
        ORDER BY (u.email = %s) DESC, d.es_principal DESC, u.id_usuario LIMIT 1
    """, EMAIL_COMPRADOR)
    if not fila:
        sys.exit("No hay ningún comprador con dirección de envío (corre datos_semilla_usuarios.sql).")
    id_comprador, id_direccion = fila[0]

    candidatos = sql("""
        SELECT p.id_producto FROM productos p JOIN inventario i ON i.id_producto = p.id_producto
        WHERE p.activo AND i.stock_disponible >= 30 ORDER BY p.id_producto LIMIT 40
    """)
    productos = []
    for (id_sql,) in candidatos:
        doc = mongo.find_one({"id_sql_origen": id_sql, "activo": True})
        if doc and not rds.exists(f"oferta:{doc['_id']}:stock") and stock_es(id_sql) is not None:
            productos.append({"_id": doc["_id"], "id_sql": id_sql, "precio": doc["precio_base"], "nombre": doc["nombre"]})
        if len(productos) == 3:
            break
    if len(productos) < 3:
        sys.exit("No se encontraron 3 productos con stock >= 30, indexados y sin oferta activa.")

    # Antes de empezar, Mongo y Elasticsearch deben coincidir con Postgres.
    for p in productos:
        pg_s = stock_pg(p["id_sql"])
        mongo.update_one({"id_sql_origen": p["id_sql"]}, {"$set": {"stock_disponible": pg_s}})
        es.update_by_query(index=ALIAS, query={"term": {"id_sql_origen": p["id_sql"]}}, refresh=True,
                           script={"source": "ctx._source.stock_disponible = params.s", "params": {"s": pg_s}})

    vaciar_carrito(id_comprador)
    print(f"Comprador id={id_comprador} (dirección {id_direccion})")
    for etiqueta, p in zip("ABC", productos):
        print(f"Producto {etiqueta}: {p['_id']} (id_sql {p['id_sql']}) {p['nombre']} - stock {stock_pg(p['id_sql'])}")
    return id_comprador, id_direccion, productos


# ---------------------------------------------------------------- escenarios


def e0_camino_feliz(uid, dir_id, A):
    print("\n[E0] Camino feliz + reintento con la misma clave de idempotencia")
    clave = nueva_clave()
    pedidos_antes, stock_antes = contar_pedidos(uid), stock_pg(A["id_sql"])
    agregar_al_carrito(uid, A)
    codigo, r = checkout(uid, dir_id, clave)
    verificar("E0", "checkout responde 201", codigo == 201, f"{codigo} {r.get('id_pedido')}")
    verificar("E0", "sin sincronización pendiente", r.get("sincronizacion_pendiente") is False)
    verificar("E0", "se creó exactamente 1 pedido", contar_pedidos(uid) == pedidos_antes + 1)
    s = stock_pg(A["id_sql"])
    verificar("E0", "stock en PostgreSQL bajó 1", s == stock_antes - 1, f"{stock_antes} -> {s}")
    verificar("E0", "MongoDB = PostgreSQL", stock_mongo(A["id_sql"]) == s, f"mongo={stock_mongo(A['id_sql'])}")
    verificar("E0", "Elasticsearch = PostgreSQL", stock_es(A["id_sql"]) == s, f"es={stock_es(A['id_sql'])}")
    verificar("E0", "carrito sin la línea comprada", A["_id"] not in carrito(uid))
    estados = {e[1] for e in eventos_pedido(r["id_pedido"])}
    verificar("E0", "todos los eventos del outbox procesados", estados == {"procesado"}, str(estados))

    codigo2, r2 = checkout(uid, dir_id, clave)
    verificar("E0", "reintento con la misma clave -> 200 repetido, mismo pedido",
              codigo2 == 200 and r2.get("repetido") and r2.get("id_pedido") == r["id_pedido"],
              f"{codigo2} pedido {r2.get('id_pedido')}")
    verificar("E0", "el reintento NO creó otro pedido ni cobró dos veces",
              contar_pedidos(uid) == pedidos_antes + 1 and stock_pg(A["id_sql"]) == s)


def e1_redis_lectura(uid, dir_id, A):
    print("\n[E1] Redis cae al leer el carrito")
    clave = nueva_clave()
    agregar_al_carrito(uid, A)
    pedidos_antes, stock_antes = contar_pedidos(uid), stock_pg(A["id_sql"])
    codigo, r = checkout(uid, dir_id, clave, "redis_lectura_carrito")
    verificar("E1", "responde 503 CARRITO_NO_DISPONIBLE", codigo == 503 and r.get("codigo") == "CARRITO_NO_DISPONIBLE",
              f"{codigo} {r.get('codigo')}")
    verificar("E1", "mensaje al usuario dice que no hubo cobro", "ningún cobro" in r.get("error", ""), r.get("error"))
    verificar("E1", "no se creó pedido", contar_pedidos(uid) == pedidos_antes)
    verificar("E1", "el stock no cambió", stock_pg(A["id_sql"]) == stock_antes)
    verificar("E1", "el carrito sigue intacto", A["_id"] in carrito(uid))
    verificar("E1", "no quedó clave de idempotencia", not existe_clave(clave))


def e2_postgres_antes_commit(uid, dir_id, A, C):
    print("\n[E2] PostgreSQL cae antes del COMMIT (con una línea de oferta relámpago)")
    precio_oferta = round(C["precio"] * 0.9, 2)
    r = requests.post(f"{BASE_URL}/ofertas", json={
        "producto_id": C["_id"], "cantidad_limite": 5, "precio_oferta": precio_oferta, "duracion_minutos": 10,
        "rol_solicitante": "administrador", "id_usuario": ID_ADMIN}, timeout=5)
    if r.status_code != 201:
        verificar("E2", "crear la oferta de prueba", False, f"{r.status_code} {r.text}")
        return
    try:
        rr = requests.post(f"{BASE_URL}/ofertas/{C['_id']}/reservar",
                           json={"id_usuario": uid, "cantidad": 2, "rol_solicitante": "comprador"}, timeout=5)
        verificar("E2", "reserva de 2 unidades en la oferta", rr.status_code == 201, str(rr.status_code))

        clave = nueva_clave()
        pedidos_antes = contar_pedidos(uid)
        stock_a, stock_c = stock_pg(A["id_sql"]), stock_pg(C["id_sql"])
        codigo, resp = checkout(uid, dir_id, clave, "postgres_antes_commit")
        verificar("E2", "responde 503 PAGO_NO_CONFIRMADO", codigo == 503 and resp.get("codigo") == "PAGO_NO_CONFIRMADO",
                  f"{codigo} {resp.get('codigo')}")
        verificar("E2", "no se creó pedido (rollback)", contar_pedidos(uid) == pedidos_antes)
        verificar("E2", "el inventario de PostgreSQL no cambió",
                  stock_pg(A["id_sql"]) == stock_a and stock_pg(C["id_sql"]) == stock_c)
        verificar("E2", "la clave de idempotencia también se revirtió", not existe_clave(clave))
        o = requests.get(f"{BASE_URL}/ofertas/{C['_id']}", params={"id_usuario": uid}, timeout=5).json()
        verificar("E2", "COMPENSACIÓN: la reserva volvió a estar activa y no hay unidades vendidas",
                  (o.get("reserva_usuario") or {}).get("cantidad") == 2 and o.get("unidades_vendidas") == 0,
                  f"reservadas={o.get('unidades_reservadas')} vendidas={o.get('unidades_vendidas')}")
        verificar("E2", "el carrito sigue intacto (línea normal + oferta)",
                  A["_id"] in carrito(uid) and f"oferta:{C['_id']}" in carrito(uid))

        codigo2, resp2 = checkout(uid, dir_id, clave)
        verificar("E2", "reintentar con la misma clave (sin falla) completa la compra",
                  codigo2 == 201, f"{codigo2} pedido {resp2.get('id_pedido')}")
        o = requests.get(f"{BASE_URL}/ofertas/{C['_id']}", timeout=5).json()
        verificar("E2", "ahora sí: 2 unidades vendidas en la oferta y 2 menos en PostgreSQL",
                  o.get("unidades_vendidas") == 2 and stock_pg(C["id_sql"]) == stock_c - 2,
                  f"vendidas={o.get('unidades_vendidas')} stock {stock_c} -> {stock_pg(C['id_sql'])}")
    finally:
        requests.delete(f"{BASE_URL}/ofertas/{C['_id']}",
                        params={"rol_solicitante": "administrador", "id_usuario": ID_ADMIN}, timeout=5)
        vaciar_carrito(uid)


def e3_redis_post_commit(uid, dir_id, A):
    print("\n[E3] Redis cae DESPUÉS del COMMIT (no se puede limpiar el carrito)")
    clave = nueva_clave()
    agregar_al_carrito(uid, A)
    pedidos_antes = contar_pedidos(uid)
    codigo, r = checkout(uid, dir_id, clave, "redis_post_commit")
    verificar("E3", "responde 201: el pedido es válido aunque Redis falló",
              codigo == 201 and r.get("sincronizacion_pendiente") is True, f"{codigo} pedido {r.get('id_pedido')}")
    verificar("E3", "se creó 1 pedido", contar_pedidos(uid) == pedidos_antes + 1)
    verificar("E3", "el carrito TODAVÍA tiene la línea pagada (ventana de inconsistencia)", A["_id"] in carrito(uid))
    pend = [e for e in eventos_pedido(r["id_pedido"]) if e[0] == "limpiar_carrito"]
    verificar("E3", "evento limpiar_carrito pendiente con el error registrado",
              pend and pend[0][1] == "pendiente" and pend[0][3], pend[0][3] if pend else "")

    # El usuario recarga la página (clave NUEVA) y ve lo pagado todavía en su carrito.
    codigo_nuevo, r_nuevo = checkout(uid, dir_id, nueva_clave())
    verificar("E3", "un checkout con OTRA clave sobre el carrito viejo no cobra de nuevo (409 CARRITO_VACIO)",
              codigo_nuevo == 409 and r_nuevo.get("codigo") == "CARRITO_VACIO", f"{codigo_nuevo} {r_nuevo.get('codigo')}")
    verificar("E3", "sigue habiendo un solo pedido", contar_pedidos(uid) == pedidos_antes + 1)

    codigo2, r2 = checkout(uid, dir_id, clave)
    verificar("E3", "el cliente reintenta con la misma clave -> 200 repetido, mismo pedido",
              codigo2 == 200 and r2.get("repetido") and r2.get("id_pedido") == r["id_pedido"], str(codigo2))
    verificar("E3", "NO hay pedido duplicado aunque el carrito seguía lleno", contar_pedidos(uid) == pedidos_antes + 1)
    verificar("E3", "el carrito quedó limpio", esperar(lambda: A["_id"] not in carrito(uid), 10))
    estados = {e[1] for e in eventos_pedido(r["id_pedido"])}
    verificar("E3", "todos los eventos terminaron procesados", estados == {"procesado"}, str(estados))


def e4_mongo_post_commit(uid, dir_id, B):
    print("\n[E4] MongoDB cae al copiar el stock después del COMMIT")
    clave = nueva_clave()
    agregar_al_carrito(uid, B)
    stock_mongo_antes = stock_mongo(B["id_sql"])
    codigo, r = checkout(uid, dir_id, clave, "mongo_post_commit")
    verificar("E4", "responde 201 con sincronización pendiente",
              codigo == 201 and r.get("sincronizacion_pendiente") is True, f"{codigo} pedido {r.get('id_pedido')}")
    s = stock_pg(B["id_sql"])
    verificar("E4", "MongoDB quedó con el stock VIEJO (inconsistencia temporal)",
              stock_mongo(B["id_sql"]) == stock_mongo_antes and stock_mongo_antes != s,
              f"mongo={stock_mongo(B['id_sql'])} postgres={s}")
    verificar("E4", "Elasticsearch sí se actualizó (falla aislada por motor)", stock_es(B["id_sql"]) == s)
    t0 = time.time()
    ok = esperar(lambda: stock_mongo(B["id_sql"]) == stock_pg(B["id_sql"]), ESPERA_RELEVO_SEGUNDOS)
    verificar("E4", "el relevo corrigió MongoDB sin intervención", ok, f"convergió en {time.time() - t0:.0f} s")
    ev = [e for e in eventos_pedido(r["id_pedido"]) if e[0] == "stock_mongo"]
    verificar("E4", "evento stock_mongo procesado en el 2.º intento o después",
              ev and ev[0][1] == "procesado" and ev[0][2] >= 2, f"intentos={ev[0][2] if ev else '?'}")


def e5_caida_real_elasticsearch(uid, dir_id, B):
    print("\n[E5] Caída REAL de Elasticsearch (docker compose stop elasticsearch)")
    subprocess.run(["docker", "compose", "stop", "elasticsearch"], cwd=RAIZ, check=True, capture_output=True)
    try:
        b = requests.get(f"{BASE_URL}/busqueda", params={"q": "laptop"}, timeout=15)
        verificar("E5", "el buscador responde 503 BUSCADOR_NO_DISPONIBLE",
                  b.status_code == 503 and b.json().get("codigo") == "BUSCADOR_NO_DISPONIBLE", str(b.status_code))
        clave = nueva_clave()
        agregar_al_carrito(uid, B)
        codigo, r = checkout(uid, dir_id, clave)
        verificar("E5", "el checkout NO depende del buscador: 201", codigo == 201, f"pedido {r.get('id_pedido')}")
        ev = [e for e in eventos_pedido(r["id_pedido"]) if e[0] == "stock_elasticsearch"]
        verificar("E5", "evento stock_elasticsearch quedó pendiente", ev and ev[0][1] == "pendiente",
                  (ev[0][3] or "")[:80] if ev else "")
        verificar("E5", "MongoDB sí quedó al día", stock_mongo(B["id_sql"]) == stock_pg(B["id_sql"]))
    finally:
        subprocess.run(["docker", "compose", "start", "elasticsearch"], cwd=RAIZ, check=True, capture_output=True)
    t0 = time.time()
    ok = esperar(lambda: stock_es(B["id_sql"]) == stock_pg(B["id_sql"]), ESPERA_CAIDA_REAL_SEGUNDOS, cada=5)
    verificar("E5", "al volver Elasticsearch, el relevo puso su stock al día", ok,
              f"convergió {time.time() - t0:.0f} s después de levantarlo")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--caida-real", action="store_true",
                        help="Incluye E5: detiene y vuelve a levantar el contenedor de Elasticsearch.")
    args = parser.parse_args()

    uid, dir_id, (A, B, C) = preparar()
    try:
        e0_camino_feliz(uid, dir_id, A)
        e1_redis_lectura(uid, dir_id, A)
        e2_postgres_antes_commit(uid, dir_id, A, C)
        e3_redis_post_commit(uid, dir_id, A)
        e4_mongo_post_commit(uid, dir_id, B)
        if args.caida_real:
            e5_caida_real_elasticsearch(uid, dir_id, B)
    finally:
        vaciar_carrito(uid)

    print("\n" + "=" * 74)
    total, fallas = len(resultados), [r for r in resultados if not r[2]]
    print(f"RESUMEN: {total - len(fallas)}/{total} verificaciones correctas")
    for esc, desc, _, det in fallas:
        print(f"   FALLA {esc}: {desc} {det}")
    print("RESULTADO:", "PASS" if not fallas else "FAIL")
    sys.exit(0 if not fallas else 1)


if __name__ == "__main__":
    main()
