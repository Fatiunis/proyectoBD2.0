"""
Prueba del control de acceso de Redis (entrega final).

Standalone: NO es parte de la app Flask. Solo necesita el Redis del
docker-compose levantado con database/redis/users.acl. Se conecta como cada
usuario y verifica que puede hacer lo que su servicio necesita y que NO puede
hacer nada fuera de su alcance (la respuesta esperada de Redis es NOPERM,
NOAUTH o WRONGPASS).

Usuarios (detalle en docs/decisiones/ADR-009-control-acceso-redis.md):
  (sin credenciales)  -> rechazado: el usuario "default" está deshabilitado
  tiendaya_api        -> API web: keys carrito:* y oferta:*, comandos de datos y scripts
  tiendaya_relevo     -> relevo del outbox: solo HGET/HDEL/scripts sobre carritos y reservas
  tiendaya_lectura    -> visores (RedisInsight): solo lectura sobre todas las keys
  tiendaya_admin      -> operación: todo permitido

Solo usa keys con el sufijo "prueba_acl" y las borra al terminar.

Uso:
    venv\\Scripts\\python.exe backend/scripts/prueba_control_acceso_redis.py
"""

import os
import sys

import redis
from dotenv import load_dotenv

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(RAIZ, ".env"))

HOST = os.getenv("REDIS_HOST_PRUEBA", "localhost")
PUERTO = 6379
CREDENCIALES = {
    "tiendaya_api": "api_tiendaya_2026",
    "tiendaya_relevo": "relevo_tiendaya_2026",
    "tiendaya_lectura": "lectura_tiendaya_2026",
    "tiendaya_admin": "admin_tiendaya_2026",
}

CARRITO = "carrito:prueba_acl"
STOCK = "oferta:prueba_acl:stock"
RESERVAS = "oferta:prueba_acl:reservas"
AJENA = "sesion:prueba_acl"  # una key que no pertenece a ningún servicio

resultados = []


def cliente(usuario=None, password=None):
    return redis.Redis(host=HOST, port=PUERTO, username=usuario, password=password, decode_responses=True,
                       socket_connect_timeout=3, protocol=2)


def como(usuario):
    return cliente(usuario, CREDENCIALES[usuario])


def verificar(usuario, descripcion, operacion, permitido):
    """Ejecuta la operación y compara con lo esperado. Un rechazo cuenta si
    Redis responde con un error de autenticación o de permisos."""
    try:
        r = operacion()
        obtenido, detalle = True, repr(r)[:60]
    except (redis.exceptions.NoPermissionError, redis.exceptions.AuthenticationError,
            redis.exceptions.AuthenticationWrongNumberOfArgsError) as e:
        obtenido, detalle = False, str(e).split(".")[0][:90]
    except redis.exceptions.ResponseError as e:
        # Dentro de un script Lua, Redis 7 reporta la falta de permisos como
        # error del script: "ACL failure in script: User ... has no permissions to run ...".
        texto = str(e)
        if "NOPERM" in texto or "ACL failure" in texto or "no permissions" in texto.lower():
            obtenido, detalle = False, texto.rsplit(" script: ", 1)[0][:90]
        else:
            raise
    ok = obtenido == permitido
    resultados.append(ok)
    esperado = "PERMITIDO" if permitido else "DENEGADO "
    print(f"  [{'OK  ' if ok else 'FALLA'}] {esperado} {descripcion:<58} -> {detalle}")


def main():
    print("=" * 100)
    print("PRUEBA DE CONTROL DE ACCESO EN REDIS (users.acl)")
    print("=" * 100)

    admin = como("tiendaya_admin")
    admin.delete(CARRITO, STOCK, RESERVAS, AJENA)
    admin.set(AJENA, "dato de otro servicio")

    print("\n[1] Conexión sin credenciales y usuario default")
    anonimo = cliente()
    verificar("anonimo", "PING sin autenticarse", anonimo.ping, False)
    verificar("anonimo", "GET sin autenticarse", lambda: anonimo.get(AJENA), False)
    verificar("default", "AUTH como 'default' (deshabilitado)", lambda: cliente("default", "x").ping(), False)
    verificar("api", "AUTH de tiendaya_api con contraseña incorrecta",
              lambda: cliente("tiendaya_api", "incorrecta").ping(), False)

    print("\n[2] tiendaya_api (API web)")
    api = como("tiendaya_api")
    verificar("api", f"HSET {CARRITO}", lambda: api.hset(CARRITO, "PROD-0001", '{"cantidad": 1}'), True)
    verificar("api", f"HGETALL {CARRITO}", lambda: api.hgetall(CARRITO), True)
    verificar("api", f"SET {STOCK} EX 60", lambda: api.set(STOCK, 10, ex=60), True)
    verificar("api", f"DECRBY {STOCK}", lambda: api.decrby(STOCK, 1), True)
    verificar("api", "EVAL script sobre sus keys (como las ofertas)",
              lambda: api.eval("return redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])", 1, RESERVAS, "7", "{}"), True)
    verificar("api", f"GET {AJENA} (key fuera de carrito:*/oferta:*)", lambda: api.get(AJENA), False)
    verificar("api", f"SET {AJENA}", lambda: api.set(AJENA, "x"), False)
    verificar("api", "EVAL que toca una key ajena desde Lua",
              lambda: api.eval("return redis.call('GET', KEYS[1])", 1, AJENA), False)
    verificar("api", "EVAL que intenta FLUSHALL desde Lua",
              lambda: api.eval("return redis.call('FLUSHALL')", 0), False)
    verificar("api", "FLUSHALL", api.flushall, False)
    verificar("api", "KEYS * (bloquea el servidor)", lambda: api.keys("*"), False)
    verificar("api", "CONFIG GET requirepass", lambda: api.config_get("requirepass"), False)
    verificar("api", "ACL LIST (ver otros usuarios)", api.acl_list, False)
    verificar("api", "SHUTDOWN", lambda: api.execute_command("SHUTDOWN"), False)

    print("\n[3] tiendaya_relevo (relevo del outbox del checkout)")
    relevo = como("tiendaya_relevo")
    verificar("relevo", f"HGET {CARRITO}", lambda: relevo.hget(CARRITO, "PROD-0001"), True)
    verificar("relevo", f"HDEL {CARRITO} (limpiar línea comprada)", lambda: relevo.hdel(CARRITO, "PROD-0001"), True)
    verificar("relevo", f"HDEL {RESERVAS} (cerrar reserva)", lambda: relevo.hdel(RESERVAS, "7"), True)
    verificar("relevo", f"HSET {CARRITO} (agregar al carrito)",
              lambda: relevo.hset(CARRITO, "PROD-9", "{}"), False)
    verificar("relevo", f"GET {STOCK} (stock de la oferta)", lambda: relevo.get(STOCK), False)
    verificar("relevo", f"INCRBY {STOCK} (devolver stock)", lambda: relevo.incrby(STOCK, 5), False)
    verificar("relevo", f"DEL {CARRITO} (borrar el carrito entero)", lambda: relevo.delete(CARRITO), False)
    verificar("relevo", "EVAL que hace SET desde Lua",
              lambda: relevo.eval("return redis.call('SET', KEYS[1], '1')", 1, CARRITO), False)
    verificar("relevo", f"HGET {AJENA}", lambda: relevo.hget(AJENA, "x"), False)

    print("\n[4] tiendaya_lectura (visor RedisInsight)")
    lectura = como("tiendaya_lectura")
    verificar("lectura", f"GET {AJENA} (lee cualquier key)", lambda: lectura.get(AJENA), True)
    verificar("lectura", f"GET {STOCK}", lambda: lectura.get(STOCK), True)
    verificar("lectura", "SCAN", lambda: lectura.scan(0, match="*prueba_acl*", count=1000), True)
    verificar("lectura", "INFO keyspace", lambda: lectura.info("keyspace"), True)
    verificar("lectura", f"SET {AJENA}", lambda: lectura.set(AJENA, "x"), False)
    verificar("lectura", f"DEL {CARRITO}", lambda: lectura.delete(CARRITO), False)
    verificar("lectura", "FLUSHDB", lectura.flushdb, False)
    verificar("lectura", "EVAL (scripts)", lambda: lectura.eval("return 1", 0), False)

    print("\n[5] tiendaya_admin (operación)")
    verificar("admin", "ACL WHOAMI", admin.acl_whoami, True)
    verificar("admin", "DEL de todas las keys de prueba", lambda: admin.delete(CARRITO, STOCK, RESERVAS, AJENA), True)

    total, ok = len(resultados), sum(resultados)
    print("\n" + "=" * 100)
    print(f"RESUMEN: {ok}/{total} verificaciones correctas")
    print(f"RESULTADO: {'PASS' if ok == total else 'FAIL'}")
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    main()
