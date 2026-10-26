# ADR-009 — Control de acceso en Redis con ACL por servicio

Fecha: 2026-10-21 (entrega final)

## Contexto

La entrega final pide "autenticación y autorización configuradas explícitamente en al menos un componente NoSQL, con roles y permisos acotados según el servicio que los utiliza, y evidencia de que un usuario sin los permisos correspondientes no puede ejecutar operaciones fuera de su alcance".

Estado al terminar la Entrega 3 (documentado en `docs/arquitectura.md`, "Sin autenticación centralizada"):

| Componente | Autenticación |
|---|---|
| Redis | ninguna: cualquiera que llegara al puerto 6379 podía leer carritos, cambiar el cupo de una oferta o hacer `FLUSHALL` |
| Elasticsearch | ninguna (`xpack.security.enabled=false`) |
| MongoDB | ninguna (instalación local de cada integrante) |
| Neo4j | un solo usuario administrador; la edición Community no tiene roles |

Redis es el componente donde una operación indebida hace más daño al negocio: `INCRBY oferta:<pid>:stock 1000` rompe la garantía de "sin sobreventa" de la Entrega 2, y `FLUSHALL` borra todos los carritos y ofertas. Además lo usan **tres servicios con necesidades distintas**:

- la **API web** (carrito, ofertas, checkout): lee y escribe `carrito:*` y `oferta:*`, ejecuta scripts Lua;
- el **relevo del outbox** (Entrega 3): solo cierra reservas y quita líneas pagadas del carrito;
- los **visores** (RedisInsight): solo deberían mirar.

## Alternativas consideradas

1. **No configurar control de acceso** y documentar el riesgo. No cumple el requisito.
2. **Solo `requirepass`** en Redis: autentica, pero es una sola contraseña con todos los permisos; no hay roles por servicio.
3. **ACL de Redis 7 con un usuario por servicio**, en un archivo `users.acl` versionado y montado en el contenedor.
4. **Seguridad de Elasticsearch** (roles nativos: buscador de solo lectura, indexador con escritura). Igual de válida, pero obliga a reconfigurar Kibana (service token), el indexador, el backend y los scripts de prueba con credenciales, y el daño que evita es menor: el índice se reconstruye entero desde MongoDB.
5. **Autenticación en MongoDB.** MongoDB corre instalado localmente en cada máquina; activarla exige editar `mongod.cfg` y crear usuarios a mano en cada una, sin forma de versionarlo en el repositorio.

## Decisión

Alternativa 3. Redis arranca con `--aclfile /usr/local/etc/redis/users.acl` (archivo `database/redis/users.acl`, montado de solo lectura):

| Usuario | Lo usa | Keys | Comandos |
|---|---|---|---|
| `default` | nadie | — | **deshabilitado** (`off`): una conexión sin credenciales recibe `NOAUTH` |
| `tiendaya_api` | API web (`REDIS_URL`) | `carrito:*`, `oferta:*` | 25 comandos: los de string y hash que usa el código, `SCAN`, `EVAL`/`EVALSHA`, `SCRIPT LOAD`/`EXISTS`, `TIME`. Sin `KEYS`, `FLUSHALL`, `CONFIG`, `ACL`, `SHUTDOWN` |
| `tiendaya_relevo` | relevo del outbox (`REDIS_URL_RELEVO`) | `carrito:*`, `oferta:*:reservas` | `HGET`, `HDEL`, `EVAL`/`EVALSHA`, `SCRIPT LOAD`/`EXISTS` |
| `tiendaya_lectura` | RedisInsight (perfil `visores`) | todas, **solo lectura** (`%R~*`) | `@read`, `INFO`, `SCAN`; sin escritura ni scripts |
| `tiendaya_admin` | operación y scripts de prueba (`REDIS_URL_ADMIN`) | todas | todos |

Las listas de comandos salen de un inventario del código (`grep` de las llamadas `redis_client.*` y de los `redis.call(...)` de los 9 scripts Lua), no de categorías genéricas. Las contraseñas se guardan en el archivo como **hash SHA-256** (`#<hash>`), nunca en texto plano; las de desarrollo están en `.env.example`.

En el backend, el relevo usa su propio cliente (`redis_relevo` en `backend/app/extensions.py`); `ofertas_redis._ejecutar` recibe el cliente a usar.

## Justificación

- **Consistencia:** los permisos se aplican también **dentro de los scripts Lua**. Un script ejecutado por `tiendaya_api` que intente leer una key ajena o hacer `FLUSHALL` falla con `ACL failure in script`. Sin esto, `EVAL` sería una puerta trasera a cualquier comando.
- **Mínimo privilegio por servicio:** el relevo solo hace lo que el outbox necesita. Aunque su código tuviera un error, no puede subir el cupo de una oferta (`INCRBY` denegado) ni borrar un carrito entero (`DEL` denegado).
- **Patrón de consulta:** las keys ya tenían prefijos por dominio (`carrito:`, `oferta:`), así que los patrones de key de ACL se aplican sin renombrar nada.
- **Costo operativo:** un archivo de texto en el repositorio y un parámetro en el `docker-compose.yml`. Cada integrante lo obtiene con `git pull` y `docker compose up -d`; no hay que crear usuarios a mano.

## Hallazgo durante la implementación: `default` y el AOF

La primera versión deshabilitaba `default` **y le quitaba todos los permisos** (`user default off -@all`). Al reiniciar Redis, los cambios hechos por scripts Lua **se perdían**: Redis 7.4 guarda el efecto de un script en el AOF como `MULTI ... EXEC`, y al reproducirlo comprueba los comandos con los permisos de `default`; con `-@all` descarta la transacción (`NOPERM ... after processing the command 'exec'` en el log). Se reprodujo con un `EVAL` que escribe dos campos: tras `docker compose restart redis` el hash no existía.

Corrección: `user default off resetpass ~* &* +@all`. `default` sigue sin poder usarse (`off`, sin contraseña válida: una conexión anónima recibe `NOAUTH` y `AUTH default` responde `WRONGPASS ... user is disabled`), pero el replay del AOF vuelve a funcionar. Verificado: el hash escrito por script sobrevive al reinicio. Registrado como [H-025](../hallazgos.md).

## Consecuencias

**Beneficios:**
- Evidencia: `backend/scripts/prueba_control_acceso_redis.py`, 37/37 verificaciones ([salida](../evidencia/prueba_control_acceso_redis.txt)): conexión anónima y `default` rechazados, y cada usuario puede lo suyo y nada más (incluidos scripts Lua que intentan salir de su alcance).
- Las pruebas existentes pasan sin cambios funcionales con las ACL activas: oferta bajo concurrencia (50 solicitudes, 10 vendidas, 0 sobreventa) y fallas del checkout (40/40, incluido el relevo con su usuario restringido).
- RedisInsight queda en solo lectura: mirar los datos ya no puede romperlos.

**Limitaciones asumidas:**
- **Todos deben actualizar su `.env`**: con el `REDIS_URL` viejo (`redis://localhost:6379/0`) el backend recibe `NOAUTH`.
- `redis-cli` dentro del contenedor ahora necesita usuario: `docker compose exec redis redis-cli --user tiendaya_admin --pass admin_tiendaya_2026`.
- Las contraseñas de desarrollo están en `.env.example` y en el `docker-compose.yml` (la del visor). En producción irían en un gestor de secretos y el `users.acl` se generaría en el despliegue.
- No hay TLS: las credenciales viajan en claro dentro de la red local de Docker.
- `tiendaya_api` necesita los prefijos `carrito:*` y `oferta:*` juntos porque varios scripts Lua tocan una oferta y un carrito en la misma operación atómica; separar carrito y ofertas en dos usuarios obligaría a partir esos scripts y perder la atomicidad.
- Elasticsearch y MongoDB siguen sin autenticación (ver la tabla de control de acceso en [`arquitectura-final.html`](../arquitectura-final.html)); es el siguiente paso natural, con el mismo criterio de un rol por servicio.
