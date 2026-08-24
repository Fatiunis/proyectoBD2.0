# TiendaYa

Portal de comercio electrónico con arquitectura de datos políglota (proyecto de curso — Bases de Datos 2).

- **PostgreSQL**: usuarios/autenticación, direcciones, categorías, pedidos, líneas de pedido, pagos, inventario, y el procedimiento transaccional de checkout.
- **MongoDB**: catálogo de productos (atributos polimórficos por categoría) e historial de cambios (event sourcing) para reconstruir el estado de un producto en cualquier fecha.
- **Backend**: Flask (`backend/main.py`), expone una API REST consumida por el frontend.
- **Frontend**: HTML + Tailwind (CDN) + JS vanilla, sin build step — `frontend/index.html` (sitio público) y `frontend/admin.html` (panel administrativo).

## Estado del proyecto

**Fase Inicial** — completa: esquema relacional en 3FN, datos semilla, checkout como transacción atómica (`sp_procesar_checkout`, con bloqueo pesimista y rollback automático) expuesto en `POST /api/checkout`.

**Entrega 1** — completa en código: catálogo documental con atributos por categoría, migración Postgres→Mongo, índice compuesto, consultas de agregación, historial de cambios con reconstrucción point-in-time, panel admin (catálogo, usuarios, historial).

**Pendiente (documentación, no código):** diagrama entidad-relación, registro de decisión de embeber/referenciar (reseñas, imágenes, vendedor), informe de Entrega 1, y una nota explícita sobre cómo `lineas_pedido` (relacional) se relaciona con los productos que ahora viven en Mongo.

**Limitación conocida:** el checkout sigue operando sobre las tablas `productos`/`inventario` de PostgreSQL (no sobre MongoDB). Si editas un producto desde el panel admin, el cambio solo se refleja en Mongo — el checkout seguiría usando el precio/stock de Postgres. Los dos catálogos no se mantienen sincronizados automáticamente tras la migración inicial.

## Requisitos previos

- Python 3.10+
- PostgreSQL corriendo localmente (o accesible por red)
- MongoDB corriendo localmente (o accesible por red)

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

Con PostgreSQL ya poblado (los 9 productos), corre la migración — es idempotente: si la vuelves a correr, recrea las colecciones desde cero.

```bash
python database/migrations/migracion_postgres_a_mongo.py
```

Esto crea `productos` y `historial_cambios_productos` en Mongo, con los eventos iniciales de creación y los índices (`idx_categoria_activo_precio`, `idx_sku_unico`, `idx_historial_producto_fecha`).

### 5. Levantar el backend

```bash
python backend/main.py
```

Flask queda escuchando en `http://127.0.0.1:8000`.

### 6. Servir el frontend

El frontend usa `fetch` contra el backend, así que sírvelo con un servidor estático (abrirlo como `file://` también funciona en la mayoría de navegadores, pero un servidor local es más consistente):

```bash
cd frontend
python -m http.server 8080
```

- Sitio público: `http://127.0.0.1:8080/index.html`
- Panel admin: `http://127.0.0.1:8080/admin.html`

## Credenciales de prueba

Todos los usuarios semilla (`database/postgres/ddl_tiendaya.sql`) usan la misma contraseña: **`Tiendaya123!`**

| Email | Rol | Notas |
|---|---|---|
| admin@tiendaya.com | administrador | Único rol que puede entrar a `admin.html` |
| ventas@techstore.com | vendedor | |
| contacto@modaurbana.com | vendedor | |
| carlos.mendez@email.com | comprador | Tiene dirección de envío registrada (id 1) |
| sofia.lopez@email.com | comprador | Tiene dirección de envío registrada (id 2) |

El registro público (`index.html`) solo crea cuentas de `comprador`. Para crear cuentas de `vendedor` o `administrador` nuevas, usa la pestaña "Usuarios" del panel admin.

## Estructura del repositorio

```
backend/
  main.py                  API Flask (auth, checkout, catálogo, historial)
database/
  postgres/
    ddl_tiendaya.sql               Esquema 3FN + semilla + sp_procesar_checkout
    datos_semilla_productos.sql    5 productos adicionales
  mongo/
    01_indexes.js                  Índices de referencia (ya se crean también desde la migración)
    02_aggregation_queries.js      Consultas de agregación de referencia
  migrations/
    migracion_postgres_a_mongo.py  ETL: aplana productos de Postgres a documentos Mongo
frontend/
  index.html                Sitio público (catálogo, login/registro de comprador)
  admin.html                 Panel admin (catálogo, usuarios, historial) — login propio
  js/
    common.js                  API_URL, sesión, toasts, miniaturas por categoría
    public.js                   Lógica de index.html
    admin.js                     Lógica de admin.html
requirements.txt
.env.example
```
