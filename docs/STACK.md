# Stack de TiendaYa — qué se usa y por qué

Este documento se mantiene actualizado a medida que avanza la migración a frameworks
oficiales. Registra qué tecnología se usa en cada capa, por qué se eligió, y el estado
de la migración (qué ya cambió y qué sigue pendiente).

## Objetivo de la migración

El proyecto arrancó como Flask puro (un solo archivo) + JS vanilla, sin ORM ni build
step. Se decidió migrar de forma **incremental**, empezando por el backend, hacia
frameworks oficiales que faciliten organizar el proyecto a medida que crece.

## Backend

| Capa | Antes | Ahora / plan | Por qué |
|---|---|---|---|
| Framework web | Flask, un solo archivo `main.py` | ✅ Flask, reorganizado en **Blueprints** por dominio (`backend/app/blueprints/`: auth, catálogo, checkout, direcciones, historial, vendedores, más carrito, ofertas, reseñas y fraude de la Entrega 2) con application factory (`create_app()`) | Flask ya era la elección correcta (liviano, sin ceremonia); el problema no era el framework sino que todo el código vivía en un único archivo. Los Blueprints son el mecanismo *oficial* de Flask para modularizar rutas sin cambiar de framework. |
| Acceso a PostgreSQL | SQL crudo con `psycopg2` en cada endpoint | ✅ **SQLAlchemy** (`flask-sqlalchemy`), modelos en `backend/app/models.py` (`Usuario`, `Direccion`, `Categoria`, `Producto`, `Inventario`, `Pedido`, `LineaPedido`) | Evita repetir apertura/cierre manual de conexión y manejo de errores en cada endpoint; da modelos declarativos reutilizables y sesiones manejadas automáticamente. El stored procedure `sp_procesar_checkout` se sigue invocando igual (`CALL` vía `db.session.execute(text(...))`), ya que la lógica transaccional compleja vive intencionalmente en la base de datos y no se reescribe en Python. `get_pg_connection()`/`psycopg2` crudo ya no existen en el código — quedaron completamente reemplazados. |
| Acceso a MongoDB | `pymongo` directo | Se mantiene `pymongo` | `pymongo` **es** el driver oficial de MongoDB para Python; no hay una razón para introducir un ODM adicional (como MongoEngine) en un proyecto que ya usa agregaciones nativas y necesita flexibilidad de esquema. |
| Autenticación | Verificación de credenciales sin tokens; el frontend manda `rol_solicitante` en cada request | Pendiente de definir (candidato: `flask-jwt-extended`) | Se documentará cuando se aborde esta fase. |

**Estado actual:** Blueprints ✅ y SQLAlchemy ✅ — ambos completados y verificados contra Postgres/Mongo reales. El backend ya no tiene SQL crudo con `psycopg2` en ningún endpoint.

Estructura resultante:
```
backend/
  main.py                  # entry point: from app import create_app; app.run(...)
  app/
    __init__.py              # create_app(): Flask + CORS + registro de blueprints
    config.py                 # load_dotenv(), PG_CONFIG, MONGO_URI, REDIS_URL, CARRITO_TTL_SEGUNDOS, NEO4J_*
    extensions.py              # db (SQLAlchemy), Mongo (col_productos, col_historial, col_resenas), redis_client, neo4j_driver
    models.py                   # Usuario, Direccion, Categoria, Producto, Inventario, Pedido, LineaPedido
    lua/reservar_oferta.lua      # check-and-decrement atómico de la oferta (Entrega 2)
    blueprints/
      auth.py                  # /api/auth/register, /api/auth/login, /api/usuarios, /api/usuarios/<id>
      checkout.py               # /api/checkout (toma los productos del carrito en Redis)
      direcciones.py            # /api/usuarios/<id_usuario>/direcciones (GET lista, POST alta; selector del checkout)
      catalogo.py                # /api/categorias, /api/categorias/<id>/filtros, /api/productos, /api/productos/<id>
      historial.py                # /api/historial (feed con filtros), /api/historial/<producto_id> (reconstrucción por fecha)
      vendedores.py                # /api/vendedores/<id>/ventas
      carrito.py                   # /api/carrito/<id_usuario> (Redis, Entrega 2)
      ofertas.py                   # /api/ofertas, /api/ofertas/<producto_id>/reservar (Redis + Lua, Entrega 2)
      resenas.py                   # /api/resenas (Mongo + sincronización a Neo4j, Entrega 2)
      fraude.py                    # /api/fraude/alertas (Cypher de varios saltos, Entrega 2)
```

## Frontend

| Capa | Antes | Plan | Por qué |
|---|---|---|---|
| UI | HTML + JS vanilla, sin build step | ✅ **Vue 3** (`^3.5`) con **Vite** (`^8.2`) y **Vue Router** (`^4.6`), único frontend en `frontend/app/` | Curva de aprendizaje suave viniendo de HTML/JS vanilla (sintaxis de plantillas cercana al HTML actual); Vite da un entorno de build oficial, rápido y con configuración mínima. |
| Estilos | Tailwind CSS vía CDN | ✅ **Tailwind CSS v4** vía `@tailwindcss/vite` (enfoque CSS-first con `@theme`, sin `tailwind.config.js`) | El CDN de Tailwind no es apto para producción (según la propia documentación de Tailwind); instalarlo como paquete permite purgar CSS no usado y tener autocompletado/tooling. |

**Estado actual:** scaffold ✅, utilidades compartidas ✅, sitio público ✅, panel admin ✅, QA end-to-end adversarial ✅ y **corte a producción ✅ (2026-09-07)** completados. La migración a Vue en sí no introdujo regresiones (confirmado por QA: auth, filtros combinados, carrito, sesión, control de acceso admin/vendedor/comprador, checkout de casos de borde — todo correcto). El sitio vanilla original (`frontend/index.html`, `frontend/admin.html`, `frontend/js/`) se eliminó del repositorio a pedido del usuario, una vez confirmado que Vue lo reemplazaba por completo — Vue 3 (`frontend/app/`) es ahora el único frontend del proyecto.

**Bugs reales encontrados por QA (preexistentes en el backend, heredados tal cual por la migración — no son regresiones de Vue/SQLAlchemy):**
- **F1 (bloqueante) ✅ corregido y verificado (2026-09-07)**: un producto creado desde cero vía admin no tenía `id_sql_origen`, así que nunca podía comprarse. `POST /api/productos` ahora, al dar de alta un producto nuevo, también crea las filas correspondientes en PostgreSQL (`productos` + `inventario`, vía los modelos SQLAlchemy — se agregó el modelo `Inventario` en `backend/app/models.py`) y guarda el `id_producto` resultante como `id_sql_origen` en Mongo. Orden de escritura: primero Postgres (con commit), recién si tiene éxito se escribe Mongo — así nunca queda un documento Mongo huérfano si Postgres falla. Verificado con un checkout real de principio a fin sobre un producto recién creado.
- **F2 (bloqueante para integridad de datos) ✅ corregido y verificado (2026-09-07)**: editar un producto ahora hace **merge** sobre el documento Mongo existente — solo se sobrescriben los campos que vienen en el payload; `imagenes`/`atributos`/`categoria` no enviados conservan su valor actual en vez de resetearse. Los defaults (antes `https://via.placeholder.com/300`, un servicio dado de baja) solo aplican al dar de alta un producto nuevo, y ahora el default de `imagenes` es `[]` en vez de una URL rota. Verificado: editar solo el precio de un producto con imágenes/atributos reales los preserva intactos.
- **F3 (menor, sin corregir)**: categorías sin `esquema_atributos` (ej. "Tecnología", "Moda y Ropa") no aparecen como pestaña en el catálogo público aunque tengan productos reales.
- **F4 (cosmético, sin corregir)**: `metodo_pago` inválido en checkout muestra el mensaje crudo de Postgres en vez de uno de negocio (no alcanzable desde la UI normal).
- **F5 ✅ corregido junto con F2**: el placeholder de imagen por defecto ya no apunta al servicio dado de baja (default ahora es `imagenes: []`, con fallback a ícono SVG en el frontend).

Pendiente (menor, no bloqueante): F3 y F4, a decidir si se abordan.

**Panel admin migrado** (`frontend/app/src/views/VistaAdmin.vue` + `components/admin/`): `LoginAdmin`, `SidebarAdmin`, `GestionProductos` + `FormularioProducto`, `GestionCategorias` + `FormularioCategoria`, `GestionUsuarios`, `GestionVentas`, `HistorialProducto`. Reusa `useSesion` (misma sesión global que el sitio público, fiel al comportamiento del vanilla) y agrega `composables/useCategorias.js` (compartido entre catálogo y categorías). Verificado en navegador real: catálogo, categorías con atributos, usuarios con roles, e historial con reconstrucción point-in-time funcionando sobre datos reales.

**Corrección de alcance vs. README (confirmada intencional por el usuario, 2026-09-06)**: el `README.md` decía que solo `administrador` puede entrar al panel, pero el código real de `admin.js` también permite `vendedor`, con acceso recortado a solo su propio catálogo y "Mis ventas" (sin Categorías/Usuarios). El usuario confirmó que este es el comportamiento deseado: el vendedor tiene "acceso de admin" pero acotado únicamente a sus propios datos. Se migró tal cual, y el `README.md` ya describe este comportamiento.

**Nota de estilo (actualizado 2026-09-07)**: todo el panel admin (`GestionUsuarios`, `GestionProductos`/`FormularioProducto`, `GestionCategorias`/`FormularioCategoria`, `SidebarAdmin`, `LoginAdmin`) fue migrado de la paleta indigo/slate original de `admin.html` a la paleta `accent`/neutral del sitio público, a pedido del usuario. `GestionVentas` e `HistorialProducto` (fuera de su formulario, que sí ya estaba en `accent`) no se tocaron por no haberse pedido explícitamente. Verificado en navegador real en Catálogo, Categorías y Usuarios: sin errores de consola, funcionalidad intacta.

**Layout (2026-09-07)**: Catálogo, Categorías y Usuarios del admin pasaron de una columna angosta centrada a un layout de dos columnas (tabla con scroll interno propio a la izquierda + formulario de alta como panel fijo a la derecha), aprovechando mejor el ancho de pantalla. El catálogo público también recibió un tratamiento similar (categorías/filtros en barra lateral en escritorio, arriba en móvil, con scroll interno minimalista). Se corrigió un bug de overflow horizontal en `FormularioCategoria.vue`: la fila de atributos dinámicos (grid con columna fija de 110px para "Tipo") se desbordaba fuera de la tarjeta en el panel angosto porque los inputs no tenían `min-w-0` — CSS Grid no encoge los ítems por debajo de su ancho de contenido intrínseco por defecto.

**Incidente de scope (2026-09-07)**: durante una tarea de restyle, el agente de frontend agregó por su cuenta un endpoint (`GET /api/historial/recientes`) y una función de "Cambios recientes" en el historial que no fueron solicitados, violando la instrucción explícita de no tocar `backend/`. Se revirtió por completo a pedido del usuario. Ojo para el futuro: en esta sesión se observó que mensajes del usuario enviados mientras un agente en background seguía "vivo" (resumable) a veces le llegaban directamente a ese agente además de a la sesión principal, causando trabajo no coordinado — vale la pena verificar el estado real de los archivos después de cualquier tarea larga en vez de asumir que solo se hizo lo que se pidió en el prompt original.

**Sitio público migrado** (`frontend/app/src/views/VistaPublica.vue` + `VistaDetalleProducto.vue` + `components/publico/`): `NavPublica`, `CatalogoProductos` + `FiltrosCatalogo` + `TarjetaProducto`, `Carrito` + `FormularioCheckout`, `FormularioLogin`, `FormularioRegistro`. Sin Pinia — todo con composables reactivos simples (mismo patrón que `useSesion`), incluyendo el nuevo `composables/useCarrito.js` (en ese momento persistido en `localStorage["carrito_tiendaya"]`; desde la Entrega 2 el carrito vive en Redis, vía `/api/carrito/<id_usuario>`, y requiere sesión iniciada — ver el historial de decisiones, 2026-09-13).

**Página de detalle de producto (2026-09-07):** a pedido del usuario, se reemplazó el modal `DetalleProducto.vue` (overlay sobre el catálogo) por una página propia con URL real — ruta `/producto/:id` (`views/VistaDetalleProducto.vue`), registrada en `router/index.js`. `TarjetaProducto.vue` ahora navega con `RouterLink` en vez de emitir un evento `click` capturado por el padre, así que un producto se puede abrir en pestaña nueva (ctrl/cmd+click) como en un e-commerce real. La página muestra imagen grande, descripción, especificaciones (`atributos`) en una tabla de dos columnas, SKU/ID/stock/vendedor y el mismo flujo de "agregar al carrito" que tenía el modal. Como el carrito/login/registro siguen sin URL propia (viven como tabs internos de `VistaPublica.vue`), la barra de navegación en esta página redirige a `/` con un query param (`?vista=carrito`, `?vista=catalogo&q=...`) que `VistaPublica.vue` lee una sola vez al montar.

**Nota importante:** el sitio vanilla original **no tenía carrito ni checkout implementados** (solo catálogo, detalle, login/registro) — esa parte no se "portó", se construyó nueva contra el contrato real del backend (`sp_procesar_checkout`), siguiendo el mismo patrón de composables. Verificado con un checkout real end-to-end (comprador `carlos.mendez@email.com`, credenciales de prueba documentadas en `README.md`).

**~~Limitación conocida a resolver (no bloqueante)~~ ✅ resuelta (2026-09-23):** antes no existía un endpoint para listar las direcciones de un comprador, así que el checkout pedía el "ID de dirección de envío" como número manual. Ahora `GET`/`POST /api/usuarios/<id_usuario>/direcciones` (`backend/app/blueprints/direcciones.py`) las lista y las crea, y `FormularioCheckout.vue` usa un selector real (ver el historial de decisiones al final).

**Utilidades compartidas migradas** (`frontend/app/src/`), reemplazando `frontend/js/common.js`:
- `services/api.js` — `apiFetch`, port 1:1 del wrapper de fetch original.
- `composables/useSesion.js` — sesión reactiva (`ref`) sobre `localStorage["usuario_tiendaya"]`.
- `composables/useToast.js` + `components/ToastContainer.vue` — notificaciones reactivas (reemplaza `toast()`).
- `utils/categoriaVisual.js` + `components/MiniaturaCategoria.vue` — ícono SVG de respaldo por categoría.
- `components/ImagenProducto.vue` — imagen real del producto con fallback a ícono SVG vía `@error` (más idiomático en Vue que el HTML-string + `onerror` inline que usaba la versión vanilla).

Verificado en navegador real: fetch real a `GET /api/categorias` contra el backend Flask, sesión reactiva (set/limpiar), toasts success/error, e `ImagenProducto` con imagen real y con fallback.

Estructura actual (ver el README raíz para la lista completa):
```
frontend/app/
  src/
    main.js               # createApp(App).use(router).mount
    App.vue                # solo <RouterView />
    style.css               # @import "tailwindcss"; + @theme (accent, Inter)
    router/index.js          # rutas "/", "/producto/:id" y "/admin/:tab?"
    views/
      VistaPublica.vue        # sitio público real (catálogo, carrito, checkout, login/registro)
      VistaDetalleProducto.vue # página de producto (especificaciones, reseñas, oferta límite)
      VistaAdmin.vue           # panel admin real (catálogo, categorías, usuarios, ventas, historial, fraude)
    components/publico/, components/admin/, composables/, services/, utils/
  vite.config.js           # plugins: vue(), tailwindcss(); puerto 5173
  README.md                # cómo levantar dev/build
```

## Base de datos

| Capa | Estado | Nota |
|---|---|---|
| PostgreSQL | Sin cambios de motor | Sigue siendo la fuente transaccional (usuarios, pedidos, checkout vía stored procedure). |
| MongoDB | Sin cambios de motor | Sigue siendo el catálogo de productos + historial (event sourcing); Entrega 2 le agrega la colección `resenas`. |
| Redis | ✅ Nuevo (Entrega 2) | Carrito de compra (`carrito:{id_usuario}`, TTL 30 min) y oferta de inventario limitado (`oferta:{producto_id}:stock`, decremento atómico vía script Lua). Ninguno de los dos es fuente de verdad del inventario real — ver limitación conocida en `README.md`. |
| Neo4j | ✅ Nuevo (Entrega 2) | Grafo `(:Cuenta)-[:CALIFICO]->(:Producto)` para detección de fraude en reseñas. Ver `docs/decisiones/ADR-002-grafos-vs-columnar.md` para la justificación frente a la alternativa columnar (descartada por ahora). |
| Migraciones | Script custom (`database/migrations/migracion_postgres_a_mongo.py`, `sembrar_resenas_fraude.py`) | No se introduce una herramienta de migraciones (Alembic, etc.) en esta fase; se evaluará si SQLAlchemy lo justifica más adelante. |

## Historial de decisiones

- 2026-09-06: se decide migrar de forma incremental, empezando por el backend
  (Blueprints + SQLAlchemy), y usar Vue 3 + Vite para el frontend en una fase
  posterior.
- 2026-09-06: se completa la reorganización de `backend/main.py` en Blueprints
  de Flask con application factory. Sin cambios de comportamiento: las 13
  rutas originales quedan idénticas en path, método y respuesta. Verificado
  con `app.url_map` y con el servidor real contra Postgres/Mongo.
- 2026-09-06: se completa la migración a SQLAlchemy para todo el acceso a
  PostgreSQL (auth, categorías, vendedores, e invocación del stored procedure
  de checkout). Se detectó y corrigió un bug real durante la migración:
  `Usuario.fecha_registro` no tenía declarado el `server_default` de la
  columna, lo que rompía `POST /api/auth/register` con `NotNullViolation`
  (SQLAlchemy mandaba `NULL` explícito en vez de dejar que Postgres aplicara
  el default). Se agregó `server_default=CURRENT_TIMESTAMP` también a
  `Producto.fecha_creacion` y `Pedido.fecha_pedido` por consistencia con el
  DDL. `get_pg_connection()` y el import de `psycopg2` crudo se eliminaron de
  `backend/app/extensions.py` al quedar sin uso.
- 2026-09-06: se crea el scaffold de Vue 3 + Vite + Tailwind v4 + Vue Router
  en `frontend/app/`, sin tocar el sitio vanilla existente (sigue siendo el
  de producción). Verificado con captura de pantalla en `/` y `/admin`:
  tema Tailwind y enrutamiento funcionan. Sin lógica de negocio migrada aún.
- 2026-09-07: con la migración a Vue funcionalmente completa y verificada
  (sitio público + panel admin, QA end-to-end sin regresiones), el usuario
  decide el corte de producción: se elimina el sitio vanilla original
  (`frontend/index.html`, `frontend/admin.html`, `frontend/js/`) del
  repositorio. `frontend/app/` (Vue) queda como el único frontend del
  proyecto. Se actualiza el README raíz, este documento y
  `frontend/app/README.md` para reflejar el corte (ya no se documentan "dos
  frontends", solo Vue).
- 2026-09-13: arranca la Entrega 2. El usuario decide, entre grafos y
  columnar, implementar **Neo4j** para detección de fraude en reseñas
  (aun sabiendo que implica construir el sistema de reseñas desde cero,
  ya que no existía) y descartar Cassandra/columnar por ahora (ver
  `docs/decisiones/ADR-002-grafos-vs-columnar.md`); infraestructura nueva
  vía Docker Compose (`docker-compose.yml`, servicios `redis:7-alpine` y
  `neo4j:5-community`).
- 2026-09-13: se detecta que la base de datos Postgres local ya tenía
  datos reales encima de la semilla original (cuenta admin propia, un
  vendedor agregado a mano, el rol de un comprador semilla cambiado por
  pruebas previas), lo que habría chocado con un script de semilla que
  asumiera IDs fijos. Se corrige `database/postgres/datos_semilla_usuarios.sql`
  para no fijar `id_usuario` (se deja que `SERIAL` los asigne) y usar
  `ON CONFLICT (email) DO NOTHING`, de forma que sea seguro correrlo sobre
  cualquier base sin importar su historial. Verificado aplicándolo contra
  la base real: 10 compradores nuevos insertados sin colisión.
- 2026-09-13: se completa el carrito de compra sobre Redis
  (`backend/app/blueprints/carrito.py`): hash `carrito:{id_usuario}`,
  TTL de 1800s renovado en cada operación (`EXPIRE`). `useCarrito.js` se
  migra de `localStorage` a este backend conservando su interfaz pública
  intacta (mutación optimista local + `apiFetch` en segundo plano); el
  carrito ahora requiere sesión iniciada (ya no hay carrito anónimo).
  Verificado con el servidor real: TTL confirmado con `redis-cli TTL`
  refrescándose en cada operación, y con `HGETALL` confirmando el borrado
  real tras un checkout exitoso.
- 2026-09-13: se completa la oferta de inventario limitado sobre Redis
  (`backend/app/lua/reservar_oferta.lua` + `backend/app/blueprints/ofertas.py`):
  contador atómico `oferta:{producto_id}:stock`, reserva vía script Lua
  (`EVAL`, check-and-decrement en una sola operación de servidor, sin
  locks de aplicación ni `WATCH`/`MULTI`), independiente del `inventario`
  de PostgreSQL. Se corrige `backend/main.py` para pasar `threaded=True`
  a `app.run(...)` — sin eso el servidor de desarrollo de Flask serializa
  requests y la prueba de concurrencia no sería válida. Evidencia real
  (`backend/scripts/prueba_concurrencia_oferta.py`, 50 requests
  concurrentes contra un límite de 10): 10 éxitos, 40 rechazos, stock
  final en Redis = 0 — sin sobreventa.
- 2026-09-13: se construye el sistema de reseñas desde cero
  (`backend/app/blueprints/resenas.py`, colección Mongo `resenas`,
  índice único `{producto_id, autor.id_usuario}`) y su sincronización
  síncrona a Neo4j (`MERGE` sobre nodos `Cuenta`/`Producto` y relación
  `CALIFICO`, en su propio try/except desacoplado del insert en Mongo —
  mismo criterio de "sin 2PC" ya usado entre Postgres/Mongo). El cálculo
  de `verificada_compra` hace join contra `pedidos`/`lineas_pedido` de
  Postgres sin bloquear la creación de la reseña si no hay compra
  registrada (deliberado: el patrón de fraude a detectar depende de que
  se pueda calificar sin haber comprado). Verificado con el servidor real
  contra Neo4j real: nodo/relación creados correctamente, sin duplicar
  nodos entre reseñas del mismo producto.
- 2026-09-13: se siembran datos de prueba con un patrón de fraude
  detectable (`database/migrations/sembrar_resenas_fraude.py`, idempotente,
  sin IDs fijos — consulta compradores/productos reales en cada corrida):
  ruido legítimo (53 reseñas dispersas en 30 días), un anillo de fraude
  fuerte (4 cuentas que se califican mutuamente sobre los mismos 4
  productos de un mismo vendedor, calificación 5 fija, concentradas en
  menos de 2 horas) y un anillo débil de control (2 cuentas, 2 productos
  compartidos, que no debe marcarse como sospechoso). Durante la
  verificación se confirmó que, con 11 cuentas y 18 productos, algunos
  pares de cuentas no relacionadas coinciden por azar en 3+ productos
  compartidos — un umbral ingenuo de "productos compartidos" por sí solo
  generaría falsos positivos.
- 2026-09-13: se implementa la detección de fraude
  (`backend/app/blueprints/fraude.py`, `GET /api/fraude/alertas`) con una
  consulta Cypher de 3 saltos que combina tres señales para evitar los
  falsos positivos detectados en el paso anterior: productos compartidos
  (≥3 por par), calificación uniforme de 5 estrellas en ambos lados del
  par, y una ventana de tiempo corta entre ambas calificaciones (6h por
  defecto). Verificado contra los datos reales sembrados: el anillo
  fuerte aparece completo (los 4 tríos posibles de las 4 cuentas
  involucradas), el anillo débil de control no aparece en ningún
  resultado, y no se detectaron falsos positivos adicionales del ruido
  aleatorio.
- 2026-09-14: se completa la UI de la Entrega 2 en una sola pasada (para
  evitar que dos agentes tocaran `VistaDetalleProducto.vue` a la vez):
  `components/publico/OfertaLimitada.vue` (barra de progreso, reserva,
  polling cada 3s, alta/cierre de oferta para vendedor/admin),
  `components/publico/ResenasProducto.vue` (listado con badge de compra
  verificada, formulario gateado a rol comprador), y
  `components/admin/GestionFraude.vue` (tab nuevo, solo administrador,
  con fila expandible con el JSON crudo de cada alerta). Verificado
  reproduciendo las llamadas reales que hace cada componente contra el
  backend (creación/reserva/cierre de oferta, alta de reseña duplicada,
  alertas de fraude con y sin rol de administrador) y confirmando que
  Vite transforma los módulos sin errores — sin acceso a un navegador
  real en este entorno, pendiente una verificación visual manual.
- 2026-09-14: pase de QA independiente sobre los 4 blueprints nuevos, la
  regresión de checkout/catálogo/categorías/historial/auth, y la
  interacción entre piezas nuevas (carrito + checkout, oferta + carrito
  en paralelo, reseña reflejada en Mongo y Neo4j) — sin hallazgos de bugs.
  Se detectó un hueco en los datos semilla (no un bug de código): de los
  11 compradores, solo Sofia Lopez tenía una dirección de envío propia,
  así que un checkout real con cualquier otro comprador nuevo fallaba con
  "la dirección no pertenece al comprador". Se corrige agregando una
  dirección principal por email a cada uno de los 10 compradores nuevos
  en `datos_semilla_usuarios.sql` (mismo criterio de `ON CONFLICT`/lookup
  dinámico, sin IDs fijos). Verificado contra la base real: los 11
  compradores tienen dirección propia.
- 2026-09-22: se fusiona `main` (Entrega 2) en `dev` (atributos personalizados
  por producto) y, tras revisar el proyecto contra el enunciado oficial, se
  corrigen los huecos de mayor peso en la rúbrica de la Entrega 2:
  (1) la oferta de inventario limitado ahora tiene **ventana de tiempo**:
  `POST /api/ofertas` exige `duracion_minutos` (1 a 10 080) y las claves
  `oferta:{id}:stock`/`:limite` se crean con ese TTL, así que la oferta
  vence sola; `GET` devuelve `segundos_restantes` y `fecha_fin`, y la
  página del producto muestra una cuenta regresiva. (2) Solo el vendedor
  dueño del producto o un administrador pueden crear o cerrar su oferta.
  (3) El checkout toma los productos del **carrito guardado en Redis** en
  vez de los que envía el navegador, responde `409 CARRITO_VACIO` si el
  carrito expiró y borra el carrito tras confirmar el pago; el frontend
  recarga el carrito al abrirlo. `prueba_concurrencia_oferta.py` pasa a
  usar un producto real (PROD-0001), ya que ahora se valida que exista.
  Verificado end-to-end contra el servidor real: compra real (pedido 11,
  la lista de productos falsa enviada por el cliente se ignoró), checkout
  con carrito expirado rechazado sin crear pedido, expiración de la
  oferta, 403 para vendedor ajeno y prueba de concurrencia en PASS
  (10 éxitos, 40 rechazos, stock final 0). Se agregan
  `docs/decisiones/ADR-003-redis-carrito-y-oferta.md` y
  `docs/informe-entrega-2.md` (borrador), y se pone al día la
  documentación desactualizada (README, este documento, `arquitectura.md`
  y el README del frontend).
- 2026-09-22 (tarde): a partir de pruebas del usuario en el navegador:
  (1) la **referencia de pago pasa a generarla el backend**
  (`TY-AAAAMMDDHHMMSS-XXXXXX`, hora de Guatemala + 6 hex); el campo se
  quita del formulario de checkout, `POST /api/checkout` ignora
  `referencia_pago` si llega y la devuelve en la respuesta 201.
  (2) Se diagnostica que "el carrito no se vacía tras comprar" no era un
  bug del código sino del servidor de desarrollo: con el repo dentro de
  OneDrive, el watcher de Vite perdió eventos de cambio y el navegador
  terminó con **dos instancias de `useCarrito.js`** (distinto `?t=`); el
  checkout vaciaba una y la pantalla mostraba la otra. Se reinicia Vite y
  se activa `server.watch.usePolling` (300 ms) en `vite.config.js`.
  (3) Para que las reseñas no queden escondidas al final de la página: al
  confirmar la compra se muestra un resumen (pedido, referencia y un botón
  "Dejar reseña" por producto que abre `/producto/:id#escribir-resena`), y
  la página del producto tiene un enlace "★ Escribir reseña" bajo el
  precio; el router hace scroll al ancla esperando a que el producto
  termine de cargar. Verificado en el navegador real (pedido 15).
- 2026-09-23: (1) **Direcciones de envío**: nuevo blueprint
  `backend/app/blueprints/direcciones.py` (`GET` y `POST
  /api/usuarios/<id_usuario>/direcciones`) y modelo SQLAlchemy `Direccion`
  en `models.py` (tabla `direcciones` del DDL). La primera dirección de un
  usuario queda como principal y marcar otra como principal desmarca la
  anterior (el alta bloquea la fila del usuario con `SELECT ... FOR UPDATE`
  para que dos altas simultáneas no dejen dos principales).
  `FormularioCheckout.vue` deja de pedir el ID de dirección a mano: muestra
  un selector con las direcciones del comprador, con la principal
  preseleccionada, y un mini formulario para agregar una si no tiene
  ninguna o quiere otra. Antes el usuario tenía que adivinar el ID y el
  checkout fallaba con "La dirección X no pertenece al comprador Y".
  (2) **Imágenes desde el panel admin**: `FormularioProducto.vue` agrega la
  sección "Imágenes del producto" (hasta 10 links http/https, miniatura de
  vista previa, radio de portada y botones ↑/↓ para reordenar).
  `POST /api/productos` valida y normaliza `imagenes` con
  `_normalizar_imagenes` (lista de strings u objetos `{url, es_portada}` →
  `[{id_imagen, url, es_portada, orden}]`, una sola portada: la marcada o
  la primera; quita duplicados; 400 si hay una URL inválida o más de 10),
  **antes** de escribir en Postgres o Mongo, así un error no deja filas
  huérfanas. En edición se mantiene el merge de F2: sin `imagenes` se
  conservan las existentes y con `[]` se vacían; el formulario siempre
  envía la lista completa. Estas imágenes viven solo en Mongo: la
  migración completa las borra y `--incremental` las conserva (ver
  `README.md`).
