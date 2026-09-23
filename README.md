# TiendaYa

Portal de comercio electrónico con arquitectura de datos políglota (proyecto de curso — Bases de Datos 2).

- **PostgreSQL**: usuarios/autenticación, direcciones, categorías, pedidos, líneas de pedido, pagos, inventario, y el procedimiento transaccional de checkout.
- **MongoDB**: catálogo de productos (atributos polimórficos por categoría), historial de cambios (event sourcing) y reseñas de producto.
- **Redis**: carrito de compra (expira por inactividad) y la oferta de inventario limitado (reserva atómica, sin sobreventa bajo concurrencia).
- **Neo4j**: grafo de reseñas para detectar fraude (cuentas que se califican entre sí de forma reiterada sobre los mismos productos).
- **Backend**: Flask con application factory (`backend/main.py` → `backend/app/create_app()`), organizado en **Blueprints** por dominio y **SQLAlchemy** para todo el acceso a PostgreSQL. Expone una API REST consumida por el frontend.
- **Frontend**: **Vue 3 + Vite + Tailwind v4** (`frontend/app/`) — sitio público (catálogo, carrito, checkout, reseñas, oferta límite) y panel admin (catálogo, categorías, usuarios, ventas, historial, fraude).

## Novedades de la Entrega 2 (léelo si ya tenías el proyecto montado de antes)

Si ya tenías TiendaYa corriendo de una entrega anterior, esto es lo que se agregó y lo que necesitas hacer para ponerte al día — no es opcional, el backend no arranca bien sin Redis/Neo4j configurados:

1. **Instala Docker + Docker Compose** si no lo tienes (requisito nuevo).
2. **`git pull`** para traer `docker-compose.yml`, los blueprints nuevos, y los scripts de semilla/migración nuevos.
3. **Reinstala dependencias de Python**: `pip install -r requirements.txt` (agrega `redis`, `neo4j`, `requests`).
4. **Agrega las variables de entorno nuevas a tu `.env`** (Redis y Neo4j — ver el paso 2 de instalación más abajo, o copia de nuevo `.env.example` y ajusta).
5. Sigue los pasos **5 en adelante** de la sección de Instalación (levantar Redis/Neo4j, aplicar constraints, sembrar compradores y reseñas de prueba) — son pasos nuevos que no existían antes.

Qué se construyó, en concreto:
- **Carrito de compra**: ya no vive en `localStorage`, vive en Redis (`carrito:{id_usuario}`, expira a los 30 min de inactividad). Requiere sesión iniciada. El checkout toma los productos de ese carrito en Redis (no de lo que envía el navegador), así que un carrito expirado ya no se puede pagar. La referencia de pago la genera el backend automáticamente (formato `TY-AAAAMMDDHHMMSS-XXXXXX`). Al confirmar la compra se muestra un resumen con el número de pedido, la referencia y un botón "Dejar reseña" por cada producto comprado.
- **Oferta de inventario limitado** ("flash sale"): cupo independiente por producto en Redis, con una **duración** que se indica al crearla (la oferta vence sola al terminar esa ventana de tiempo), reservado con un script Lua atómico (sin sobreventa, verificado con 50 solicitudes concurrentes contra un límite de 10 → 10 éxitos, 0 sobreventa). Se crea y se cierra desde la página de detalle del producto; solo puede hacerlo el vendedor dueño del producto o un administrador.
- **Reseñas de producto**: sistema nuevo desde cero — cualquier comprador puede calificar (1-5) y comentar un producto una sola vez, visible en `/producto/:id`. El formulario está al final de la página del producto; se llega directo con el enlace "★ Escribir reseña" bajo el precio, o con "Dejar reseña" desde el resumen de compra (URL `/producto/:id#escribir-resena`).
- **Detección de fraude en reseñas**: cada reseña se sincroniza a un grafo en Neo4j; el panel admin (`/admin/fraude`, solo administrador) corre una consulta de varios saltos que señala cuentas que se recalifican entre sí sobre los mismos productos.
- **Documentación nueva**: [`docs/decisiones/ADR-002-grafos-vs-columnar.md`](docs/decisiones/ADR-002-grafos-vs-columnar.md) (por qué Neo4j y no Cassandra), [`docs/decisiones/ADR-003-redis-carrito-y-oferta.md`](docs/decisiones/ADR-003-redis-carrito-y-oferta.md) (por qué Redis para el carrito y la oferta), [`docs/arquitectura.md`](docs/arquitectura.md) (diagrama actualizado) y [`docs/informe-entrega-2.md`](docs/informe-entrega-2.md) (informe de la entrega).

## Estado del proyecto

**Fase Inicial** — completa: esquema relacional en 3FN, datos semilla, checkout como transacción atómica (`sp_procesar_checkout`, con bloqueo pesimista y rollback automático) expuesto en `POST /api/checkout`.

**Entrega 1** — completa: catálogo documental con atributos por categoría, migración Postgres→Mongo, índice compuesto, índice de texto para búsqueda, consultas de agregación, historial de cambios con reconstrucción point-in-time, panel admin (catálogo, categorías, usuarios, historial).

**Migración a frameworks** — completa: backend en Blueprints + SQLAlchemy, frontend migrado por completo a Vue 3 + Vite. El sitio HTML/JS vanilla original ya se retiró del repositorio. Detalle en [`docs/STACK.md`](docs/STACK.md).

**Entrega 2** — completa: carrito y oferta de inventario limitado sobre Redis, sistema de reseñas y detección de fraude sobre Neo4j (ver sección de arriba). Bitácora completa de qué se hizo, por qué, y qué se verificó en [`docs/STACK.md`](docs/STACK.md).

**Informe de la Entrega 1:** [`docs/Entrega 1 Base de Datos 2 (1).pdf`](<docs/Entrega 1 Base de Datos 2 (1).pdf>) (diagrama entidad-relación, justificación de la normalización y decisiones de embeber/referenciar).

**Pendiente (documentación, no código):** explicar cómo `lineas_pedido` (PostgreSQL) referencia productos que ahora viven en MongoDB (vía el campo `id_sql_origen`).

**Limitaciones conocidas:**
- El checkout opera sobre `productos`/`inventario` de PostgreSQL, no sobre MongoDB — editar un producto desde el admin solo se refleja en Mongo, el checkout sigue usando precio/stock de Postgres. Los dos catálogos no se sincronizan automáticamente.
- La oferta de inventario limitado vive enteramente en Redis, independiente del inventario real de Postgres — es un cupo aparte para la mecánica de flash sale, no descuenta stock del catálogo.
- La sincronización de una reseña hacia Neo4j es de mejor esfuerzo (sin 2PC): si Neo4j no está disponible al crear la reseña, esta igual queda guardada en Mongo y solo se registra una advertencia en el log del backend.
- El historial de cambios del producto no registra el stock: cada evento guarda nombre, descripción, precio, estado activo/inactivo y atributos. La reconstrucción por fecha indica si el producto estaba disponible para la venta (activo), pero no cuántas unidades había en existencia en ese momento.

## Requisitos previos

- Python 3.10+
- PostgreSQL corriendo localmente (o accesible por red)
- MongoDB corriendo localmente (o accesible por red)
- Node.js `^20.19.0` o `>=22.12.0` + npm (requerido por Vite para levantar el frontend)
- **Docker + Docker Compose** (para levantar Redis y Neo4j — requerido desde la Entrega 2)

## Instalación

Sigue los pasos en orden. Si ya tenías el proyecto montado de una entrega anterior, puedes saltar directo al paso 5.

### 1. Entorno Python

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tu contraseña de PostgreSQL local (el resto de valores por defecto sirven si usas los puertos/nombres estándar, incluidos los de Redis/Neo4j que levanta el `docker-compose.yml` de este repo):

```
PG_HOST=localhost
PG_PORT=5432
PG_DBNAME=tiendaya_db
PG_USER=postgres
PG_PASSWORD=tu_password_local

MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=tiendaya_nosql

REDIS_URL=redis://localhost:6379/0
CARRITO_TTL_SEGUNDOS=1800

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=tiendaya123
```

`.env` está en `.gitignore` — nunca lo subas al repositorio.

### 3. Crear la base de datos y cargar el esquema (PostgreSQL)

Crea la base de datos vacía:

```bash
psql -U postgres -c "CREATE DATABASE tiendaya_db;"
```

Carga el esquema, el procedimiento de checkout y los primeros 4 productos:

```bash
psql -U postgres -d tiendaya_db -f database/postgres/ddl_tiendaya.sql
```

Carga los 11 productos adicionales de la semilla (15 en total):

```bash
psql -U postgres -d tiendaya_db -f database/postgres/datos_semilla_productos.sql
```

Si no tienes el cliente `psql` instalado, puedes correr cualquiera de los `.sql` con este atajo en Python (usa las credenciales de tu `.env`):

```bash
python -c "import psycopg2, os; from dotenv import load_dotenv; load_dotenv(); c=psycopg2.connect(host=os.getenv('PG_HOST'), port=os.getenv('PG_PORT'), dbname=os.getenv('PG_DBNAME'), user=os.getenv('PG_USER'), password=os.getenv('PG_PASSWORD')); cur=c.cursor(); cur.execute(open('database/postgres/ddl_tiendaya.sql', encoding='utf-8').read()); c.commit(); print('DDL aplicado')"
```

(cambia la ruta del archivo para correr también los demás `.sql` de este paso y del paso 5).

### 4. Migrar el catálogo a MongoDB

Con PostgreSQL ya poblado (los 15 productos), corre la migración — es idempotente: si la vuelves a correr, **recrea las colecciones desde cero** (`drop()` + reinserción), así que es seguro correrla de nuevo cada vez que haces `pull` de una rama que la haya tocado.

```bash
python database/migrations/migracion_postgres_a_mongo.py
```

Esto crea `productos` y `historial_cambios_productos` en Mongo, con los eventos iniciales de creación, fotos reales por producto (Unsplash, mapeadas por SKU en el propio script) y los índices (`idx_categoria_activo_precio`, `idx_sku_unico`, `idx_historial_producto_fecha`, `idx_texto_busqueda`). **Si ya tenías el catálogo migrado de antes, vuelve a correr este script** para que tu Mongo local quede igual al del resto del equipo.

### 5. Levantar Redis y Neo4j, y sembrar los datos de la Entrega 2

Desde la raíz del repo:

```bash
docker compose up -d
```

Levanta Redis (puerto `6379`, usado por el carrito y la oferta de inventario limitado) y Neo4j (puertos `7474` browser / `7687` bolt, usuario `neo4j` / contraseña `tiendaya123` — usado por la detección de fraude en reseñas). Dale unos 15-20 segundos a Neo4j antes de seguir, tarda más que Redis en quedar listo (puedes verificar con `docker compose logs neo4j` hasta ver `Started.`).

Aplica las constraints de unicidad del grafo (una sola vez, seguro de repetir):

```bash
docker compose exec neo4j cypher-shell -u neo4j -p tiendaya123 -f /dev/stdin < database/neo4j/01_constraints.cypher
```

Amplía la semilla de compradores y sus direcciones de envío (necesario para que la detección de fraude tenga variedad de cuentas y para poder probar checkout con ellos — es seguro correrlo aunque tu base ya tenga usuarios propios, usa `ON CONFLICT (email) DO NOTHING` en vez de IDs fijos):

```bash
psql -U postgres -d tiendaya_db -f database/postgres/datos_semilla_usuarios.sql
```

Siembra reseñas de prueba con un patrón de fraude detectable (ruido legítimo + un grupo de 4 cuentas que se recalifican entre sí sobre los mismos productos + un par de control que no debería marcarse como sospechoso). Es idempotente — puedes correrlo de nuevo sin duplicar datos:

```bash
python database/migrations/sembrar_resenas_fraude.py
```

### 6. Levantar el backend

```bash
python backend/main.py
```

Flask queda escuchando en `http://127.0.0.1:8000`. Internamente `backend/main.py` solo llama a `create_app()`; las rutas reales viven organizadas por dominio en `backend/app/blueprints/` (ver estructura más abajo o `docs/STACK.md` para el detalle completo).

### 7. Levantar el frontend

```bash
cd frontend/app
npm install
npm run dev
```

Vite queda escuchando en `http://localhost:5173` (o el siguiente puerto libre si ese ya está en uso) y habla con el backend en `http://127.0.0.1:8000`. Rutas: `/` sitio público (catálogo, carrito, checkout, login/registro), `/producto/:id` detalle de producto (reseñas y oferta de inventario limitado si el producto tiene una activa), `/admin` panel admin (catálogo, categorías, usuarios, ventas, historial, fraude — este último solo para administrador).

Para un build de producción: `npm run build` (genera `frontend/app/dist/`).

**Si el repositorio está dentro de OneDrive** (o en otra carpeta sincronizada): `vite.config.js` usa `server.watch.usePolling`, porque OneDrive no siempre avisa de los cambios en los archivos y Vite podía seguir sirviendo versiones viejas de algunos módulos (por ejemplo, un carrito que no se vaciaba al comprar). Si igual ves un comportamiento que no coincide con el código, detén Vite, vuelve a correr `npm run dev` y recarga el navegador con **Ctrl+F5**.

## Credenciales de prueba

Todos los usuarios semilla usan la misma contraseña: **`Tiendaya123!`**

| Email | Rol | Notas |
|---|---|---|
| admin@tiendaya.com | administrador | Acceso completo a `/admin` (catálogo, categorías, usuarios, historial, fraude) |
| ventas@techstore.com | vendedor | Acceso a `/admin` acotado a su propio catálogo y "Mis ventas" (sin Categorías/Usuarios/Fraude) |
| contacto@modaurbana.com | vendedor | Igual que el anterior |
| carlos.mendez@email.com | comprador | Dirección de envío registrada |
| sofia.lopez@email.com | comprador | Dirección de envío registrada |

El registro público (`/`) solo crea cuentas de `comprador`. Para crear cuentas de `vendedor` o `administrador` nuevas, usa la pestaña "Usuarios" del panel admin.

Tras correr `database/postgres/datos_semilla_usuarios.sql` (paso 5) hay **10 compradores adicionales**, cada uno con su propia dirección de envío (misma contraseña `Tiendaya123!`), por ejemplo `maria.torres@email.com` — necesarios para checkout de prueba y para que la detección de fraude tenga variedad de cuentas.

## Estructura del repositorio

```
backend/
  main.py                    Entry point: from app import create_app; app.run(..., threaded=True)
  app/
    __init__.py                 create_app(): Flask + CORS + registro de blueprints
    config.py                    load_dotenv(), PG_CONFIG, MONGO_URI, REDIS_URL, NEO4J_URI...
    extensions.py                 db (SQLAlchemy), Mongo (col_productos, col_historial, col_resenas), redis_client, neo4j_driver
    models.py                      Modelos SQLAlchemy: Usuario, Categoria, Producto, Inventario, Pedido, LineaPedido
    lua/
      reservar_oferta.lua           Check-and-decrement atómico para la oferta de inventario limitado
    blueprints/
      auth.py                       /api/auth/register, /api/auth/login, /api/usuarios, /api/usuarios/<id>
      checkout.py                    /api/checkout
      catalogo.py                     /api/categorias, /api/categorias/<id>/filtros, /api/productos, /api/productos/<id>
      historial.py                     /api/historial, /api/historial/<producto_id>
      vendedores.py                     /api/vendedores/<id>/ventas
      carrito.py                        /api/carrito/<id_usuario> (Redis, Entrega 2)
      ofertas.py                        /api/ofertas, /api/ofertas/<producto_id>/reservar (Redis + Lua, Entrega 2)
      resenas.py                        /api/resenas (Mongo + sync a Neo4j, Entrega 2)
      fraude.py                         /api/fraude/alertas (consulta Cypher de 3 saltos, Entrega 2)
  scripts/
    prueba_concurrencia_oferta.py  Evidencia de que la oferta límite no permite sobreventa bajo concurrencia
database/
  postgres/
    ddl_tiendaya.sql               Esquema 3FN + semilla + sp_procesar_checkout
    datos_semilla_productos.sql    11 productos adicionales (15 en total)
    datos_semilla_usuarios.sql     10 compradores + direcciones adicionales (Entrega 2, IDs dinámicos vía ON CONFLICT)
  mongo/
    01_indexes.js                  Índices de referencia (ya se crean también desde la migración)
    02_aggregation_queries.js      Consultas de agregación de referencia
  neo4j/
    01_constraints.cypher          Constraints de unicidad para nodos Cuenta/Producto (Entrega 2)
  migrations/
    migracion_postgres_a_mongo.py  ETL: aplana productos de Postgres a documentos Mongo + fotos reales por SKU
    sembrar_resenas_fraude.py       Siembra reseñas con un patrón de fraude detectable (Entrega 2, idempotente)
frontend/
  app/                        Sitio Vue 3 + Vite (único frontend, ver docs/STACK.md)
    src/
      views/                       VistaPublica.vue, VistaDetalleProducto.vue, VistaAdmin.vue
      components/publico/           Catálogo, filtros, tarjeta de producto, carrito, checkout, login/registro, reseñas, oferta límite
      components/admin/              Catálogo, categorías, usuarios, ventas, historial, fraude (GestionFraude.vue)
      composables/                    useSesion, useToast, useCategorias, useCarrito (Redis-backed, Entrega 2)
      services/api.js                 apiFetch (wrapper de fetch contra el backend)
docs/
  STACK.md                   Bitácora técnica completa: qué cambió en cada fase, por qué, y qué se verificó
  arquitectura.md            Diagrama de arquitectura actualizado (Entrega 2)
  decisiones/
    ADR-002-grafos-vs-columnar.md   Registro de decisión: Neo4j para fraude en reseñas, columnar descartado por ahora
    ADR-003-redis-carrito-y-oferta.md  Registro de decisión: Redis para el carrito y la oferta de inventario limitado
  informe-entrega-2.md       Informe de la Entrega 2 (decisiones, evidencia y responsabilidades)
docker-compose.yml          Redis + Neo4j (Entrega 2)
requirements.txt
.env.example
```
