# TiendaYa

Portal de comercio electrónico con arquitectura de datos políglota (proyecto de curso — Bases de Datos 2).

- **PostgreSQL**: usuarios/autenticación, direcciones, categorías, pedidos, líneas de pedido, pagos, inventario, y el procedimiento transaccional de checkout.
- **MongoDB**: catálogo de productos (atributos polimórficos por categoría), historial de cambios (event sourcing) y reseñas de producto.
- **Redis**: carrito de compra (expiración por inactividad configurable con `CARRITO_TTL_SEGUNDOS`; por defecto, desde el 2026-10-07, no expira) y la oferta de inventario limitado (reserva atómica, sin sobreventa bajo concurrencia). Con **control de acceso** (ACL): un usuario por servicio y sin acceso anónimo ([ADR-009](docs/decisiones/ADR-009-control-acceso-redis.md)).
- **Neo4j**: grafo de reseñas para detectar fraude (cuentas que se califican entre sí de forma reiterada sobre los mismos productos).
- **Elasticsearch**: buscador del catálogo (tolerancia a errores de tipeo, sinónimos, autocompletado, relevancia y filtros facetados), alimentado desde MongoDB.
- **PostgreSQL + pgvector** (contenedor aparte, puerto 5433): embeddings de las descripciones de producto para **productos relacionados** y **búsqueda semántica** ([ADR-008](docs/decisiones/ADR-008-componente-vectorial.md)).
- **Consistencia del checkout**: una transacción en PostgreSQL con clave de idempotencia y un *outbox* de eventos que se reintentan hacia Redis, MongoDB, Elasticsearch y pgvector ([estrategia](docs/estrategia-consistencia-checkout.md)).
- **Backend**: Flask con application factory (`backend/main.py` → `backend/app/create_app()`), organizado en **Blueprints** por dominio y **SQLAlchemy** para todo el acceso a PostgreSQL. Expone una API REST consumida por el frontend.
- **Frontend**: **Vue 3 + Vite + Tailwind v4** (`frontend/app/`) — sitio público (catálogo paginado, carrito, checkout, reseñas, oferta límite, productos relacionados, página de ofertas flash, "Mi cuenta" del comprador, buscador con facetas) y panel admin (catálogo, categorías, usuarios, ventas, ofertas flash del vendedor, historial, fraude, sincronización).

**Documentos de la entrega final:** [informe](docs/informe-entrega-final.md) · [diagrama de arquitectura final](docs/arquitectura-final.html) (ábrelo en el navegador) · [retrospectiva](docs/retrospectiva.md) · [guion de la presentación](docs/guion-presentacion-final.md).

## Novedades de la entrega final (léelo si ya tenías el proyecto montado)

Dos componentes nuevos: **recomendación semántica con pgvector** y **control de acceso en Redis**. Si ya tenías TiendaYa corriendo de la Entrega 3, haz esto **en orden** (si es tu primera instalación, sigue directamente la [Instalación](#instalación)):

1. **`git pull`**.
2. **Instala la dependencia nueva** (con el venv activado): `pip install -r requirements.txt`. Agrega `sentence-transformers`, que trae PyTorch: son unos 550 MB y tarda unos minutos. En **Linux** instala antes la versión CPU de PyTorch, porque la de PyPI trae CUDA y pesa varios GB: `pip install torch --index-url https://download.pytorch.org/whl/cpu`. En Windows y macOS no hace falta.
3. **Actualiza tu `.env`**. Sin esto el backend **no conecta a Redis** (responde `NOAUTH`). Lo más simple es copiar las líneas nuevas de `.env.example`:
   ```
   REDIS_URL=redis://tiendaya_api:api_tiendaya_2026@localhost:6379/0
   REDIS_URL_RELEVO=redis://tiendaya_relevo:relevo_tiendaya_2026@localhost:6379/0
   REDIS_URL_ADMIN=redis://tiendaya_admin:admin_tiendaya_2026@localhost:6379/0
   VECTORES_URL=postgresql+psycopg2://vectores_app:vectores_app_2026@localhost:5433/tiendaya_vectores
   MODELO_EMBEDDINGS=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
   ```
   (`REDIS_URL` ya existía: **reemplázala**, no la dupliques.)
4. **Levanta los contenedores**: `docker compose up -d`. Redis se recrea con el archivo de usuarios (`database/redis/users.acl`) sin perder datos, y aparece un servicio nuevo, `vectores` (PostgreSQL + pgvector), que la primera vez descarga la imagen (~150 MB) y crea solo su tabla, su índice y sus roles.
5. **Aplica la migración** del outbox en tu PostgreSQL local (agrega el tipo de evento `embedding_producto`; no toca datos y se puede repetir):
   ```bash
   psql -U postgres -d tiendaya_db -f database/postgres/migracion_entrega_final_vectores.sql
   ```
   (sin `psql`, usa el atajo de Python del [paso 3](#3-crear-la-base-de-datos-y-cargar-el-esquema-postgresql) cambiando la ruta del archivo).
6. **Genera los embeddings** del catálogo (la primera vez descarga el modelo, ~460 MB; después tarda unos 10 s):
   ```bash
   python database/migrations/generar_embeddings_productos.py
   ```
   Debe terminar con `pgvector: 1019 embeddings` (o la cantidad de productos de tu Mongo).
7. **Reinicia el backend** (`python backend/main.py`) y Vite (`npm run dev` en `frontend/app/`).
8. **Comprueba** que todo quedó bien:
   ```bash
   python backend/scripts/prueba_control_acceso_redis.py      # 37/37 PASS
   python backend/scripts/prueba_recomendacion.py             # 16/16 PASS (con el backend andando)
   ```

Qué se construyó:
- **Productos relacionados** en la página de cada producto: 6 productos parecidos por el significado de su nombre, categoría y descripción, con su "% afín". Se descartan variantes casi idénticas (la misma laptop con otra RAM) para que la franja muestre productos distintos. Endpoint: `GET /api/productos/<id>/relacionados?limite=6` (`&misma_categoria=1` para restringir a la categoría, `&diversificar=0` para ver los vecinos sin filtrar).
- **Búsqueda por significado** en la página de resultados: debajo de los resultados del buscador aparece "También podría interesarte" (o "Productos por significado" si Elasticsearch no encontró nada). Encuentra, por ejemplo, audífonos para "regalo para alguien que ama la música" aunque ninguna palabra coincida. Endpoint: `GET /api/busqueda/semantica?q=...&limite=12`.
- **Panel admin → Sincronización** muestra cuántos productos tienen embedding y el tipo de evento nuevo "Recalcular embedding (pgvector)". Al guardar un producto en el admin, su embedding se recalcula solo (si cambió el texto); si pgvector está caído, queda pendiente en el outbox.
- **Redis con usuarios**: ya no acepta conexiones sin contraseña. La API entra como `tiendaya_api`, el relevo del outbox como `tiendaya_relevo` (solo puede leer y borrar líneas de carritos y reservas) y RedisInsight como `tiendaya_lectura` (solo lectura). Tabla completa en [Credenciales de los componentes](#credenciales-de-los-componentes).
- Para usar `redis-cli` ahora hay que dar usuario: `docker compose exec redis redis-cli --user tiendaya_admin --pass admin_tiendaya_2026` (los comandos de `redis-cli` de documentos anteriores, como el informe de la Entrega 2, siguen valiendo agregando esas dos opciones).
- Si el contenedor `vectores` no está corriendo, el portal funciona igual: solo desaparecen las franjas de recomendaciones.

## Novedades: detección de fraude ampliada (2026-10-07)

Amplía la detección de fraude en reseñas de la Entrega 2 con cuatro patrones nuevos sobre el mismo grafo de Neo4j. Es un cambio posterior a la Entrega 3 (no es de la Entrega 4). **Lo de la Entrega 2 sigue igual**: `GET /api/fraude/alertas` (los anillos de 3 cuentas), su formato y la semilla `sembrar_resenas_fraude.py` no cambian; todo lo nuevo se agrega al lado. La explicación completa (patrones, umbrales, puntajes y cómo se probó) está en [`docs/deteccion-fraude-ampliada.md`](docs/deteccion-fraude-ampliada.md), y la decisión de diseño en [ADR-007](docs/decisiones/ADR-007-deteccion-fraude-ampliada.md).

Para ponerte al día (con Docker levantado, `docker compose up -d`, y el `venv` activado):

1. **`git pull`**. No hay dependencias nuevas de Python ni de npm, ni migraciones de PostgreSQL o MongoDB.
2. **Aplica las constraints nuevas del grafo** (`Vendedor.id_vendedor` y `Direccion.clave`; seguro de repetir):
   ```bash
   docker compose exec -T neo4j cypher-shell -u neo4j -p tiendaya123 < database/neo4j/02_fraude_ampliado.cypher
   ```
   Ese comando funciona en Git Bash, `cmd` y macOS/Linux. En PowerShell, que no tiene el operador `<`, usa `Get-Content database/neo4j/02_fraude_ampliado.cypher | docker compose exec -T neo4j cypher-shell -u neo4j -p tiendaya123`. (El script del paso siguiente también crea estas constraints si faltan.)
3. **Completa el grafo con lo que ya tenías** (vendedor de cada producto, si cada reseña tiene compra verificada y las direcciones de envío de cada cuenta). Solo agrega al grafo: no borra nada ni toca MongoDB ni PostgreSQL, y se puede repetir:
   ```bash
   python database/migrations/sincronizar_grafo_fraude.py
   ```
4. **Siembra los escenarios de prueba de los patrones nuevos** (crea 24 compradores `@fraude-demo.tiendaya.gt`, ver [Credenciales de prueba](#credenciales-de-prueba), con sus reseñas y direcciones; al terminar vuelve a sincronizar el grafo). Solo borra lo que sembró él mismo en una corrida anterior, así que se puede repetir:
   ```bash
   python database/migrations/sembrar_fraude_ampliado.py
   ```
   Si algún día vuelves a correr `sembrar_resenas_fraude.py` (que borra **todas** las reseñas), repite después los pasos 3 y 4, en ese orden.
5. **Reinicia el backend** (`python backend/main.py`). Si el backend se cae solo al guardar un archivo, con `OSError: [WinError 10038]`, vuelve a lanzarlo: es un problema del recargador de Flask en Windows ([H-019](docs/hallazgos.md)).
6. **Dónde verlo**: entra como `admin@tiendaya.com` al panel `/admin/fraude`. Con la semilla, cada pestaña de patrón tiene al menos una alerta. Por la API: `curl "http://127.0.0.1:8000/api/fraude/resumen?rol_solicitante=administrador"`. Para comprobarlo todo de una vez: `python backend/scripts/prueba_fraude_ampliado.py` (con el backend corriendo; 59/59 verificaciones).

Qué se construyó, en concreto:
- **Cuatro patrones nuevos** en `backend/app/blueprints/fraude.py`, cada uno con umbrales que se pueden cambiar por parámetro:
  - `cuenta_rafaga` (**Cuenta en ráfaga**): una cuenta que publica muchas reseñas en muy poco tiempo, casi todas de productos que nunca compró. Por defecto: 5 reseñas en 1 hora, con al menos 80 % sin compra.
  - `grupo_coordinado` (**Grupo coordinado**): varias cuentas que califican igual los mismos productos casi al mismo tiempo, para subirles la nota (5 estrellas) o para hundirlos (1-2 estrellas). Por defecto: 3 cuentas, 2 productos en común, ventana de 6 horas. A diferencia del anillo de la Entrega 2 (tríos, 3 productos, solo 5 estrellas), detecta grupos de cualquier tamaño y también los ataques con reseñas malas.
  - `sesgo_vendedor_sin_compra` (**Cuenta sesgada hacia un vendedor**): una cuenta que califica varios productos de la misma tienda sin haberle comprado nada, siempre con 5 estrellas (para inflarla) o siempre con 1-2 (para hundirla). Por defecto: 3 reseñas.
  - `cuentas_vinculadas` (**Cuentas vinculadas**): cuentas que envían a la misma dirección y califican igual los mismos productos, probablemente una sola persona con varias cuentas. Por defecto: 2 productos en común.
  - Cada alerta trae las cuentas, los productos, el vendedor (si aplica), un **puntaje de 0 a 100** con su **nivel** (`alto` desde 70, `medio` desde 40, `bajo` por debajo), un motivo en texto y la evidencia (los números que la dispararon).
- **Rutas nuevas** (solo administrador: sin `rol_solicitante=administrador` responden `403`; si Neo4j no está disponible, `503` con `codigo: "GRAFO_NO_DISPONIBLE"`):
  - `GET /api/fraude/patrones`: los 4 patrones, con nombre, descripción y umbrales por defecto.
  - `GET /api/fraude/alertas/<tipo>`: las alertas de un patrón, de mayor a menor puntaje (hasta 50). Acepta los umbrales del patrón como parámetros enteros (por ejemplo `?min_resenas=4`); un valor inválido responde `400` y un tipo desconocido, `404`. Devuelve `{tipo, alertas, total, parametros}`.
  - `GET /api/fraude/resumen`: corre los 4 patrones con sus umbrales por defecto y devuelve cuántas alertas tiene cada uno (`por_tipo`, `total_alertas`) y las cuentas de mayor riesgo (`cuentas_riesgo`, con los patrones en que aparece cada una).
- **Grafo ampliado, sin quitar nada del de la Entrega 2**: nodos `(:Vendedor)` y `(:Direccion)`, relaciones `(:Producto)-[:VENDIDO_POR]->(:Vendedor)` y `(:Cuenta)-[:ENVIA_A]->(:Direccion)`, y la propiedad `compra_verificada` en cada `CALIFICO` (mismo criterio que el "compra verificada" del listado de reseñas). Una dirección se identifica por una clave normalizada (minúsculas y espacios simples en la línea 1, la ciudad y el código postal), así que dos cuentas que escriben la misma dirección con distintas mayúsculas o espacios llegan al mismo nodo. Constraints en `database/neo4j/02_fraude_ampliado.cypher`.
- **Sincronización en mejor esfuerzo** (`backend/app/grafo_fraude.py`, nuevo): al crear una reseña, `resenas.py` guarda además en Neo4j si hubo compra y el vendedor del producto; al crear, editar o borrar una dirección, `direcciones.py` actualiza sus `ENVIA_A`. Igual que el espejo de reseñas de la Entrega 2, si Neo4j falla, la reseña o la dirección quedan guardadas igual y solo se registra una advertencia; `sincronizar_grafo_fraude.py` repara el grafo.
- **Panel `/admin/fraude` con pestañas**: **Resumen** (conteo por patrón y tabla de cuentas de mayor riesgo, con su nivel y los patrones en que aparecen), **Anillos de reseñas** (la consulta de la Entrega 2, la de siempre) y una pestaña por cada patrón nuevo, con su URL propia (`/admin/fraude?patron=cuenta_rafaga`, etc.) y los umbrales editables. El panel muestra el nivel de cada alerta y cuenta, no el puntaje numérico (ese viene en la API). Detalle en [`frontend/app/README.md`](frontend/app/README.md#panel-de-fraude).
- **Prueba automática**: `backend/scripts/prueba_fraude_ampliado.py` (59/59 verificaciones, [evidencia](docs/evidencia/prueba_fraude_ampliado.txt)): cada escenario positivo aparece en su patrón, cada control no, la consulta de la Entrega 2 sigue igual, los errores (`403`, `404`, `400`) y la sincronización de reseñas y direcciones con Neo4j. Para provocar una alerta a mano, la [guía de prueba de fraude](docs/guia-prueba-fraude.md) tiene una sección nueva para los patrones ampliados.
- Hallazgos de esta parte: H-019 a H-024 en [`docs/hallazgos.md`](docs/hallazgos.md).

## Novedades después de la Entrega 3 (2026-10-07)

Son cambios sobre lo entregado en la Entrega 3 (no son de la Entrega 4). Para ponerte al día:

1. **`git pull`**. No hay dependencias nuevas de Python ni de npm, ni migraciones de base de datos.
2. **Revisa `CARRITO_TTL_SEGUNDOS` en tu `.env`**. El valor por defecto pasó de `1800` a `0` (el carrito no expira), pero si copiaste el `.env.example` anterior tu `.env` sigue diciendo `1800`, y ese valor manda sobre el de por defecto: tu carrito seguirá expirando a los 30 minutos de inactividad. Pon `0` si quieres el comportamiento nuevo, o déjalo en un valor mayor que 0 si quieres que expire (por ejemplo, para demostrar la expiración por inactividad de la Entrega 2). La decisión y su justificación están en [ADR-006](docs/decisiones/ADR-006-carrito-sin-expiracion-por-defecto.md).
3. Reinicia el backend (`python backend/main.py`) y Vite (`npm run dev` en `frontend/app/`). En Windows, si Vite falla con `listen EACCES` en el 5173, levántalo con `npm run dev -- --port 5300` (ver el paso 7).

Qué se construyó, en concreto:
- **Ofertas flash visibles en el sitio público**. Antes, una oferta de inventario limitado solo se veía si el comprador entraba a la página de ese producto. Ahora:
  - La barra de navegación tiene un botón **"Ofertas"** con un contador de las ofertas disponibles (con cupo y sin terminar).
  - Ese botón abre la **página de ofertas flash** (`/?vista=ofertas`), con todas las ofertas activas, filtro por categoría y orden "Terminan pronto" o "Mayor descuento". Las agotadas aparecen como "Agotada".
  - **Los filtros de la página de ofertas no son los del sidebar del catálogo.** Los de ofertas (categoría y orden) se aplican en el navegador sobre la única consulta a `GET /api/ofertas?limite=100`, que no acepta parámetros de filtro; no se guardan al salir de la vista. Los del sidebar del catálogo (categoría y atributos, con selección y rango) se aplican en el servidor, con `GET /api/productos?categoria_id=…&atributo_…`, sobre MongoDB. No están conectados: la franja de ofertas muestra siempre todas las ofertas vigentes, sin importar la categoría elegida en el sidebar, aunque la etiqueta "⚡ -X%" sí aparece en las tarjetas que el filtro deja pasar. Detalle en [`frontend/app/README.md`](frontend/app/README.md#ofertas-flash).
  - En el catálogo aparece una **franja de ofertas** compacta (`FranjaOfertasFlash.vue`, dentro de `CatalogoProductos.vue`): ocupa la columna derecha, encima de la grilla de productos, así que el menú de categorías de la izquierda sigue siempre a la vista. Es oscura para que destaque: degradado verde oliva oscuro, texto blanco y acentos ámbar. Muestra hasta 12 ofertas con desplazamiento lateral y un enlace "Ver todas" a la página de ofertas. Se puede contraer a una sola línea ("N ofertas flash activas"); ese estado se recuerda durante la sesión del navegador (`sessionStorage`, clave `tiendaya_franja_ofertas_contraida`). Si no hay ofertas vigentes, la franja no se muestra.
  - Las **tarjetas del catálogo** de un producto con oferta vigente muestran una etiqueta "⚡ -X%" sobre la imagen y el precio de oferta junto al precio normal tachado (`TarjetaProducto.vue`, con `ofertaActivaDe` de `useOfertasFlash.js`, sin pedir nada más al servidor).
  - En la **página del producto**, si tiene una oferta activa, el precio se reemplaza por un bloque con el precio de oferta, el precio normal tachado, el % de descuento, el ahorro, las unidades que quedan y una **cuenta regresiva** hasta el fin de la oferta (o "Sin límite de tiempo" si la oferta no tiene vencimiento, es decir, si `segundos_restantes` viene `null`). El % de descuento es el `descuento_pct` que calcula el servidor. El botón "Reservar a precio de oferta" lleva al bloque de reserva, que funciona igual que antes. Abajo se sigue pudiendo comprar a precio normal.
  - Lo respalda un endpoint público nuevo, **`GET /api/ofertas`** (sin autenticación). Devuelve `{ofertas, total}`: las ofertas activas de productos activos, primero las que todavía tienen cupo y después las agotadas, y dentro de cada grupo las que vencen antes. Cada oferta trae nombre, imagen, `precio_base`, `precio_oferta`, `descuento_pct`, cupo, unidades restantes, reservadas y vendidas, `segundos_restantes`, `fecha_fin`, `categoria` y `vendedor`. Acepta `?limite=` de 1 a 100 (100 por defecto; otro valor responde `400`); `total` cuenta todas las ofertas activas, antes de recortar. `descuento_pct` es un entero: el porcentaje sobre el `precio_base` de MongoDB, redondeado hacia arriba desde ,5 (`ROUND_HALF_UP`) y acotado entre 0 y 99, para que una oferta que cobra algo nunca aparezca como -100 % ([H-017](docs/hallazgos.md)); vale `null` si el producto no tiene `precio_base`. `GET /api/ofertas/<producto_id>` (la oferta de un producto) devuelve ahora también `descuento_pct`, con el mismo cálculo. Para encontrarlas, el backend recorre las claves `oferta:*:id` de Redis con `SCAN` (no con `KEYS`, que bloquea Redis mientras recorre todas las claves), busca esos productos en MongoDB y confirma cada oferta con `consultar_oferta.lua` (`ofertas_redis.pids_con_oferta_activa`). El frontend comparte una sola consulta entre el botón, la franja, las tarjetas del catálogo y la página (`composables/useOfertasFlash.js`; la barra, la franja y la página la piden con `limite=100`, así que las tarjetas de cualquier vista pública, también la de búsqueda, conocen todas las ofertas, [H-018](docs/hallazgos.md)) y la repite cada 20 s.
- **Pestaña "Ofertas flash" del vendedor** (`/admin/ofertas`, solo vendedor). Muestra sus ofertas activas con un resumen (ofertas activas, unidades vendidas y restantes), cuenta regresiva y botón para finalizar cada una, y un formulario para crear una nueva: se elige el producto, el precio de oferta (o un % de descuento), el cupo y la duración. Se actualiza cada 15 s. Lo respalda **`GET /api/vendedores/<id>/ofertas?rol_solicitante=...&id_usuario=...`**: un vendedor solo puede ver las suyas (`403` si pide las de otro); un administrador puede consultar las de cualquier vendedor. Crear y finalizar siguen usando `POST /api/ofertas` y `DELETE /api/ofertas/<producto_id>`, como desde la página del producto. `POST /api/ofertas` ahora devuelve también `descuento_pct`.
- **"Mis ventas" también para el administrador**. Antes solo la veía el vendedor. El administrador ve las ventas de los productos que él mismo publicó (los que tienen su usuario como vendedor). **Cambia el contrato**: `GET /api/vendedores/<id>/ventas` ahora exige `?rol_solicitante=vendedor|administrador&id_usuario=<id>`. Sin `rol_solicitante` válido responde `403`, sin `id_usuario` entero `400`, y un vendedor que pide las ventas de otro, `403`.
- **Los modales del panel admin se cierran con Escape** (`ModalAdmin.vue`).
- **Carrito sin expiración por defecto**. `CARRITO_TTL_SEGUNDOS` pasa a valer `0` si no se define: el carrito no expira, y cada lectura o escritura le quita el TTL que pudiera tener (`PERSIST`). Así, un carrito que quedó con TTL de la configuración anterior deja de vencer. Un valor mayor que 0 vuelve a activar la expiración por inactividad, igual que en la Entrega 2 (el TTL se renueva en cada operación). Las líneas de oferta del carrito siguen venciendo a los `RESERVA_OFERTA_TTL_SEGUNDOS` (60 s), pase lo que pase con el carrito.
  - **Decidido por el equipo (2026-10-07)**: el enunciado pide un "carrito de compra persistente por sesión, con expiración automática por inactividad" y "un tiempo de expiración configurado explícitamente" (criterio de 1.5 puntos de la Entrega 2). Se mantiene `0` por defecto: la expiración sigue configurándose explícitamente con la variable, las reservas de oferta siguen venciendo solas, y para demostrar la expiración se pone un valor mayor que 0 en el `.env` (por ejemplo `1800`). Justificación en [ADR-006](docs/decisiones/ADR-006-carrito-sin-expiracion-por-defecto.md), que reemplaza ese punto de ADR-003; antecedente en [H-016](docs/hallazgos.md).

## Novedades de la Entrega 3 (léelo si ya tenías el proyecto montado de antes)

Si ya tenías TiendaYa corriendo de la Entrega 2, esto es lo que necesitas hacer para ponerte al día:

1. **`git pull`** (trae Elasticsearch en `docker-compose.yml`, los módulos nuevos del backend y los scripts).
2. **Reinstala dependencias de Python**: `pip install -r requirements.txt` (agrega `elasticsearch`).
3. **Agrega las variables nuevas a tu `.env`**: `ELASTICSEARCH_URL` y, si quieres probar las fallas simuladas, `PERMITIR_FALLAS_SIMULADAS=1`. También hay tres opcionales que, si no las pones, toman su valor por defecto: `ES_ALIAS_PRODUCTOS` (`productos`), `OUTBOX_INTERVALO_SEGUNDOS` (`15`) y `OUTBOX_MAX_INTENTOS` (`10`) (ver el [paso 2](#2-variables-de-entorno)).
4. **Aplica la migración de la Entrega 3** sobre tu base existente (crea dos tablas nuevas, no toca datos):
   ```bash
   psql -U postgres -d tiendaya_db -f database/postgres/migracion_entrega3_consistencia.sql
   ```
   (o el atajo en Python del [paso 3](#3-crear-la-base-de-datos-y-cargar-el-esquema-postgresql) si no tienes `psql`, cambiando la ruta del archivo).
5. **Levanta Elasticsearch e indexa el catálogo** ([paso 5](#5-levantar-redis-neo4j-y-elasticsearch-y-sembrar-los-datos)):
   ```bash
   docker compose up -d
   python database/migrations/indexar_productos_elasticsearch.py
   ```
6. Reinicia el backend (`python backend/main.py`). Al arrancar tiene que decir `[relevo] Relevo de eventos de sincronización activo`.
7. **Comprueba que tu MongoDB tenga el índice `idx_activo_precio`** (de la Entrega 2). La migración no lo crea y su `drop()` lo borra, así que es fácil no tenerlo: en una de las bases locales del equipo faltaba. El comando del [paso 4](#4-migrar-el-catálogo-a-mongodb) es seguro de repetir.

Qué se construyó, en concreto:
- **Buscador con Elasticsearch**: al escribir en la barra de búsqueda aparece un **autocompletado** (con flechas ↑/↓ y Enter). Al presionar Enter se abre la página de resultados, ordenada por **relevancia**. Esa página tolera **errores de tipeo** ("laptp" encuentra laptops), entiende **sinónimos** ("portátil", "auriculares", "smartphone"), ofrece **"¿Quisiste decir…?"** y tiene **filtros facetados** por categoría, marca, tienda y rango de precio, calculados con agregaciones del motor (con el conteo de cada opción). Se puede ordenar por precio. Si Elasticsearch no está disponible, la búsqueda cae a la de MongoDB y muestra un aviso de "búsqueda simplificada". API: `GET /api/busqueda` y `GET /api/busqueda/autocompletar` (blueprint `busqueda.py`). El índice tiene un mapping propio ([`database/elasticsearch/productos_indice.json`](database/elasticsearch/productos_indice.json)) explicado en [ADR-004](docs/decisiones/ADR-004-motor-de-busqueda.md). Guardar un producto desde el admin lo reindexa solo.
- **Checkout con estrategia de consistencia**: [`docs/estrategia-consistencia-checkout.md`](docs/estrategia-consistencia-checkout.md) explica cada punto de falla y su mitigación. En resumen:
  - **Clave de idempotencia**: el frontend manda una por intento de compra. Si el cliente reintenta un pago que sí se había confirmado (por ejemplo, porque se perdió la respuesta), el backend devuelve el mismo pedido (`200`, `"repetido": true`) en vez de cobrar otra vez.
  - **Outbox**: en la misma transacción que el pedido se guardan los eventos de lo que hay que hacer después en los otros motores: limpiar el carrito y cerrar reservas en Redis, y copiar el stock a MongoDB y a Elasticsearch. Se ejecutan al instante; si un motor falla, un **relevo** (hilo en el backend, cada 15 s) los reintenta con espera creciente. Todos son idempotentes. Esto reemplaza las copias de "mejor esfuerzo" de antes, que, si fallaban, dejaban el stock de Mongo mal para siempre.
  - **Mensajes claros**: si algo falla antes de cobrar, el comprador ve "No se realizó ningún cobro y tu carrito sigue intacto" y un botón **Reintentar compra**. Si se perdió la conexión, ve que reintentar es seguro.
- **Fallas simuladas** (solo desarrollo, con `PERMITIR_FALLAS_SIMULADAS=1`): el checkout muestra un selector "Simular falla" para provocar que Redis, PostgreSQL, MongoDB o Elasticsearch fallen en distintos puntos del flujo. La prueba automática está en `backend/scripts/prueba_fallas_checkout.py` (45/45 verificaciones, [evidencia](docs/evidencia/prueba_fallas_checkout.txt)) y la del buscador en `backend/scripts/prueba_buscador.py` (21/21, [evidencia](docs/evidencia/prueba_buscador.txt)).
- **Panel admin → Sincronización** (solo administrador): eventos del outbox pendientes, procesados y fallidos, con su último error, más botones para procesarlos ya o volver a encolar los fallidos.
- **Correcciones tras las pruebas del 2026-10-06** (detalle en [`docs/hallazgos.md`](docs/hallazgos.md)). Cambian algunos contratos de la API:
  - **Historial paginado**: `GET /api/historial` ya no devuelve solo los 50 eventos más recientes. Acepta `pagina` y `por_pagina` (20 por defecto, máximo 100; `limit` sigue funcionando como alias de `por_pagina`) y devuelve `{eventos, total, pagina, por_pagina, total_paginas}`, del más reciente al más antiguo. La pestaña Historial del admin muestra el total de eventos y los botones "Anterior"/"Siguiente", y vuelve a cargar el selector de productos (antes fallaba con "data is not iterable"; H-001 y H-011).
  - **Catálogo con orden estable**: `GET /api/productos` desempata por `_id` (precio + `_id`, o relevancia + `_id` con `q`). Antes, recorrer todas las páginas repetía unos productos y saltaba otros (H-010).
  - **Errores del buscador**: `GET /api/busqueda` responde `400 BUSQUEDA_NO_VALIDA` si Elasticsearch rechaza la consulta, y `400` si `precio_min`/`precio_max` no son números finitos (`nan`, `inf`). El `503 BUSCADOR_NO_DISPONIBLE`, que es lo que hace caer al respaldo de MongoDB, queda solo para cuando el motor no está disponible (conexión, timeout, índice inexistente, `401`/`403`, `429` o `5xx`). Una página más allá de los primeros 10 000 resultados responde `200` con `items` vacíos y el `total` y las facetas reales (H-002 y H-003).
  - **Páginas fuera de rango**: `GET /api/historial` y `GET /api/productos` con un número de página enorme (por ejemplo `pagina=10000000000000000000`) responden `200` con la lista vacía y el `total` real; antes daban `500` (H-012). En la pestaña Historial, "Anterior"/"Siguiente" paginan con los últimos filtros aplicados con "Filtrar", no con lo que esté escrito en los campos (H-014).
  - **Checkout**: `id_comprador` puede llegar como número (`12`) o como string numérico (`"12"`); cualquier otro valor responde `400`. Antes, reintentar con `"12"` daba `409 CLAVE_IDEMPOTENCIA_AJENA` (H-004).
- **Documentación nueva**: [`docs/estrategia-consistencia-checkout.md`](docs/estrategia-consistencia-checkout.md), [ADR-004](docs/decisiones/ADR-004-motor-de-busqueda.md) (por qué Elasticsearch y cómo se diseñó el índice), [ADR-005](docs/decisiones/ADR-005-newsql-pagos.md) (evaluación NewSQL para pagos: no migrar, y cuándo sí), [`docs/arquitectura.md`](docs/arquitectura.md) (diagrama actualizado), [`docs/informe-entrega-3.md`](docs/informe-entrega-3.md), [`docs/guion-demostracion-entrega-3.md`](docs/guion-demostracion-entrega-3.md) (guion de la demostración en vivo) y [`docs/reporte-trabajo-entrega-3.md`](docs/reporte-trabajo-entrega-3.md) (reporte detallado de todo lo trabajado).

## Novedades de la Entrega 2

Si ya tenías TiendaYa corriendo de una entrega anterior, esto es lo que se agregó y lo que necesitas hacer para ponerte al día — no es opcional, el backend no arranca bien sin Redis/Neo4j configurados:

1. **Instala Docker + Docker Compose** si no lo tienes (requisito nuevo).
2. **`git pull`** para traer `docker-compose.yml`, los blueprints nuevos, y los scripts de semilla/migración nuevos.
3. **Reinstala dependencias de Python**: `pip install -r requirements.txt` (agrega `redis`, `neo4j`, `requests`).
4. **Agrega las variables de entorno nuevas a tu `.env`** (Redis y Neo4j — ver el paso 2 de instalación más abajo, o copia de nuevo `.env.example` y ajusta).
5. Sigue los pasos **5 en adelante** de la sección de Instalación (levantar Redis/Neo4j, aplicar constraints, sembrar compradores y reseñas de prueba) — son pasos nuevos que no existían antes.

Qué se construyó, en concreto:
- **Carrito de compra**: ya no vive en `localStorage`, vive en Redis (`carrito:{id_usuario}`, expira a los 30 min de inactividad; desde el 2026-10-07, por defecto no expira, ver "Novedades después de la Entrega 3"). Requiere sesión iniciada. El checkout toma los productos de ese carrito en Redis (no de lo que envía el navegador), así que un carrito expirado ya no se puede pagar. La referencia de pago la genera el backend automáticamente (formato `TY-AAAAMMDDHHMMSS-XXXXXX`). Al confirmar la compra se muestra un resumen con el número de pedido, la referencia y un botón "Dejar reseña" por cada producto comprado.
- **Oferta de inventario limitado** ("flash sale"): cupo independiente por producto en Redis, con una **duración** que se indica al crearla (la oferta vence sola al terminar esa ventana de tiempo), reservado con un script Lua atómico (sin sobreventa, verificado con 50 solicitudes concurrentes contra un límite de 10 → 10 éxitos, 0 sobreventa). Se crea y se cierra desde la página de detalle del producto (y, desde el 2026-10-07, también desde la pestaña "Ofertas flash" del panel del vendedor); solo puede hacerlo el vendedor dueño del producto o un administrador.
  - **Precio de oferta**: al crear la oferta se fija un `precio_oferta`, que debe ser menor que el precio normal. **No se puede editar**: para cambiarlo, hay que finalizar la oferta y crear otra. La página del producto muestra el precio de oferta, el normal tachado y el % de descuento.
  - **Reserva de 1 minuto en el carrito**: "Reservar y agregar al carrito" aparta las unidades y agrega al carrito una línea aparte, marcada "Oferta relámpago", con el precio de oferta, la cantidad fija y una cuenta regresiva. Si no se compra en ese tiempo (`RESERVA_OFERTA_TTL_SEGUNDOS`, 60 por defecto), la línea sale del carrito y las unidades vuelven a la oferta. Quitar la línea o vaciar el carrito también las libera de inmediato. Cada comprador puede tener una sola reserva activa por oferta.
  - **El cupo se descuenta al comprar, no al reservar**: el checkout confirma la reserva en Redis (Lua), cobra el precio de oferta y descuenta también el inventario real de PostgreSQL. Si la reserva ya venció, el checkout responde 409 (`RESERVA_OFERTA_EXPIRADA`) y quita la línea. Si PostgreSQL falla, las unidades vuelven a la oferta. Una línea normal y una de oferta del mismo producto pueden convivir en el carrito; el stock se valida sumando las dos.
  - Requiere aplicar `database/postgres/migracion_sp_checkout_precio_oferta.sql` en las bases que ya existían (ver el paso 3 de Instalación).
- **Reseñas de producto**: sistema nuevo desde cero — cualquier comprador puede calificar (1-5) y comentar un producto una sola vez, visible en `/producto/:id`. El formulario está al final de la página del producto; se llega directo con el enlace "★ Escribir reseña" bajo el precio, o con "Dejar reseña" desde el resumen de compra (URL `/producto/:id#escribir-resena`).
- **Detección de fraude en reseñas**: cada reseña se sincroniza a un grafo en Neo4j; el panel admin (`/admin/fraude`, solo administrador) corre una consulta de varios saltos que señala cuentas que se recalifican entre sí sobre los mismos productos. Para provocar una alerta a propósito, revisarla en el panel y limpiar los datos después, sigue [`docs/guia-prueba-fraude.md`](docs/guia-prueba-fraude.md).
  - Desde el 2026-10-07 hay además cuatro patrones nuevos; esta consulta sigue igual, en la pestaña "Anillos de reseñas". Ver [Novedades: detección de fraude ampliada](#novedades-detección-de-fraude-ampliada-2026-10-07).
- **Direcciones de envío en el checkout**: el checkout ya no pide escribir el ID de la dirección (antes había que adivinarlo y fallaba con "La dirección X no pertenece al comprador Y"). Ahora muestra un selector con las direcciones del comprador, con la principal ya elegida, y un mini formulario para agregar una si no tiene ninguna o quiere otra. Lo respalda un blueprint nuevo (`direcciones.py`: `GET`/`POST /api/usuarios/<id_usuario>/direcciones`); la primera dirección de un usuario queda como principal y marcar otra como principal desmarca la anterior.
- **Imágenes en el formulario de producto del admin**: al crear o editar un producto se pueden agregar hasta 10 links de imagen (http/https), con vista previa, elección de portada y orden (↑/↓). Detalle en [Imágenes de los productos](#imágenes-de-los-productos).
- **"Mi cuenta" del comprador**: un comprador con sesión iniciada ve el botón "Mi cuenta" en la barra de navegación, con tres pestañas:
  - **Mis pedidos**: total gastado (sin contar pedidos cancelados), número de pedidos y la lista de pedidos, del más reciente al más antiguo; cada uno se expande para ver sus líneas. Lo respalda un blueprint nuevo (`compradores.py`: `GET /api/compradores/<id_comprador>/pedidos`).
  - **Editar perfil**: nombre, teléfono y cambio de contraseña. Para cambiarla hay que escribir la actual, y la nueva debe tener al menos 8 caracteres (`PUT /api/usuarios/<id_usuario>/perfil`).
  - **Mis direcciones**: agregar, editar, marcar como principal y eliminar direcciones (`PUT`/`DELETE /api/usuarios/<id_usuario>/direcciones/<id_direccion>`). **Máximo 3 por usuario**: la cuarta responde `409`, también desde el checkout. Si eliminas la principal, la más antigua de las que quedan pasa a serlo. Una dirección que ya se usó en un pedido no se puede eliminar (`409`), porque el pedido la referencia.
- **Catálogo paginado**: con más de 1000 productos, el catálogo público y la pestaña Catálogo del admin muestran 24 productos por página, con botones "Anterior"/"Siguiente". **Cambió el formato de `GET /api/productos`**: acepta `pagina` y `por_pagina` (24 por defecto, máximo 100) y ya no devuelve una lista, sino `{items, total, pagina, por_pagina, total_paginas}`. Hay un índice nuevo en Mongo (`idx_activo_precio`) para la vista "Todas las categorías": créalo con el comando del [paso 4](#4-migrar-el-catálogo-a-mongodb).
- **Stock sincronizado entre PostgreSQL y MongoDB**: al confirmar una compra, el backend copia a Mongo el stock que quedó en Postgres, así la página del producto ya no muestra un stock viejo. Desde la Entrega 3 esta copia pasa por el outbox, con reintentos (y también llega a Elasticsearch). Al editar el stock de un producto desde el admin, el cambio también se escribe en el `inventario` de Postgres, que es el que usa el checkout (mejor esfuerzo: si falla, la edición en Mongo igual queda hecha y solo se registra una advertencia).
- **Documentación nueva**: [`docs/decisiones/ADR-002-grafos-vs-columnar.md`](docs/decisiones/ADR-002-grafos-vs-columnar.md) (por qué Neo4j y no Cassandra), [`docs/decisiones/ADR-003-redis-carrito-y-oferta.md`](docs/decisiones/ADR-003-redis-carrito-y-oferta.md) (por qué Redis para el carrito y la oferta), [`docs/arquitectura.md`](docs/arquitectura.md) (diagrama actualizado) y [`docs/informe-entrega-2.md`](docs/informe-entrega-2.md) (informe de la entrega).

## Estado del proyecto

**Fase Inicial** — completa: esquema relacional en 3FN, datos semilla, checkout como transacción atómica (`sp_procesar_checkout`, con bloqueo pesimista y rollback automático) expuesto en `POST /api/checkout`.

**Entrega 1** — completa: catálogo documental con atributos por categoría, migración Postgres→Mongo, índice compuesto, índice de texto para búsqueda, consultas de agregación, historial de cambios con reconstrucción point-in-time, panel admin (catálogo, categorías, usuarios, historial).

**Migración a frameworks** — completa: backend en Blueprints + SQLAlchemy, frontend migrado por completo a Vue 3 + Vite. El sitio HTML/JS vanilla original ya se retiró del repositorio. Detalle en [`docs/STACK.md`](docs/STACK.md).

**Entrega 2** — completa: carrito y oferta de inventario limitado sobre Redis, sistema de reseñas y detección de fraude sobre Neo4j. Bitácora completa de qué se hizo, por qué, y qué se verificó en [`docs/STACK.md`](docs/STACK.md).

**Entrega 3** — completa: buscador sobre Elasticsearch (tolerancia a errores, autocompletado, facetas), estrategia de consistencia del checkout (idempotencia, compensación y outbox con reintentos) con prueba de falla simulada, y evaluación NewSQL para pagos (ver "Novedades de la Entrega 3" arriba e informe en [`docs/informe-entrega-3.md`](docs/informe-entrega-3.md)).

**Después de la Entrega 3 (2026-10-07)** — ofertas flash visibles en el sitio público y pestaña de ofertas del vendedor, "Mis ventas" para el administrador y carrito sin expiración por defecto (decidido en [ADR-006](docs/decisiones/ADR-006-carrito-sin-expiracion-por-defecto.md)). Ver "Novedades después de la Entrega 3" arriba.

**Detección de fraude ampliada (2026-10-07)** — cuatro patrones nuevos sobre el grafo de Neo4j (`cuenta_rafaga`, `grupo_coordinado`, `sesgo_vendedor_sin_compra` y `cuentas_vinculadas`), con puntaje de riesgo, resumen por cuenta y panel con pestañas; la consulta de anillos de la Entrega 2 sigue igual. Prueba automática 59/59 y verificación final del agente de pruebas en [`docs/hallazgos.md`](docs/hallazgos.md) ("Verificación del fraude ampliado"). Ver "Novedades: detección de fraude ampliada" arriba y [`docs/deteccion-fraude-ampliada.md`](docs/deteccion-fraude-ampliada.md).

**Entrega final** — completa: recomendación de productos y búsqueda semántica con PostgreSQL + pgvector ([ADR-008](docs/decisiones/ADR-008-componente-vectorial.md)), control de acceso en Redis con un usuario por servicio ([ADR-009](docs/decisiones/ADR-009-control-acceso-redis.md)), [diagrama de arquitectura final](docs/arquitectura-final.html) y [retrospectiva](docs/retrospectiva.md). Evidencia: [`prueba_recomendacion.txt`](docs/evidencia/prueba_recomendacion.txt) (20/20) y [`prueba_control_acceso_redis.txt`](docs/evidencia/prueba_control_acceso_redis.txt) (37/37). Informe en [`docs/informe-entrega-final.md`](docs/informe-entrega-final.md).

**Informe de la Entrega 1:** [`docs/Entrega 1 Base de Datos 2 (1).pdf`](<docs/Entrega 1 Base de Datos 2 (1).pdf>) (diagrama entidad-relación, justificación de la normalización y decisiones de embeber/referenciar).

**Hallazgos de las pruebas:** los errores y pendientes que encontramos al probar (con su estado, cómo reproducirlos y la corrección propuesta) se registran en [`docs/hallazgos.md`](docs/hallazgos.md). Revísalo antes de reportar un error, por si ya está anotado.

**Pendiente (documentación, no código):** explicar cómo `lineas_pedido` (PostgreSQL) referencia productos que ahora viven en MongoDB (vía el campo `id_sql_origen`).

**Limitaciones conocidas:**
- El checkout opera sobre `productos`/`inventario` de PostgreSQL, no sobre MongoDB. Del catálogo, solo el **stock** se sincroniza entre los motores (tras una compra, por el outbox con reintentos; al editarlo en el admin, de mejor esfuerzo). El resto de lo que se edita desde el admin (**precio**, nombre, descripción, atributos) queda solo en Mongo y Elasticsearch: el checkout sigue cobrando el precio de Postgres.
- El stock que muestran el catálogo y el buscador puede tener unos segundos de atraso si MongoDB o Elasticsearch fallaron después de una compra (consistencia eventual; el relevo lo corrige solo). El checkout nunca vende de más por eso, porque valida contra PostgreSQL.
- El relevo del outbox es un hilo dentro del backend: si Flask está detenido, nadie reintenta (los eventos quedan guardados y se procesan al volver). Un evento que falla 10 veces queda `fallido` y se vuelve a encolar desde el panel admin → Sincronización.
- Control de acceso: Redis exige usuario por servicio (ACL) y pgvector usa roles; **Elasticsearch y MongoDB siguen sin autenticación** y Neo4j tiene un solo usuario (Community no tiene roles). En la API, el rol (`rol_solicitante`) lo manda el navegador y no se verifica con un token: es la principal deuda señalada en la [retrospectiva](docs/retrospectiva.md).
- La búsqueda semántica usa un modelo pequeño que corre en CPU: acierta la categoría en 6 de 8 frases de prueba; por ejemplo, "fragancia elegante para una cena" devuelve cuchillos ([H-027](docs/hallazgos.md)). Por eso complementa al buscador de Elasticsearch, no lo reemplaza.
- Un producto editado en el admin se recomienda con su texto nuevo apenas se guarda; si pgvector estaba caído, con el texto anterior hasta que el relevo procese el evento `embedding_producto`.
- La oferta de inventario limitado (cupo, precio y reservas) vive en Redis. Es un cupo aparte del inventario real, pero al confirmar la compra las unidades vendidas en oferta **sí** se descuentan del `inventario` de PostgreSQL, igual que una compra normal.
- El precio de oferta se valida al crearla contra el `precio_base` de MongoDB, y en el checkout contra el de PostgreSQL. Si un producto se editó solo en Mongo y los dos precios no coinciden, una oferta que se creó sin problema puede fallar al pagar. En ese caso el checkout devuelve las unidades a la oferta.
- Con el valor por defecto (`CARRITO_TTL_SEGUNDOS=0`) el carrito no expira, así que los carritos abandonados no se borran solos y ocupan memoria en Redis. Para que expiren por inactividad hay que poner un valor mayor que 0 en el `.env` ([ADR-006](docs/decisiones/ADR-006-carrito-sin-expiracion-por-defecto.md)). Las reservas de oferta del carrito sí vencen siempre.
- La sincronización de una reseña hacia Neo4j es de mejor esfuerzo (sin 2PC): si Neo4j no está disponible al crear la reseña, esta igual queda guardada en Mongo y solo se registra una advertencia en el log del backend.
- Desde la detección de fraude ampliada (2026-10-07), las direcciones de envío también se copian a Neo4j en mejor esfuerzo. Si dos cambios de direcciones del mismo usuario se confirman casi a la vez, el grafo puede quedar con la versión anterior hasta la próxima edición de direcciones o hasta correr `database/migrations/sincronizar_grafo_fraude.py` ([H-020](docs/hallazgos.md)). Mientras tanto, `cuentas_vinculadas` puede ver una dirección vieja.
- El historial de cambios del producto no registra el stock: cada evento guarda nombre, descripción, precio, estado activo/inactivo y atributos. La reconstrucción por fecha indica si el producto estaba disponible para la venta (activo), pero no cuántas unidades había en existencia en ese momento.

## Requisitos previos

- Python 3.10+
- PostgreSQL corriendo localmente (o accesible por red)
- MongoDB corriendo localmente (o accesible por red)
- Node.js `^20.19.0` o `>=22.12.0` + npm (requerido por Vite para levantar el frontend)
- **Docker + Docker Compose** (para levantar Redis, Neo4j, Elasticsearch y PostgreSQL + pgvector). Elasticsearch usa unos 1-1.5 GB de RAM (heap de 512 MB más la propia JVM)
- Unos **1.5 GB libres en disco** para PyTorch (~550 MB en el venv) y el modelo de embeddings (~460 MB, se descarga solo la primera vez a la caché de Hugging Face)

## Arranque diario (después de apagar o reiniciar la computadora)

Esto es para cuando el proyecto **ya está instalado** (si es la primera vez, sigue la [Instalación](#instalación)). Los datos no se pierden al apagar: PostgreSQL y MongoDB los guardan en disco, y Redis, Neo4j y Elasticsearch, en volúmenes de Docker. Solo hay que volver a encender los servicios, en este orden:

1. **Abre Docker Desktop** y espera a que diga *Engine running* (abajo a la izquierda). PostgreSQL y MongoDB, si los instalaste como servicios de Windows, arrancan solos con la computadora.
2. **Levanta Redis, Neo4j, Elasticsearch y pgvector.** Abre una terminal en la carpeta del proyecto:
   ```bash
   docker compose up -d
   ```
   Espera de 30 a 40 segundos. Elasticsearch está listo cuando http://localhost:9200 muestra un JSON, o cuando `docker compose ps` lo marca `healthy`.
3. **Levanta el backend**, en esa misma terminal (déjala abierta):
   ```bash
   venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
   python backend/main.py
   ```
   Tiene que mostrar `Running on http://127.0.0.1:8000` y `[relevo] Relevo de eventos de sincronización activo`.
4. **Levanta el frontend** en una **segunda terminal** (déjala abierta también):
   ```bash
   cd frontend/app
   npm run dev
   ```
   Abre la dirección que muestra (normalmente http://localhost:5173). Si falla con `EACCES`, usa `npm run dev -- --port 5300` (ver el [paso 7](#7-levantar-el-frontend)).
5. **(Opcional) Visores de las bases:** `docker compose --profile visores up -d` levanta RedisInsight y Kibana (ver [Ver las bases de datos](#ver-las-bases-de-datos)).

**Para apagar todo:** `Ctrl+C` en las terminales del backend y del frontend, y luego `docker compose --profile visores stop` (o `docker compose stop` si no levantaste los visores). Nunca uses `docker compose down -v`: la `-v` **borra los volúmenes** y con ellos los datos de Redis, Neo4j y Elasticsearch.

**Si algo no responde:**
- PostgreSQL o MongoDB no conectan: en Windows, abre *Servicios* (`services.msc`) y verifica que `postgresql-x64-18` y `MongoDB` estén *En ejecución*.
- El buscador muestra "búsqueda simplificada": Elasticsearch todavía está arrancando o no tiene el índice. Espera un poco y, si sigue igual, corre `python database/migrations/indexar_productos_elasticsearch.py`.
- El carrito, las ofertas o el panel de fraude dan error (en la consola del backend aparece un error de Redis o Neo4j): los contenedores no están corriendo. Revisa con `docker compose ps` y corre `docker compose up -d`. No hace falta reiniciar el backend: se reconecta solo.
- En la consola del backend aparece `NOAUTH Authentication required` o `WRONGPASS`: tu `.env` tiene el `REDIS_URL` viejo, sin usuario. Cópialo de `.env.example` (ver [Novedades de la entrega final](#novedades-de-la-entrega-final-léelo-si-ya-tenías-el-proyecto-montado)) y reinicia el backend.
- No aparecen los "Productos relacionados": el contenedor `vectores` no está corriendo (`docker compose up -d`) o faltan los embeddings (`python database/migrations/generar_embeddings_productos.py`). El panel admin → Sincronización dice cuántos productos tienen embedding.

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

`requirements.txt` incluye `sentence-transformers` (recomendación semántica, entrega final), que instala PyTorch: la descarga es de unos 550 MB. En **Linux**, instala primero la versión CPU de PyTorch (la de PyPI trae CUDA y pesa varios GB): `pip install torch --index-url https://download.pytorch.org/whl/cpu`, y después `pip install -r requirements.txt`. En Windows y macOS no hace falta.

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
# Solo la leen dos scripts de database/migrations/; el backend usa siempre "tiendaya_nosql" (backend/app/extensions.py)
MONGO_DB_NAME=tiendaya_nosql

# Redis exige usuario: cada servicio usa el suyo (database/redis/users.acl)
REDIS_URL=redis://tiendaya_api:api_tiendaya_2026@localhost:6379/0
REDIS_URL_RELEVO=redis://tiendaya_relevo:relevo_tiendaya_2026@localhost:6379/0
REDIS_URL_ADMIN=redis://tiendaya_admin:admin_tiendaya_2026@localhost:6379/0
# Segundos de inactividad tras los que expira un carrito (se renueva en cada operación).
# 0 = el carrito no expira (valor por defecto); por ejemplo 1800 = 30 minutos
CARRITO_TTL_SEGUNDOS=0
# Segundos que una reserva de oferta relámpago queda apartada en el carrito (opcional, 60 por defecto)
RESERVA_OFERTA_TTL_SEGUNDOS=60

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=tiendaya123

ELASTICSEARCH_URL=http://localhost:9200
ES_ALIAS_PRODUCTOS=productos

# Componente vectorial (contenedor "vectores", puerto 5433) y modelo de embeddings
VECTORES_URL=postgresql+psycopg2://vectores_app:vectores_app_2026@localhost:5433/tiendaya_vectores
MODELO_EMBEDDINGS=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# Cada cuántos segundos se reintentan los eventos pendientes del checkout, y cuántos intentos antes de marcarlos "fallido"
OUTBOX_INTERVALO_SEGUNDOS=15
OUTBOX_MAX_INTENTOS=10
# 1 = el checkout acepta fallas simuladas (solo desarrollo y para la prueba de falla); 0 en cualquier otro caso
PERMITIR_FALLAS_SIMULADAS=0
```

`.env` está en `.gitignore` — nunca lo subas al repositorio.

Sobre `CARRITO_TTL_SEGUNDOS`: con `0` (o un valor negativo) el carrito no expira, y cada operación le quita el TTL que tuviera (`PERSIST`). Con un valor mayor que 0, el carrito expira tras ese tiempo **sin actividad**, porque el TTL se renueva en cada lectura o escritura. Las reservas de oferta del carrito vencen aparte, con `RESERVA_OFERTA_TTL_SEGUNDOS`. El enunciado pide expiración por inactividad: si vas a demostrar ese requerimiento, usa un valor mayor que 0 (por qué el valor por defecto es `0`: [ADR-006](docs/decisiones/ADR-006-carrito-sin-expiracion-por-defecto.md)).

Ojo con `MONGO_DB_NAME`: el backend no la lee, se conecta siempre a la base `tiendaya_nosql` (fijo en `backend/app/extensions.py`). Solo la usan `database/migrations/migracion_postgres_a_mongo.py`, `database/migrations/sembrar_resenas_fraude.py` y el comando del índice del paso 4 (el indexador de Elasticsearch usa la conexión del backend). Si la cambias, esos scripts escribirían en una base que el backend no ve, así que déjala en `tiendaya_nosql`.

### 3. Crear la base de datos y cargar el esquema (PostgreSQL)

Crea la base de datos vacía:

```bash
psql -U postgres -c "CREATE DATABASE tiendaya_db;"
```

Si no tienes `psql`, el mismo paso en Python (se conecta a la base `postgres`, que siempre existe, con `autocommit` porque `CREATE DATABASE` no puede correr dentro de una transacción; usa las credenciales de tu `.env`):

```bash
python -c "import psycopg2, os; from dotenv import load_dotenv; load_dotenv(); c=psycopg2.connect(host=os.getenv('PG_HOST'), port=os.getenv('PG_PORT'), dbname='postgres', user=os.getenv('PG_USER'), password=os.getenv('PG_PASSWORD')); c.autocommit=True; c.cursor().execute('CREATE DATABASE ' + os.getenv('PG_DBNAME')); print('Base creada')"
```

Carga el esquema, el procedimiento de checkout y los primeros 4 productos:

```bash
psql -U postgres -d tiendaya_db -f database/postgres/ddl_tiendaya.sql
```

**Si tu base `tiendaya_db` ya existía de antes**, no vuelvas a correr el DDL (borra todo); corre en su lugar la migración que actualiza `sp_procesar_checkout` para aceptar el precio de oferta relámpago por línea y validar el stock sumando las líneas del mismo producto (solo reemplaza el procedimiento, no toca datos):

```bash
psql -U postgres -d tiendaya_db -f database/postgres/migracion_sp_checkout_precio_oferta.sql
```

Y la de la Entrega 3, que crea las tablas `checkout_idempotencia` y `eventos_sincronizacion` (el DDL ya las trae para una base nueva; esta migración es para bases existentes, no toca datos y se puede repetir):

```bash
psql -U postgres -d tiendaya_db -f database/postgres/migracion_entrega3_consistencia.sql
```

Y la de la entrega final, que agrega el tipo de evento `embedding_producto` al outbox. **Córrela también en una base nueva** (el DDL no la trae); no toca datos y se puede repetir:

```bash
psql -U postgres -d tiendaya_db -f database/postgres/migracion_entrega_final_vectores.sql
```

Carga los 11 productos adicionales de la semilla (15 en total):

```bash
psql -U postgres -d tiendaya_db -f database/postgres/datos_semilla_productos.sql
```

Carga la **semilla masiva**: 40 tiendas nuevas (usuarios `vendedor`), 3 categorías padre y 19 subcategorías nuevas (cada una con su `esquema_atributos`), y 1000 productos con inventario inicial repartidos entre esas tiendas y las 2 tiendas semilla, cada tienda según su giro (una tienda de tecnología no vende playeras):

```bash
psql -U postgres -d tiendaya_db -f database/postgres/datos_semilla_masivos.sql
```

Puedes correrlo aunque tu base ya tenga datos propios, y más de una vez: busca categorías, tiendas y productos por nombre/email/SKU (nunca por ID fijo), no duplica nada y no gasta IDs de las secuencias al repetirse. Tampoco modifica las categorías, usuarios ni productos que ya existían.

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

La migración **no** crea el índice `idx_activo_precio`, que usa la paginación de la vista "Todas las categorías". Créalo aparte, **y vuelve a crearlo cada vez que corras la migración completa**, porque su `drop()` lo borra. Es seguro repetirlo:

```bash
python -c "from pymongo import MongoClient; import os; from dotenv import load_dotenv; load_dotenv(); c=MongoClient(os.getenv('MONGO_URI'))[os.getenv('MONGO_DB_NAME')]; print(c.productos.create_index([('activo', 1), ('precio_base', 1)], name='idx_activo_precio'))"
```

Sin este índice el catálogo funciona igual, pero Mongo tiene que recorrer y ordenar toda la colección en cada página.

**Modo incremental (recomendado para cargar la semilla masiva en una base en uso):**

```bash
python database/migrations/migracion_postgres_a_mongo.py --incremental
```

No borra nada: solo inserta en Mongo los productos de Postgres que todavía no tienen documento (por `id_sql_origen` o `sku`), cada uno con su evento `CREACION_PRODUCTO` en el historial. Los documentos que ya existían, sus ediciones desde el admin y sus eventos no se tocan. Puedes correrlo varias veces sin duplicar nada. La migración completa (sin `--incremental`) también incluye los 1000 productos, pero borra todo lo demás, igual que antes.

#### Semilla masiva: atributos, atributos personalizados e imágenes

Los atributos y las fotos de los 1000 productos no se guardan en Postgres (Postgres no tiene columna de atributos). Vienen de `database/migrations/datos_semilla_masivos_catalogo.json`, organizado por SKU, y la migración lo lee igual que lee `ATRIBUTOS_POR_SKU` / `IMAGENES_POR_SKU`:

- **Atributos:** cada producto trae exactamente las claves del `esquema_atributos` de su subcategoría, con el tipo correcto (`numero` → número, `texto` → texto) y valores variados, para que `/api/categorias/<id>/filtros` genere filtros útiles.
- **Atributos personalizados:** el 20% de los productos (200) lleva además 1 o 2 claves de texto que no están en el esquema de su categoría. Es el mismo mecanismo que usa el formulario de producto del admin (por ejemplo `edicion_limitada: "Si"`, `grabado_personalizado: "Grabado en la caja (Q80)"`, `bordado_personalizado`, `cambio_de_talla`, `incluye_lapiz`...). El formulario de edición los muestra en "Atributos personalizados".
- **Imágenes:** cada producto tiene de 1 a 3 fotos de Unsplash (295 con 1, 413 con 2 y 292 con 3). La primera es la portada (`es_portada: true`, `orden` de 1 a n). Las fotos se toman de un conjunto por subcategoría: 142 fotos en total, todas revisadas (responden HTTP 200 y muestran el tipo de producto correcto). En electrodomésticos, utensilios y audífonos la portada coincide con el tipo concreto (por ejemplo, una licuadora lleva foto de licuadora). La marca que aparece en la foto no siempre coincide con la del producto.

El `.sql` y el `.json` los genera `database/migrations/generar_semilla_masiva.py`. El script es determinístico (usa una semilla fija), así que siempre produce los mismos archivos. **Si necesitas cambiar la semilla, edita el generador y vuelve a correrlo; no edites a mano el `.sql` ni el `.json`:**

```bash
python database/migrations/generar_semilla_masiva.py
```

#### Imágenes de los productos

Las imágenes no son archivos del repositorio: cada producto guarda en Mongo una lista de enlaces a fotos (`imagenes: [{id_imagen, url, es_portada, orden}]`, con una sola portada). Cuántas tiene depende de su origen: 2 (portada y detalle) en los 15 productos originales, de 1 a 3 en la semilla masiva y hasta 10 en los productos cargados desde el panel admin. **La fuente compartida por todo el equipo es el mapa `IMAGENES_POR_SKU` de `database/migrations/migracion_postgres_a_mongo.py`** (más `datos_semilla_masivos_catalogo.json` para la semilla masiva): al correr la migración, todos obtienen las mismas imágenes.

- **Para cambiar o agregar la imagen de un producto de la semilla**, edita `IMAGENES_POR_SKU` (`"SKU": ("photo-<id portada>", "photo-<id detalle>")`, con el id que aparece en la URL de Unsplash), vuelve a correr la migración y haz commit del script. Un cambio hecho solo en tu Mongo local no les llega a los demás. (Para la semilla masiva, edita el generador, ver arriba).
- **Un producto nuevo de la semilla** necesita su entrada en el mapa; si no la tiene, recibe una foto genérica de su categoría (`IMAGEN_GENERICA_POR_CATEGORIA`).
- **Desde el panel admin**, el formulario de producto (crear o editar) tiene la sección "Imágenes del producto": hasta 10 links `http://` o `https://`, cada uno con miniatura de vista previa, un radio para marcar la portada y botones ↑/↓ para reordenar. `POST /api/productos` valida y normaliza la lista antes de escribir en Postgres o Mongo: acepta strings u objetos `{url, es_portada}`, quita las URL duplicadas, deja una sola portada (la marcada o, si no hay, la primera) y responde 400 si alguna URL es inválida o hay más de 10. Al editar, si el payload no trae `imagenes` se conservan las que había y si trae `[]` se vacían; el formulario siempre envía la lista completa. Un producto sin imágenes muestra el ícono de su categoría.
- **Las imágenes cargadas desde el panel viven solo en Mongo** (no están en `IMAGENES_POR_SKU` ni en Postgres), así que no les llegan a los demás por `git pull`.
- Ojo: la migración completa (sin `--incremental`) **borra y recrea** `productos` e `historial_cambios_productos`, así que se pierden las ediciones hechas desde el admin (incluidas las imágenes cargadas desde el panel: el producto se vuelve a crear desde Postgres con la foto genérica de su categoría o sin imagen) y el historial local. El modo `--incremental` no toca los documentos que ya existen, así que las conserva.

### 5. Levantar Redis, Neo4j y Elasticsearch, y sembrar los datos

Desde la raíz del repo:

```bash
docker compose up -d
```

Levanta cuatro servicios:

- **Redis** (puerto `6379`): carrito y oferta de inventario limitado. Arranca con los usuarios de `database/redis/users.acl`: sin usuario y contraseña no acepta ningún comando (ver [Credenciales de los componentes](#credenciales-de-los-componentes)).
- **vectores** (puerto `5433`): PostgreSQL 17 + pgvector para los embeddings de productos. La primera vez ejecuta `database/vectores/01_esquema.sql` (extensión, tabla `producto_embedding`, índice HNSW y roles). Es independiente de tu PostgreSQL local del puerto 5432.
- **Neo4j** (puertos `7474` browser / `7687` bolt, usuario `neo4j` / contraseña `tiendaya123`): detección de fraude en reseñas.
- **Elasticsearch** (puerto `9200`): buscador del catálogo.

Dale unos 20-40 segundos a Neo4j y a Elasticsearch antes de seguir, tardan más que Redis en quedar listos. Puedes verificarlo con `docker compose ps` (Elasticsearch aparece `healthy`) o con `curl http://localhost:9200`. Para abrir cada base con una interfaz gráfica (incluidos RedisInsight y Kibana, que están en el perfil opcional `visores`), mira [Ver las bases de datos](#ver-las-bases-de-datos).

Indexa el catálogo de MongoDB en Elasticsearch (necesita el paso 4 hecho). Crea un índice nuevo, verifica que tenga la misma cantidad de productos que Mongo y recién entonces mueve el alias `productos` hacia él, así que es seguro correrlo las veces que haga falta, incluso con el backend andando:

```bash
python database/migrations/indexar_productos_elasticsearch.py
```

**Vuelve a correrlo** si cambias `database/elasticsearch/productos_indice.json` (mapping, sinónimos), si corres la migración completa de Mongo (sin `--incremental`) o si borras el volumen de Elasticsearch. Los productos que crees o edites desde el admin se indexan solos.

Genera los embeddings del catálogo en pgvector (necesita el paso 4 hecho y el contenedor `vectores` arriba). La primera vez descarga el modelo de lenguaje (~460 MB); después, recalcula solo los productos cuyo texto cambió, así que es seguro repetirlo:

```bash
python database/migrations/generar_embeddings_productos.py
```

Termina con `pgvector: N embeddings`, donde N es la cantidad de productos de MongoDB (1019 con todas las semillas). **Vuelve a correrlo** si corres la migración completa de Mongo o si borras el volumen `vectores_data`; con `--forzar` recalcula todo (por ejemplo, si cambias `MODELO_EMBEDDINGS`). Los productos que crees o edites desde el admin se actualizan solos.

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

Para la detección de fraude ampliada (desde el 2026-10-07), completa el grafo y siembra sus escenarios, en este orden y después de `sembrar_resenas_fraude.py` (los dos se pueden repetir; las constraints de `database/neo4j/02_fraude_ampliado.cypher` las crea el primero si faltan, y también se pueden aplicar como en las [novedades](#novedades-detección-de-fraude-ampliada-2026-10-07)):

```bash
python database/migrations/sincronizar_grafo_fraude.py
python database/migrations/sembrar_fraude_ampliado.py
```

### 6. Levantar el backend

```bash
python backend/main.py
```

Flask queda escuchando en `http://127.0.0.1:8000`. Internamente, `backend/main.py` llama a `create_app()` y arranca el **relevo del outbox**: un hilo que cada 15 s reintenta los eventos de sincronización pendientes del checkout. En la consola debe aparecer una sola vez `[relevo] Relevo de eventos de sincronización activo`. Las rutas viven organizadas por dominio en `backend/app/blueprints/` (ver la estructura más abajo o `docs/STACK.md` para el detalle completo).

#### Probar la recomendación y el control de acceso (entrega final)

Con el backend levantado:

```bash
python backend/scripts/prueba_recomendacion.py                # R1-R6: cobertura, relacionados, búsqueda semántica, índice, sincronización, permisos
python backend/scripts/prueba_recomendacion.py --caida-real   # + R7: detiene y vuelve a levantar el contenedor vectores
python backend/scripts/prueba_control_acceso_redis.py         # no necesita el backend: solo Redis
```

La primera verifica, entre otras cosas, que las recomendaciones son de la misma categoría o de una afín, que una frase sin palabras en común con el catálogo encuentra la categoría correcta (y qué devuelve Elasticsearch para la misma frase), y que los roles de pgvector no pueden hacer más de lo debido. La segunda se conecta a Redis como cada usuario y comprueba que puede lo suyo y recibe `NOPERM` en todo lo demás, incluso dentro de scripts Lua. Salidas guardadas en [`docs/evidencia/`](docs/evidencia/).

#### Probar las fallas del checkout

Hay dos formas: un **script automático**, que corre todos los escenarios y revisa cada base, y una **prueba a mano desde el navegador**, que sirve para la demostración. Las dos crean pedidos reales en tu base local.

**Antes de empezar (las dos formas):**
1. En el `.env` de la raíz debe estar la línea `PERMITIR_FALLAS_SIMULADAS=1`. Si la agregaste ahora, reinicia el backend (Ctrl+C y `python backend/main.py`).
2. Deben estar arriba los contenedores (`docker compose up -d`), PostgreSQL y MongoDB, y el backend.

**Forma 1: script automático.** En **otra** terminal (el backend debe seguir corriendo en la primera), desde la raíz del proyecto:

```bash
venv\Scripts\activate
python backend/scripts/prueba_fallas_checkout.py               # camino feliz + 4 fallas simuladas (E0-E4), ~1 min
python backend/scripts/prueba_fallas_checkout.py --caida-real  # + caída real de Elasticsearch (E5): la detiene y la vuelve a levantar, ~2-3 min
python backend/scripts/prueba_buscador.py --caida-real         # evidencia del buscador
```

Cada verificación imprime `[OK  ]` o `[FALLA]`. Al final debe decir `RESUMEN: 45/45 verificaciones correctas` y `RESULTADO: PASS` (con `--caida-real`; sin esa opción son menos verificaciones). Compra como `maria.torres@email.com` y usa productos con stock de 30 o más. Si algo sale `[FALLA]`, revisa primero que el backend esté corriendo y que el flag esté en el `.env`.

**Forma 2: a mano desde el navegador.**
1. Abre `http://localhost:5173`, inicia sesión como `maria.torres@email.com` (contraseña `Tiendaya123!`) y agrega uno o dos productos al carrito.
2. Ve a pagar. Debajo del formulario aparece el cuadro **Simular falla (solo desarrollo)**. Si no aparece, el flag no está activo o no reiniciaste el backend.
3. Elige una falla, confirma el pago y compara con lo esperado:

| Opción del selector | Qué deberías ver |
|---|---|
| Redis no responde al leer el carrito | Error "No se realizó ningún cobro". No hay pedido nuevo y el carrito sigue igual. |
| PostgreSQL se cae antes del COMMIT | Error "No pudimos confirmar tu pago. No se realizó ningún cobro". No hay pedido, el stock no cambia y, si había una oferta relámpago, la reserva se libera. Vuelve a pagar con **Sin falla** y la compra sí pasa. |
| Redis no responde después de confirmar | La compra **sí** se confirma. El carrito puede seguir mostrando lo comprado unos segundos, hasta que el relevo lo limpia. Si intentas pagar otra vez, no se cobra doble. |
| MongoDB no responde al copiar el stock | La compra se confirma. En Compass, el stock del producto en MongoDB queda viejo y en unos 15-30 s el relevo lo corrige solo. |
| Elasticsearch no responde al copiar el stock | La compra se confirma. El stock en Elasticsearch (Kibana) se corrige solo en unos 15-30 s. |

4. Para ver la cola de reintentos, entra como `admin@tiendaya.com` a `http://localhost:5173/admin/sincronizacion`: ahí aparecen los eventos pendientes, con su error, y cómo pasan a *procesado*.

Para simular una caída **real** sin el script: `docker compose stop elasticsearch`, haz una compra (funciona igual, pero el buscador muestra que no está disponible), luego `docker compose start elasticsearch` y en menos de un minuto el stock queda al día.

Qué se prueba y qué resultado se espera: [`docs/estrategia-consistencia-checkout.md`](docs/estrategia-consistencia-checkout.md) (sección 7).

### 7. Levantar el frontend

```bash
cd frontend/app
npm install
npm run dev
```

Vite queda escuchando en `http://localhost:5173` (o el siguiente puerto libre si ese ya está en uso) y habla con el backend en `http://127.0.0.1:8000`. Rutas: `/` sitio público (catálogo paginado con la franja de ofertas flash encima de la grilla y la etiqueta de descuento en las tarjetas con oferta, buscador con autocompletado y facetas, página de ofertas flash, carrito, checkout, login/registro y "Mi cuenta" del comprador; las vistas sin URL propia se abren desde otra página con `/?vista=ofertas`, `/?vista=carrito`, etc.), `/producto/:id` detalle de producto (reseñas y, si el producto tiene una oferta activa, el precio de oferta con cuenta regresiva y el bloque de reserva), `/admin/:tab?` panel admin (catálogo, categorías, usuarios, "Mis ventas", ofertas flash, historial, fraude y sincronización; "Ofertas flash" solo para vendedor, y categorías, usuarios, fraude y sincronización solo para administrador).

Para un build de producción: `npm run build` (genera `frontend/app/dist/`).

**Si el repositorio está dentro de OneDrive** (o en otra carpeta sincronizada): `vite.config.js` usa `server.watch.usePolling`, porque OneDrive no siempre avisa de los cambios en los archivos y Vite podía seguir sirviendo versiones viejas de algunos módulos (por ejemplo, un carrito que no se vaciaba al comprar). Si igual ves un comportamiento que no coincide con el código, detén Vite, vuelve a correr `npm run dev` y recarga el navegador con **Ctrl+F5**.

**Si Vite no arranca en Windows con `listen EACCES: permission denied`** (en `::1:5173` o `127.0.0.1:5173`): al arrancar Docker Desktop, Hyper-V/WSL reserva rangos de puertos, y a veces uno de ellos incluye el 5173. Vite solo pasa al siguiente puerto cuando el 5173 está *ocupado*, no cuando está *reservado*, así que falla en vez de cambiar de puerto. Para ver los rangos reservados (cambian en cada reinicio):

```bash
netsh interface ipv4 show excludedportrange protocol=tcp
```

Si el 5173 cae dentro de uno, levanta Vite en un puerto que quede fuera de todos los rangos, por ejemplo:

```bash
npm run dev -- --port 5300
```

El backend tiene CORS abierto a cualquier origen (`CORS(app)` en `backend/app/__init__.py`), así que el frontend funciona igual desde otro puerto. En macOS/Linux esto no pasa.

## Ver las bases de datos

TiendaYa usa seis bases. Con esta tabla puedes abrir cada una con una interfaz gráfica para ver qué guardó la aplicación:

| Base | Qué guarda | Herramienta | Dónde |
|---|---|---|---|
| **PostgreSQL** | Usuarios, direcciones, pedidos, pagos, inventario, outbox del checkout | **pgAdmin 4** (viene con el instalador de PostgreSQL) | App de escritorio |
| **MongoDB** | Catálogo, historial de cambios, reseñas | **MongoDB Compass** (viene con el instalador de MongoDB, o se [descarga](https://www.mongodb.com/try/download/compass)) | App de escritorio |
| **Redis** | Carritos y ofertas flash | **RedisInsight** (contenedor) | http://localhost:5540 |
| **Neo4j** | Grafo de reseñas para fraude | **Neo4j Browser** (incluido en Neo4j) | http://localhost:7474 |
| **Elasticsearch** | Índice del buscador | **Kibana** (contenedor) | http://localhost:5601 |
| **pgvector** | Embeddings de los productos | **pgAdmin 4** (el mismo del PostgreSQL local) | `localhost:5433` |

RedisInsight y Kibana están en el `docker-compose.yml` dentro del perfil **`visores`**, así que **no** arrancan con `docker compose up -d`. Levántalos cuando los necesites (con Redis y Elasticsearch ya corriendo):

```bash
docker compose --profile visores up -d     # levanta RedisInsight y Kibana
docker compose --profile visores stop      # los detiene (y también el resto de los servicios)
```

Kibana tarda 1-2 minutos en estar listo la primera vez y usa cerca de 1 GB de RAM. Si solo te interesa una de las dos, levántala por nombre: `docker compose --profile visores up -d redisinsight`.

### PostgreSQL → pgAdmin 4

1. Abre pgAdmin 4. En **Servers** debería aparecer ya tu PostgreSQL local; si no, clic derecho → **Register → Server**. En la pestaña *Connection* pon host `localhost`, puerto `5432`, usuario `postgres` y la misma contraseña que tienes en `PG_PASSWORD` del `.env`.
2. Navega a **Databases → tiendaya_db → Schemas → public → Tables**. Clic derecho sobre una tabla → **View/Edit Data → All Rows**.
3. Para consultas: selecciona `tiendaya_db` y abre **Tools → Query Tool**. Por ejemplo:

```sql
-- Últimos pedidos con su pago
SELECT p.id_pedido, u.email, p.estado, p.total, pg.referencia_transaccion, p.fecha_pedido
FROM pedidos p JOIN usuarios u ON u.id_usuario = p.id_comprador
LEFT JOIN pagos pg ON pg.id_pedido = p.id_pedido
ORDER BY p.id_pedido DESC LIMIT 20;

-- Outbox del checkout (Entrega 3): qué quedó pendiente o falló
SELECT id_evento, tipo, estado, intentos, ultimo_error, id_pedido
FROM eventos_sincronizacion ORDER BY id_evento DESC LIMIT 20;
```

Sin pgAdmin, también puedes usar `psql -U postgres -d tiendaya_db` en la terminal.

### MongoDB → MongoDB Compass

1. Abre Compass y conéctate con la URI `mongodb://localhost:27017` (la misma de `MONGO_URI`).
2. Entra a la base **`tiendaya_nosql`**. Tiene tres colecciones: `productos` (el catálogo), `historial_cambios_productos` (un evento por cada cambio de producto) y `resenas`.
3. En la barra **Filter** de una colección puedes buscar documentos, por ejemplo:
   - `{ "categoria.nombre": "Laptops" }` en `productos`
   - `{ "producto_id": "PROD-0001" }` en `historial_cambios_productos` (ordena con `{ "fecha_evento": -1 }` en *Sort*)
   - En la pestaña **Indexes** ves los índices (`idx_categoria_activo_precio`, `idx_texto_busqueda`…), y en **Aggregations** puedes armar pipelines.

### Redis → RedisInsight (http://localhost:5540)

1. La primera vez, acepta los términos de uso. La conexión **"TiendaYa (Redis, solo lectura)"** se crea sola al aceptarlos, porque viene configurada en el `docker-compose.yml` con el usuario `tiendaya_lectura`: puedes ver todo, pero no modificar ni borrar nada (es parte del control de acceso). Si no aparece, haz clic en **+ Add Redis database** y usa host **`redis`**, puerto `6379`, usuario `tiendaya_lectura` y contraseña `lectura_tiendaya_2026`. No pongas `localhost`: RedisInsight corre en otro contenedor, y para él `localhost` es él mismo. Si necesitas modificar algo a mano, crea otra conexión con `tiendaya_admin` / `admin_tiendaya_2026`.
   - Si ya habías abierto RedisInsight antes de la entrega final, su conexión vieja (sin usuario) dará error de autenticación: bórrala y crea la nueva como se indica arriba.
2. En **Browser** escribe un patrón en el buscador:
   - `carrito:*`: un hash por comprador (`carrito:<id_usuario>`). Cada campo es una línea del carrito.
   - `oferta:*`: las ofertas flash. `oferta:<producto>:stock` es el cupo sin vender; también están `:limite`, `:precio`, `:id` y el hash `:reservas`. La columna **TTL** muestra cuánto le queda a la oferta.
3. Sin RedisInsight: `docker compose exec redis redis-cli --user tiendaya_lectura --pass lectura_tiendaya_2026` (o `tiendaya_admin` / `admin_tiendaya_2026` para escribir), y luego `SCAN 0 MATCH oferta:* COUNT 100`, `HGETALL carrito:4` o `TTL oferta:PROD-0001:stock`. Sin `--user`, Redis responde `NOAUTH`. `ACL LIST` (como admin) muestra los usuarios y sus permisos.

### pgvector → pgAdmin 4 (localhost:5433)

1. En pgAdmin, clic derecho en **Servers → Register → Server**. Nombre: `TiendaYa vectores`. En *Connection*: host `localhost`, puerto **`5433`**, base `tiendaya_vectores`, usuario `vectores_lector` y contraseña `vectores_lector_2026` (solo lectura; `vectores_admin` / `vectores_admin_2026` es el dueño del esquema).
2. Tabla **`producto_embedding`**: un vector de 384 números por producto, con su categoría, si está activo, el hash del texto y el modelo con que se calculó.
3. Consultas de ejemplo en el **Query Tool**:

```sql
-- Los 5 productos más parecidos a PROD-0001 (1 = idéntico)
SELECT producto_id, round((1 - (embedding <=> (SELECT embedding FROM producto_embedding WHERE producto_id = 'PROD-0001')))::numeric, 3) AS similitud
FROM producto_embedding WHERE producto_id <> 'PROD-0001'
ORDER BY embedding <=> (SELECT embedding FROM producto_embedding WHERE producto_id = 'PROD-0001')
LIMIT 5;

-- Cuántos embeddings hay por categoría
SELECT id_categoria, count(*) FROM producto_embedding GROUP BY 1 ORDER BY 2 DESC;
```

Los nombres de los productos no están aquí (están en MongoDB): busca el `producto_id` en Compass. Sin pgAdmin: `docker compose exec vectores psql -U vectores_admin -d tiendaya_vectores`.

### Neo4j → Neo4j Browser (http://localhost:7474)

1. Conéctate con *Connect URL* `neo4j://localhost:7687`, usuario `neo4j` y contraseña `tiendaya123`.
2. Escribe una consulta en la barra superior y presiona **Ctrl+Enter**:

```cypher
// Quién calificó qué (vista de grafo)
MATCH (c:Cuenta)-[r:CALIFICO]->(p:Producto) RETURN c, r, p LIMIT 100

// Cuántos nodos y relaciones de cada tipo hay
MATCH (n) RETURN labels(n)[0] AS etiqueta, count(*) AS total
```

Con el grafo de fraude ampliado (`sincronizar_grafo_fraude.py`, ver el [paso 5](#5-levantar-redis-neo4j-y-elasticsearch-y-sembrar-los-datos)) también hay nodos `Vendedor` y `Direccion`. Por ejemplo, `MATCH (c:Cuenta)-[:ENVIA_A]->(d:Direccion)<-[:ENVIA_A]-(otra:Cuenta) RETURN c, d, otra` muestra cuentas que comparten dirección. Haz clic en un nodo para ver sus propiedades, o cambia a la vista **Table**.

### Elasticsearch → Kibana (http://localhost:5601)

1. Abre el menú (☰) → **Management → Dev Tools**. Ahí escribes consultas a la izquierda y las ejecutas con ▶ (o **Ctrl+Enter**):

```
GET _cat/indices/productos*?v
GET _alias/productos
GET productos/_mapping
GET productos/_search
{
  "query": { "match": { "nombre": { "query": "laptp", "fuzziness": "AUTO" } } },
  "_source": ["nombre", "precio_base", "stock_disponible"]
}
```

2. Para navegar los documentos con una tabla, ve a **Analytics → Discover** y crea un *data view* con el patrón `productos`.
3. Kibana crea sus propios índices internos (los que empiezan con punto, como `.kibana_8.15.3_001`). No afectan al índice `productos` del buscador.

Sin Kibana, Elasticsearch también se puede consultar desde el navegador, por ejemplo http://localhost:9200/productos/_search?q=laptop&pretty.

**Si `localhost:5540` o `localhost:5601` no abren en Windows**: puede pasar lo mismo que con el puerto de Vite (un rango reservado por Hyper-V/WSL). Revísalo con el comando `netsh` de la sección anterior y, si hace falta, cambia el puerto de la izquierda en el `docker-compose.yml` (por ejemplo, `"5541:5540"`).

## Credenciales de prueba

Todos los usuarios semilla usan la misma contraseña: **`Tiendaya123!`**

| Email | Rol | Notas |
|---|---|---|
| admin@tiendaya.com | administrador | Acceso completo a `/admin` (catálogo, categorías, usuarios, "Mis ventas" de los productos que publicó, historial, fraude, sincronización); no tiene la pestaña "Ofertas flash", pero puede crear o cerrar ofertas desde la página de cualquier producto |
| ventas@techstore.com | vendedor | Acceso a `/admin` acotado a su propio catálogo, "Mis ventas", "Ofertas flash" e historial (sin Categorías/Usuarios/Fraude/Sincronización) |
| contacto@modaurbana.com | vendedor | Igual que el anterior |
| carlos.mendez@email.com | comprador | Dirección de envío registrada; "Mi cuenta" con pedidos, perfil y direcciones |
| sofia.lopez@email.com | comprador | Dirección de envío registrada |
| `<nombre>.<apellido>@fraude-demo.tiendaya.gt` (por ejemplo `kevin.barrios@fraude-demo.tiendaya.gt`) | comprador | 24 cuentas de los escenarios de la detección de fraude ampliada, creadas por `database/migrations/sembrar_fraude_ampliado.py`. Solo tienen las reseñas y direcciones de la semilla, sin pedidos. La lista de cuentas por escenario está en el script (`CUENTAS_POR_ESCENARIO`) |

El registro público (`/`) solo crea cuentas de `comprador`. Para crear cuentas de `vendedor` o `administrador` nuevas, usa la pestaña "Usuarios" del panel admin.

Tras correr `database/postgres/datos_semilla_usuarios.sql` (paso 5) hay **10 compradores adicionales**, cada uno con su propia dirección de envío (misma contraseña `Tiendaya123!`), por ejemplo `maria.torres@email.com` — necesarios para checkout de prueba y para que la detección de fraude tenga variedad de cuentas.

Tras correr `database/postgres/datos_semilla_masivos.sql` (paso 3) hay **40 tiendas adicionales** con rol `vendedor` (misma contraseña `Tiendaya123!`). Cada una entra a `/admin` y ve solo su catálogo. De los 1000 productos nuevos, TechStore Oficial recibe 79 y Moda Urbana GT 47; el resto se reparte así:

| Tienda | Email | Giro (subcategorías) | Productos |
|---|---|---|---|
| Compu Centro Zona 4 | ventas@compucentrozona4.com.gt | Laptops, Monitores, Teclados, Mouse | 28 |
| Megatech Guatemala | tienda@megatechgt.com | Laptops, Monitores, Tablets | 26 |
| Cel Express Guatemala | ventas@celexpress.com.gt | Celulares, Smartwatches, Audífonos | 31 |
| Gamer Zone Xela | contacto@gamerzonexela.com | Monitores, Teclados, Mouse, Audífonos, Laptops | 32 |
| iMundo Oakland | hola@imundooakland.com.gt | Laptops, Tablets, Smartwatches, Celulares, Audífonos | 49 |
| Digital Plaza Miraflores | ventas@digitalplazagt.com | Celulares, Tablets, Audífonos | 32 |
| SonidoPro GT | info@sonidoprogt.com | Audífonos | 8 |
| Periféricos Chapines | pedidos@perifericoschapines.com | Teclados, Mouse | 9 |
| Tecno Antigua | ventas@tecnoantigua.com.gt | Celulares, Smartwatches, Tablets | 30 |
| Byte Store Mixco | contacto@bytestoremixco.com | Laptops, Monitores, Mouse, Teclados | 19 |
| Smart Life Guatemala | ventas@smartlifegt.com | Smartwatches, Audífonos, Celulares | 29 |
| Kompuservicios Quetzal | ventas@kompuquetzal.com.gt | Laptops, Monitores | 8 |
| Denim Chapín | ventas@denimchapin.com | Jeans, Playeras | 26 |
| Sneaker Hub Guatemala | hola@sneakerhubgt.com | Tenis, Gorras | 25 |
| Boutique Doña Lupita | boutique@donalupita.com.gt | Vestidos | 13 |
| Urban Xela Streetwear | contacto@urbanxela.com | Sudaderas, Playeras, Gorras | 27 |
| Estilo Antigüeño | ventas@estiloantigueno.com | Vestidos, Playeras | 19 |
| Pasos Firmes Calzado | ventas@pasosfirmes.com.gt | Tenis | 28 |
| La Gorra Chapina | pedidos@lagorrachapina.com | Gorras | 9 |
| Moda Maya Contemporánea | tienda@modamayacontemporanea.com | Vestidos, Playeras | 23 |
| Street Kings GT | ventas@streetkingsgt.com | Sudaderas, Tenis, Gorras, Playeras | 34 |
| Jeans & Co. Pradera | ventas@jeansypradera.com.gt | Jeans | 14 |
| Casual Market Cayalá | hola@casualmarketcayala.com | Playeras, Jeans, Sudaderas | 30 |
| Cocina Feliz GT | ventas@cocinafelizgt.com | Electrodomésticos de Cocina, Utensilios de Cocina | 19 |
| Hogar Práctico Quetzaltenango | contacto@hogarpracticoxela.com | Electrodomésticos de Cocina, Utensilios de Cocina | 33 |
| Casa Barista Guatemala | tienda@casabaristagt.com | Electrodomésticos de Cocina | 12 |
| El Rincón del Chef | ventas@rincondelchef.com.gt | Utensilios de Cocina | 18 |
| Electrohogar Petapa | ventas@electrohogarpetapa.com | Electrodomésticos de Cocina | 13 |
| Ciclo Guate | ventas@cicloguate.com | Bicicletas, Mochilas | 27 |
| Pedal Libre Antigua | hola@pedallibreantigua.com | Bicicletas | 10 |
| Fitness Store GT | ventas@fitnessstoregt.com | Pesas y Mancuernas, Tapetes de Yoga | 36 |
| Yoga Atitlán | namaste@yogaatitlan.com | Tapetes de Yoga | 11 |
| Aventura Outdoor Guatemala | ventas@aventuraoutdoorgt.com | Mochilas, Bicicletas | 22 |
| Power Gym Supply | pedidos@powergymsupply.com.gt | Pesas y Mancuernas | 18 |
| Mochilas Volcán | ventas@mochilasvolcan.com | Mochilas | 16 |
| Aromas de Guatemala | ventas@aromasdeguatemala.com | Perfumes | 8 |
| Dermacuidado GT | contacto@dermacuidadogt.com | Cuidado de la Piel | 8 |
| Belleza Natural Cobán | ventas@bellezanaturalcoban.com | Cuidado de la Piel, Perfumes | 34 |
| Perfumería Esencia Zona 14 | ventas@perfumeriaesencia.com.gt | Perfumes | 11 |
| Glow Beauty Store | hola@glowbeautygt.com | Cuidado de la Piel, Perfumes | 29 |

## Credenciales de los componentes

Son contraseñas **de desarrollo**, iguales para todo el equipo (están en `.env.example` y en `docker-compose.yml`). En un despliegue real irían en un gestor de secretos.

**Redis** (control de acceso por ACL, archivo `database/redis/users.acl`, contraseñas guardadas como SHA-256; detalle en [ADR-009](docs/decisiones/ADR-009-control-acceso-redis.md)):

| Usuario | Contraseña | Lo usa | Puede |
|---|---|---|---|
| `default` | — | nadie | **deshabilitado**: sin credenciales, Redis responde `NOAUTH` |
| `tiendaya_api` | `api_tiendaya_2026` | la API (`REDIS_URL`) | keys `carrito:*` y `oferta:*`; solo los comandos que usa el código y scripts Lua. Sin `KEYS`, `FLUSHALL`, `CONFIG`, `ACL` |
| `tiendaya_relevo` | `relevo_tiendaya_2026` | el relevo del outbox (`REDIS_URL_RELEVO`) | `HGET`/`HDEL` y scripts sobre `carrito:*` y `oferta:*:reservas`; nada más |
| `tiendaya_lectura` | `lectura_tiendaya_2026` | RedisInsight | leer todas las keys; no escribe ni ejecuta scripts |
| `tiendaya_admin` | `admin_tiendaya_2026` | operación y pruebas (`REDIS_URL_ADMIN`) | todo |

Para cambiar una contraseña: calcula su SHA-256 (`python -c "import hashlib; print(hashlib.sha256(b'nueva').hexdigest())"`), reemplaza el `#<hash>` del usuario en `users.acl`, actualiza el `.env` de cada integrante y corre `docker compose restart redis`.

**pgvector** (roles de PostgreSQL creados por `database/vectores/01_esquema.sql`):

| Rol | Contraseña | Puede |
|---|---|---|
| `vectores_admin` | `vectores_admin_2026` | dueño de la base `tiendaya_vectores` (cambiar el esquema) |
| `vectores_app` | `vectores_app_2026` | lo usan el backend y el script de embeddings: leer y escribir filas de `producto_embedding`; no puede crear ni borrar tablas |
| `vectores_lector` | `vectores_lector_2026` | solo leer |

**Neo4j:** `neo4j` / `tiendaya123`. **Elasticsearch y MongoDB:** sin autenticación (ver "Limitaciones conocidas").

## Estructura del repositorio

```
backend/
  main.py                    Entry point: create_app() + relevo del outbox (hilo) + app.run(..., threaded=True)
  app/
    __init__.py                 create_app(): Flask + CORS + registro de blueprints
    config.py                    load_dotenv(), PG_CONFIG, MONGO_URI, REDIS_URL, REDIS_URL_RELEVO, VECTORES_URI, MODELO_EMBEDDINGS, NEO4J_URI, ELASTICSEARCH_URL, OUTBOX_*, PERMITIR_FALLAS_SIMULADAS
    extensions.py                 db (SQLAlchemy), Mongo (col_productos, col_historial, col_resenas), redis_client (usuario tiendaya_api), redis_relevo (usuario tiendaya_relevo), neo4j_driver, es_client
    models.py                      Modelos SQLAlchemy: Usuario, Direccion, Categoria, Producto, Inventario, Pedido, LineaPedido, CheckoutIdempotencia, EventoSincronizacion
    busqueda_es.py                Elasticsearch: documento del índice, indexar, búsqueda con facetas, autocompletado (Entrega 3)
    sincronizacion.py             Outbox del checkout: registrar y procesar eventos idempotentes + hilo de relevo (Entrega 3)
    ofertas_redis.py              Keys, carga de scripts Lua y wrappers de la oferta (compartido por ofertas, carrito y checkout); pids_con_oferta_activa (SCAN de oferta:*:id)
    vectores.py                   pgvector: texto del producto, embeddings (modelo con carga perezosa), upsert por hash, vecinos por coseno y diversificación (entrega final)
    grafo_fraude.py               Sincronización en mejor esfuerzo del grafo de fraude ampliado: compra_verificada, clave normalizada de dirección, ENVIA_A (2026-10-07)
    lua/
      crear_oferta.lua               Crea cupo, límite, precio e id de la oferta en un solo paso (mismo TTL)
      consultar_oferta.lua            Estado de la oferta: disponible, reservado, vendido y la reserva del usuario
      reservar_oferta.lua             Aparta unidades por RESERVA_OFERTA_TTL_SEGUNDOS sin sobreventa (no descuenta el cupo)
      estado_linea_oferta.lua          Valida la reserva de una línea de oferta del carrito
      liberar_reserva_oferta.lua        Libera una reserva (quitar la línea o vaciar el carrito)
      consumir_reserva_oferta.lua       Checkout: pasa la reserva a "en pago" y descuenta el cupo
      compensar_reserva_oferta.lua      Checkout fallido: devuelve las unidades y restaura la reserva
      confirmar_reserva_oferta.lua      Checkout confirmado: cierra la reserva como vendida
      limpiar_carrito_comprado.lua      Outbox: quita del carrito solo las líneas pagadas que no cambiaron (Entrega 3)
    blueprints/
      auth.py                       /api/auth/register, /api/auth/login, /api/usuarios, /api/usuarios/<id>, /api/usuarios/<id>/perfil (PUT)
      direcciones.py                 /api/usuarios/<id_usuario>/direcciones (GET, POST; máx. 3) y .../<id_direccion> (PUT, DELETE)
      compradores.py                  /api/compradores/<id_comprador>/pedidos (historial de pedidos + total gastado)
      checkout.py                    /api/checkout (idempotencia + reservas de oferta + outbox), /api/checkout/fallas-simuladas
      catalogo.py                     /api/categorias, /api/categorias/<id>/filtros, /api/productos (paginado, orden estable), /api/productos/<id> (indexa en Elasticsearch al guardar)
      busqueda.py                     /api/busqueda, /api/busqueda/autocompletar (Elasticsearch, Entrega 3)
      sincronizacion.py               /api/sincronizacion/eventos, /procesar, /reintentar-fallidos (panel admin del outbox, Entrega 3)
      historial.py                     /api/historial (feed paginado con filtros), /api/historial/<producto_id> (reconstrucción por fecha)
      vendedores.py                     /api/vendedores/<id>/ventas (exige rol_solicitante e id_usuario; un vendedor solo ve las suyas)
      carrito.py                        /api/carrito/<id_usuario> (Redis, Entrega 2; por defecto no expira, CARRITO_TTL_SEGUNDOS > 0 activa la expiración)
      ofertas.py                        /api/ofertas (POST crear; GET listado público de ofertas activas), /api/ofertas/<producto_id> (GET, DELETE), /api/ofertas/<producto_id>/reservar, /api/vendedores/<id>/ofertas (ofertas del vendedor) (precio de oferta + reserva de 1 min; Redis + Lua, Entrega 2)
      resenas.py                        /api/resenas (Mongo + sync a Neo4j, Entrega 2)
      recomendaciones.py                /api/productos/<id>/relacionados, /api/busqueda/semantica, /api/vectores/estado (pgvector, entrega final)
      fraude.py                         /api/fraude/alertas (consulta Cypher de 3 saltos, Entrega 2)
                                        + /api/fraude/patrones, /api/fraude/alertas/<tipo>, /api/fraude/resumen (4 patrones, fraude ampliado, 2026-10-07)
  scripts/
    prueba_concurrencia_oferta.py  Evidencia de que la oferta límite no permite sobreventa bajo concurrencia
    prueba_fallas_checkout.py      Evidencia de la estrategia de consistencia: camino feliz + 4 fallas simuladas (E0-E4) + caída real de Elasticsearch (E5) (Entrega 3)
    prueba_buscador.py             Evidencia del buscador: errores de tipeo, sinónimos, autocompletado, facetas, respaldo (Entrega 3)
    prueba_recomendacion.py        Evidencia de la recomendación y la búsqueda semántica: cobertura, calidad, índice, sincronización, roles y caída real (entrega final)
    prueba_control_acceso_redis.py Evidencia del control de acceso en Redis: cada usuario ACL contra lo permitido y lo prohibido (37 verificaciones, entrega final)
    prueba_fraude_ampliado.py      Evidencia de la detección de fraude ampliada: positivos, controles, API original intacta, errores y sincronización (59 verificaciones, 2026-10-07)
database/
  postgres/
    ddl_tiendaya.sql               Esquema 3FN + semilla + sp_procesar_checkout
    datos_semilla_productos.sql    11 productos adicionales (15 en total)
    datos_semilla_usuarios.sql     10 compradores + direcciones adicionales (Entrega 2, IDs dinámicos vía ON CONFLICT)
    datos_semilla_masivos.sql      Semilla masiva: 19 subcategorías + 40 tiendas + 1000 productos e inventario (generado, idempotente)
    migracion_sp_checkout_precio_oferta.sql  Actualiza sp_procesar_checkout en bases existentes (precio de oferta por línea)
    migracion_entrega3_consistencia.sql      Tablas checkout_idempotencia y eventos_sincronizacion (outbox) en bases existentes
    migracion_entrega_final_vectores.sql     Agrega el evento embedding_producto al outbox (entrega final; correr también en bases nuevas)
  redis/
    users.acl                      Usuarios ACL de Redis por servicio (contraseñas como SHA-256; entrega final)
  vectores/
    01_esquema.sql                 pgvector: extensión, tabla producto_embedding, índice HNSW y roles (lo ejecuta el contenedor al crearse; entrega final)
  mongo/
    01_indexes.js                  Índices de referencia (la migración crea todos menos idx_activo_precio, ver paso 4)
    02_aggregation_queries.js      Consultas de agregación de referencia
  neo4j/
    01_constraints.cypher          Constraints de unicidad para nodos Cuenta/Producto (Entrega 2)
    02_fraude_ampliado.cypher      Constraints de Vendedor/Direccion y modelo del grafo de fraude ampliado (aditivo, 2026-10-07)
  elasticsearch/
    productos_indice.json          Settings y mapping del índice de productos: analizadores, sinónimos, autocompletado (Entrega 3)
  migrations/
    migracion_postgres_a_mongo.py  ETL: aplana productos de Postgres a documentos Mongo + fotos reales por SKU (--incremental: sin borrar)
    generar_semilla_masiva.py       Genera datos_semilla_masivos.sql + datos_semilla_masivos_catalogo.json (determinístico)
    datos_semilla_masivos_catalogo.json  Atributos (incl. personalizados) y 1-3 fotos Unsplash por SKU de la semilla masiva
    sembrar_resenas_fraude.py       Siembra reseñas con un patrón de fraude detectable (Entrega 2, idempotente)
    sincronizar_grafo_fraude.py     Completa el grafo existente: Vendedor/VENDIDO_POR, CALIFICO.compra_verificada, Direccion/ENVIA_A (no destructivo, idempotente, 2026-10-07)
    sembrar_fraude_ampliado.py      Escenarios positivos y de control de los 4 patrones nuevos + 24 compradores @fraude-demo.tiendaya.gt (aditivo, idempotente, 2026-10-07)
    indexar_productos_elasticsearch.py  Indexa el catálogo de Mongo en un índice versionado y mueve el alias (Entrega 3)
    generar_embeddings_productos.py     Calcula y guarda en pgvector los embeddings de todo el catálogo (idempotente, --forzar; entrega final)
frontend/
  app/                        Sitio Vue 3 + Vite (único frontend, ver docs/STACK.md)
    src/
      views/                       VistaPublica.vue, VistaDetalleProducto.vue, VistaAdmin.vue
      components/publico/           Catálogo, filtros, tarjeta de producto, carrito, checkout, login/registro, reseñas, oferta límite, PerfilComprador ("Mi cuenta"), ResultadosBusqueda (facetas), ProductosSemanticos (productos relacionados y búsqueda por significado, entrega final), ofertas flash (OfertasFlash.vue, FranjaOfertasFlash.vue, TarjetaOfertaPublica.vue)
      components/comunes/            Paginacion.vue (compartido por el catálogo público, el del admin, los resultados de búsqueda y el historial)
      components/admin/              Catálogo, categorías, usuarios, ventas, ofertas flash del vendedor (GestionOfertas.vue, FormularioOferta.vue, TarjetaOferta.vue), historial, fraude (GestionFraude.vue), sincronización (GestionSincronizacion.vue), ModalAdmin.vue (se cierra con Escape)
                                     + fraude ampliado (2026-10-07): ResumenFraude.vue, AnillosResenas.vue (consulta de la Entrega 2), AlertasPatron.vue, AlertaFraude.vue
      composables/                    useSesion, useToast, useCategorias, useCarrito (Redis-backed, Entrega 2), useOfertasFlash (una sola consulta a GET /api/ofertas para la barra, la franja, las tarjetas del catálogo y la página; exporta ofertaDisponible y ofertaActivaDe)
      services/api.js                 apiFetch (wrapper de fetch contra el backend)
      utils/                          categoriaVisual.js, tiempo.js (formatoMinSeg, formatoCuentaRegresiva), descuento.js (% de descuento: usa el descuento_pct del servidor si viene; si no, lo calcula con el mismo redondeo half-up, en centavos enteros; entre 0 y 99 mientras se cobre algo)
                                      + fraude.js (2026-10-07): niveles, etiquetas de patrones, umbrales y evidencia, mensajes de error del panel de fraude
docs/
  STACK.md                   Bitácora técnica completa: qué cambió en cada fase, por qué, y qué se verificó
  arquitectura.md            Diagrama de arquitectura final (Mermaid) y notas de consistencia
  arquitectura-final.html    Diagrama de arquitectura final para abrir en el navegador: vista general, checkout, recomendación, matriz y control de acceso
  arquitectura-entrega-3.html  Diagrama de la Entrega 3 (histórico)
  retrospectiva.md           Qué decisiones de arquitectura se sostendrían y cuáles se replantearían (entrega final)
  informe-entrega-final.md   Informe de la entrega final
  guion-presentacion-final.md  Guion de la presentación final: bloques, demostración en vivo, plan B y preguntas probables
  estrategia-consistencia-checkout.md  Estrategia de consistencia del checkout: puntos de falla, mitigación y prueba de falla (Entrega 3)
  decisiones/
    ADR-002-grafos-vs-columnar.md   Registro de decisión: Neo4j para fraude en reseñas, columnar descartado por ahora
    ADR-003-redis-carrito-y-oferta.md  Registro de decisión: Redis para el carrito y la oferta de inventario limitado
    ADR-004-motor-de-busqueda.md       Registro de decisión: Elasticsearch para el buscador y diseño del mapping
    ADR-005-newsql-pagos.md            Evaluación NewSQL para pagos: no migrar, y cuándo sí
    ADR-006-carrito-sin-expiracion-por-defecto.md  Registro de decisión: carrito sin expiración por defecto (2026-10-07)
    ADR-007-deteccion-fraude-ampliada.md  Registro de decisión: detección de fraude ampliada sobre el mismo grafo de Neo4j (2026-10-07)
    ADR-008-componente-vectorial.md  Registro de decisión: PostgreSQL + pgvector en contenedor dedicado para la recomendación semántica (entrega final)
    ADR-009-control-acceso-redis.md  Registro de decisión: control de acceso en Redis con un usuario ACL por servicio (entrega final)
  informe-entrega-2.md       Informe de la Entrega 2 (decisiones, evidencia y responsabilidades)
  informe-entrega-3.md       Informe de la Entrega 3 (buscador, consistencia, prueba de falla, NewSQL)
  evidencia/                 Salidas de las pruebas de la Entrega 3 (fallas del checkout y buscador)
                             + prueba_fraude_ampliado.txt (detección de fraude ampliada, 2026-10-07)
                             + prueba_recomendacion.txt y prueba_control_acceso_redis.txt (entrega final)
  guia-prueba-fraude.md      Paso a paso para provocar y revisar una alerta de fraude, y limpiar los datos de prueba
  deteccion-fraude-ampliada.md  Detección de fraude ampliada: los 4 patrones, umbrales, puntajes, grafo y verificación (2026-10-07)
  guia-funcionalidades.docx  Guía en Word por funcionalidad: qué hace, de qué base saca los datos y en qué archivos está (actualizada al 2026-10-08)
  informe-entrega-3.docx     Versión en Word del informe de la Entrega 3 (mismo contenido que informe-entrega-3.md)
  reporte-trabajo-entrega-3.md  Reporte detallado de todo lo trabajado en la Entrega 3
  guion-demostracion-entrega-3.md  Guion de la demostración en vivo: bloques por presentador, resultados esperados, plan B y preguntas probables
  hallazgos.md               Registro de hallazgos de las pruebas: errores y pendientes, con su estado y corrección
docker-compose.yml          Redis con ACL + Neo4j (Entrega 2) + Elasticsearch (Entrega 3) + vectores: PostgreSQL + pgvector (entrega final); perfil "visores": RedisInsight (solo lectura) + Kibana
requirements.txt
.env.example
```
