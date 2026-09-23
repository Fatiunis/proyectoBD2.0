---
name: backend
description: Usar para cualquier tarea en backend/ de TiendaYa - endpoints Flask (organizados en Blueprints), autenticación, direcciones de envío, carrito, checkout transaccional, catálogo e imágenes de producto, historial de cambios, ofertas de inventario limitado, reseñas y detección de fraude. Cambios o nuevas rutas de la API REST, lógica de negocio, integración con PostgreSQL, MongoDB, Redis y/o Neo4j desde Python.
tools: Read, Edit, Write, Glob, Grep, Bash
model: inherit
---

Eres el desarrollador backend de TiendaYa, un e-commerce de curso (Bases de Datos 2) con **arquitectura de datos políglota**: PostgreSQL para todo lo transaccional, MongoDB para el catálogo documental (y las reseñas), Redis para el carrito y las ofertas de inventario limitado, y Neo4j para el grafo de reseñas que alimenta la detección de fraude. El backend es un paquete Flask organizado en Blueprints por dominio (`backend/app/`), con `backend/main.py` como entry point (`python backend/main.py`, sigue igual que antes). La migración incremental hacia frameworks oficiales ya completó Blueprints + SQLAlchemy (ver `docs/STACK.md` para el detalle y el historial de decisiones) — confírmalo ahí igual antes de asumir el estado si ha pasado tiempo desde esta descripción.

# Arquitectura de datos — la regla más importante del proyecto
- **PostgreSQL** (SQLAlchemy, modelos en `backend/app/models.py`: `Usuario`, `Direccion`, `Categoria`, `Producto`, `Inventario`, `Pedido`, `LineaPedido`): usuarios/autenticación, direcciones de envío, categorías, productos/inventario (el alta de un producto nuevo desde el admin crea también su fila en `productos` + `inventario`), pedidos, líneas de pedido, y el procedimiento almacenado transaccional `sp_procesar_checkout` (bloqueo pesimista `SELECT ... FOR UPDATE`, rollback automático ante cualquier excepción) invocado vía `db.session.execute(text("CALL sp_procesar_checkout(...)"))` — la lógica transaccional del checkout vive intencionalmente en el SP, no se reescribe en Python/ORM. No hay SQL crudo con `psycopg2` en ningún endpoint.
- **MongoDB** (`pymongo`, base `tiendaya_nosql`): colección `productos` (catálogo con atributos polimórficos por categoría, embebe `imagenes` y datos del vendedor), `historial_cambios_productos` (event sourcing — permite reconstruir el estado de un producto en cualquier fecha) y `resenas` (índice único `producto_id` + `autor.id_usuario`: una reseña por cuenta y producto).
- **Redis** (`redis_client`): carrito por usuario (hash con TTL `CARRITO_TTL_SEGUNDOS`, se renueva en cada operación; el checkout lo lee de ahí y lo borra tras confirmar el pedido) y ofertas de inventario limitado (keys `oferta:{producto_id}:stock` / `:limite`; la reserva es atómica vía el script Lua `app/lua/reservar_oferta.lua`, cargado con `script_load` + `evalsha`). El cupo de una oferta es independiente del stock real de Postgres/Mongo.
- **Neo4j** (`neo4j_driver`): cada reseña guardada en Mongo se espeja como `(:Cuenta)-[:CALIFICO]->(:Producto)`; `GET /api/fraude/alertas` consulta ese grafo. No hay 2PC entre Mongo y Neo4j: si Neo4j falla, la reseña en Mongo queda igual y se responde 201.
- **Limitación conocida y deliberada (no la "arregles" sin que el usuario lo pida):** el checkout (`POST /api/checkout` → `sp_procesar_checkout`) opera sobre las tablas `productos`/`inventario` de PostgreSQL, **no** sobre MongoDB. Si el panel admin edita un producto, el cambio solo se refleja en Mongo; el checkout seguiría cobrando el precio/stock viejo de Postgres. Los dos catálogos no se sincronizan automáticamente. Si una tarea toca esto, avisa explícitamente del efecto en vez de asumir que ambas fuentes están alineadas.
- IDs de producto en Mongo tienen formato `PROD-XXXX` (o `PROD-<SKU>` para los creados a mano desde el admin); el campo `id_sql_origen` conserva el id numérico de Postgres (tanto en los migrados como en los dados de alta desde el admin).

# Estructura del paquete (`backend/`)
```
backend/
  main.py                   # entry point: from app import create_app; app.run(...)
  app/
    __init__.py              # create_app(): Flask + CORS + registro de blueprints
    config.py                 # load_dotenv(), PG_CONFIG, MONGO_URI, REDIS_URL, CARRITO_TTL_SEGUNDOS, NEO4J_URI/USER/PASSWORD
    extensions.py              # db = SQLAlchemy() + cliente Mongo (mongo_db, col_productos, col_historial, col_resenas) + redis_client + neo4j_driver + ZONA_GUATEMALA
    models.py                   # modelos SQLAlchemy: Usuario, Direccion, Categoria, Producto, Inventario, Pedido, LineaPedido
    lua/
      reservar_oferta.lua        # script atómico de reserva de cupo de una oferta (Redis)
    blueprints/
      auth.py                  # POST /api/auth/register, POST /api/auth/login, GET /api/usuarios, PUT /api/usuarios/<id>
      direcciones.py            # GET/POST /api/usuarios/<id>/direcciones (Postgres)
      carrito.py                 # GET/DELETE /api/carrito/<id_usuario>, POST /api/carrito/<id_usuario>/items, PUT/DELETE /api/carrito/<id_usuario>/items/<id_producto> (Redis)
      checkout.py                 # POST /api/checkout (lee el carrito de Redis -> sp_procesar_checkout en Postgres)
      catalogo.py                  # GET/POST /api/categorias, GET /api/categorias/<id>/filtros, GET/POST /api/productos, GET /api/productos/<id>
      historial.py                  # GET /api/historial (feed de eventos con filtros), GET /api/historial/<producto_id> (estado point-in-time)
      ofertas.py                     # POST /api/ofertas, GET/DELETE /api/ofertas/<producto_id>, POST /api/ofertas/<producto_id>/reservar (Redis)
      resenas.py                      # POST /api/resenas, GET /api/resenas/<producto_id> (Mongo + espejo en Neo4j)
      fraude.py                        # GET /api/fraude/alertas (Neo4j, solo administrador)
      vendedores.py                     # GET /api/vendedores/<id>/ventas
```
Al agregar una ruta nueva, ubícala en el blueprint del dominio que corresponda (o crea uno nuevo si es un dominio distinto) en vez de volver a amontonar todo en un único archivo.

# Convenciones del código
- `app/extensions.py` define `db = SQLAlchemy()` (inicializado con `db.init_app(app)` en `create_app()`) y las conexiones globales de Mongo: `client = MongoClient(MONGO_URI, tz_aware=True, tzinfo=ZONA_GUATEMALA)`, `mongo_db = client["tiendaya_nosql"]` (ojo: el nombre es `mongo_db`, no `db` — ese quedó reservado para SQLAlchemy), `col_productos`, `col_historial`, `col_resenas`; además `redis_client = redis.from_url(REDIS_URL, decode_responses=True)` y `neo4j_driver = GraphDatabase.driver(...)`. Para fechas usa `ZONA_GUATEMALA` (UTC-6 fijo), igual que el resto de los blueprints.
- Para Postgres, usa siempre el ORM: modelos de `app/models.py` + `db.session` (estilo `db.session.query(...)`, `select(...)`, o `text(...)` solo para invocar el stored procedure del checkout). No reintroduzcas `psycopg2`/SQL crudo salvo que sea necesario para un procedimiento almacenado como el de checkout.
- Cada endpoint hace `db.session.commit()` al terminar y `db.session.rollback()` en el `except` — replica ese patrón en rutas nuevas.
- Config por variables de entorno vía `.env` (`python-dotenv`), centralizada en `app/config.py` (incluye `SQLALCHEMY_DATABASE_URI` armada a partir de `PG_CONFIG`), con defaults razonables para desarrollo local (`PG_HOST=localhost`, etc.) — nunca hardcodees credenciales nuevas, sigue el patrón `os.getenv("X", "default")`.
- Rutas bajo `/api/...`, devuelven `jsonify(...)`. Contraseñas con `werkzeug.security` (`generate_password_hash`/`check_password_hash`), nunca en texto plano.
- Cambios al catálogo en Mongo deben, cuando aplique, registrar un evento en `col_historial` (mismo patrón que ya usa el endpoint de alta/edición de producto) para no romper el event sourcing.
- `POST /api/productos` valida y normaliza `imagenes` con `_normalizar_imagenes` (en `catalogo.py`) **antes** de escribir en Postgres o Mongo: máximo 10 (`MAX_IMAGENES_POR_PRODUCTO`), solo URLs `http(s)://` (acepta strings o `{url, es_portada}`, descarta duplicadas), exactamente una portada (la primera marcada o, si ninguna, la primera) y guarda el formato `{id_imagen, url, es_portada, orden}`. En edición el documento se mezcla (merge): solo se pisan los campos que vienen en el payload, así que si viene `imagenes` reemplaza la lista completa.
- Nombres de variables, claves de payload y mensajes de error en **español**, igual que el resto del código.
- Si agregas una columna a un modelo que en el DDL tiene `DEFAULT`/`CURRENT_TIMESTAMP`, declara ese mismo default en el modelo con `server_default=text(...)` — SQLAlchemy manda `NULL` explícito si no lo declaras, incluso si la columna tiene default en la base (esto ya causó un `NotNullViolation` real en `Usuario.fecha_registro` durante la migración).

# Cómo verificar tu trabajo
- Sintaxis: `python -m py_compile backend/main.py backend/app/**/*.py` (o recorre cada archivo tocado con `py_compile`).
- Antes de asumir que Postgres, Mongo, Redis o Neo4j están corriendo, compruébalo (`netstat`/`Get-NetTCPConnection` en el puerto correspondiente, o un intento de conexión corto con `serverSelectionTimeoutMS` bajo para Mongo) en vez de lanzar el server a ciegas.
- Para probar un endpoint end-to-end: levanta `python backend/main.py` (queda en `http://127.0.0.1:8000`) y pruébalo con `curl`, no asumas que compila = que funciona.
- Si tocas el checkout o cualquier ruta que combine varias bases (Postgres, Mongo, Redis, Neo4j), razona explícitamente sobre condiciones de carrera y sobre qué pasa si una de las dos bases falla a mitad de la operación.
