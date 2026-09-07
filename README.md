# TiendaYa

Portal de comercio electrónico con arquitectura de datos políglota (proyecto de curso — Bases de Datos 2).

- **PostgreSQL**: usuarios/autenticación, direcciones, categorías, pedidos, líneas de pedido, pagos, inventario, y el procedimiento transaccional de checkout.
- **MongoDB**: catálogo de productos (atributos polimórficos por categoría) e historial de cambios (event sourcing) para reconstruir el estado de un producto en cualquier fecha.
- **Backend**: Flask con application factory (`backend/main.py` → `backend/app/create_app()`), organizado en **Blueprints** por dominio y **SQLAlchemy** para todo el acceso a PostgreSQL. Expone una API REST consumida por el frontend.
- **Frontend**: **Vue 3 + Vite + Tailwind v4** (`frontend/app/`) — sitio público (catálogo, carrito, checkout) y panel admin (catálogo, categorías, usuarios, ventas, historial).

## Estado del proyecto

**Fase Inicial** — completa: esquema relacional en 3FN, datos semilla, checkout como transacción atómica (`sp_procesar_checkout`, con bloqueo pesimista y rollback automático) expuesto en `POST /api/checkout`.

**Entrega 1** — completa en código: catálogo documental con atributos por categoría, migración Postgres→Mongo, índice compuesto, índice de texto para búsqueda, consultas de agregación, historial de cambios con reconstrucción point-in-time, panel admin (catálogo, categorías, usuarios, historial).

**Migración a frameworks** — completa: backend reorganizado en Blueprints + SQLAlchemy, y frontend migrado por completo a Vue 3 + Vite (sitio público con carrito/checkout y panel admin completo). El sitio HTML/JS vanilla original ya se retiró del repositorio — Vue es ahora el único frontend. Detalle técnico completo, decisiones y estado exacto de cada pieza en [`docs/STACK.md`](docs/STACK.md).

**Pendiente (documentación, no código):** diagrama entidad-relación, registro de decisión de embeber/referenciar (reseñas, imágenes, vendedor), informe de Entrega 1, y una nota explícita sobre cómo `lineas_pedido` (relacional) se relaciona con los productos que ahora viven en Mongo.

**Limitación conocida:** el checkout sigue operando sobre las tablas `productos`/`inventario` de PostgreSQL (no sobre MongoDB). Si editas un producto desde el panel admin, el cambio solo se refleja en Mongo — el checkout seguiría usando el precio/stock de Postgres. Los dos catálogos no se mantienen sincronizados automáticamente tras la migración inicial.

## Requisitos previos

- Python 3.10+
- PostgreSQL corriendo localmente (o accesible por red)
- MongoDB corriendo localmente (o accesible por red)
- Node.js `^20.19.0` o `>=22.12.0` + npm (requerido por Vite para levantar el frontend)

## Instalación

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

Edita `.env` con tu contraseña de PostgreSQL local (el resto de valores por defecto sirven si usas los puertos/nombres estándar):

```
PG_HOST=localhost
PG_PORT=5432
PG_DBNAME=tiendaya_db
PG_USER=postgres
PG_PASSWORD=tu_password_local

MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=tiendaya_nosql
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

Carga los 5 productos adicionales de la semilla:

```bash
psql -U postgres -d tiendaya_db -f database/postgres/datos_semilla_productos.sql
```

Si no tienes el cliente `psql` instalado, puedes correr cualquiera de los dos `.sql` con este atajo en Python (usa las credenciales de tu `.env`):

```bash
python -c "import psycopg2, os; from dotenv import load_dotenv; load_dotenv(); c=psycopg2.connect(host=os.getenv('PG_HOST'), port=os.getenv('PG_PORT'), dbname=os.getenv('PG_DBNAME'), user=os.getenv('PG_USER'), password=os.getenv('PG_PASSWORD')); cur=c.cursor(); cur.execute(open('database/postgres/ddl_tiendaya.sql', encoding='utf-8').read()); c.commit(); print('DDL aplicado')"
```

(cambia la ruta del archivo para correr también `datos_semilla_productos.sql`).

### 4. Migrar el catálogo a MongoDB

Con PostgreSQL ya poblado (los 9 productos), corre la migración — es idempotente: si la vuelves a correr, **recrea las colecciones desde cero** (`drop()` + reinserción), así que es seguro correrla de nuevo cada vez que haces `pull` de una rama que la haya tocado.

```bash
python database/migrations/migracion_postgres_a_mongo.py
```

Esto crea `productos` y `historial_cambios_productos` en Mongo, con los eventos iniciales de creación, fotos reales por producto (Unsplash, mapeadas por SKU en el propio script) y los índices (`idx_categoria_activo_precio`, `idx_sku_unico`, `idx_historial_producto_fecha`, `idx_texto_busqueda` para la búsqueda por texto del catálogo). **Si ya tenías el catálogo migrado de antes de esta rama, vuelve a correr este script** para que tu Mongo local quede con las mismas imágenes y el mismo índice de texto que el resto del equipo.

### 5. Levantar el backend

```bash
python backend/main.py
```

Flask queda escuchando en `http://127.0.0.1:8000`. Internamente `backend/main.py` solo llama a `create_app()`; las rutas reales viven organizadas por dominio en `backend/app/blueprints/` (ver estructura más abajo o `docs/STACK.md` para el detalle completo).

### 6. Levantar el frontend

```bash
cd frontend/app
npm install
npm run dev
```

Vite queda escuchando en `http://localhost:5173` (o el siguiente puerto libre si ese ya está en uso) y habla con el backend en `http://127.0.0.1:8000`. Rutas: `/` sitio público (catálogo, carrito, checkout, login/registro), `/admin` panel admin (catálogo, categorías, usuarios, ventas, historial).

Para un build de producción: `npm run build` (genera `frontend/app/dist/`).

## Credenciales de prueba

Todos los usuarios semilla (`database/postgres/ddl_tiendaya.sql`) usan la misma contraseña: **`Tiendaya123!`**

| Email | Rol | Notas |
|---|---|---|
| admin@tiendaya.com | administrador | Entra a `/admin` con acceso completo (catálogo, categorías, usuarios, historial) |
| ventas@techstore.com | vendedor | También entra a `/admin`, pero acotado a su propio catálogo y a "Mis ventas" (sin Categorías/Usuarios) |
| contacto@modaurbana.com | vendedor | Igual que el anterior |
| carlos.mendez@email.com | comprador | Tiene dirección de envío registrada (id 1) |
| sofia.lopez@email.com | comprador | Tiene dirección de envío registrada (id 2) |

El registro público (`/`) solo crea cuentas de `comprador`. Para crear cuentas de `vendedor` o `administrador` nuevas, usa la pestaña "Usuarios" del panel admin.

## Estructura del repositorio

```
backend/
  main.py                    Entry point: from app import create_app; app.run(...)
  app/
    __init__.py                 create_app(): Flask + CORS + registro de blueprints
    config.py                    load_dotenv(), PG_CONFIG, MONGO_URI
    extensions.py                 db (SQLAlchemy), cliente Mongo (col_productos, col_historial)
    models.py                      Modelos SQLAlchemy: Usuario, Categoria, Producto, Inventario, Pedido, LineaPedido
    blueprints/
      auth.py                       /api/auth/register, /api/auth/login, /api/usuarios, /api/usuarios/<id>
      checkout.py                    /api/checkout
      catalogo.py                     /api/categorias, /api/categorias/<id>/filtros, /api/productos, /api/productos/<id>
      historial.py                     /api/historial, /api/historial/<producto_id>
      vendedores.py                     /api/vendedores/<id>/ventas
database/
  postgres/
    ddl_tiendaya.sql               Esquema 3FN + semilla + sp_procesar_checkout
    datos_semilla_productos.sql    5 productos adicionales
  mongo/
    01_indexes.js                  Índices de referencia (ya se crean también desde la migración)
    02_aggregation_queries.js      Consultas de agregación de referencia
  migrations/
    migracion_postgres_a_mongo.py  ETL: aplana productos de Postgres a documentos Mongo + fotos reales por SKU
frontend/
  app/                        Sitio Vue 3 + Vite (único frontend, ver docs/STACK.md)
    src/
      views/                       VistaPublica.vue, VistaAdmin.vue
      components/publico/           Catálogo, filtros, detalle, carrito, checkout, login/registro
      components/admin/              Catálogo, categorías, usuarios, ventas, historial
      composables/                    useSesion, useToast, useCategorias, useCarrito
      services/api.js                 apiFetch (wrapper de fetch contra el backend)
docs/
  STACK.md                   Detalle técnico de la migración a frameworks: qué cambió, por qué, y estado exacto
requirements.txt
.env.example
```
