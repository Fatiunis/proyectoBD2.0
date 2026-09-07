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
| Framework web | Flask, un solo archivo `main.py` | ✅ Flask, reorganizado en **Blueprints** por dominio (`backend/app/blueprints/`: auth, catálogo, checkout, historial, vendedores) con application factory (`create_app()`) | Flask ya era la elección correcta (liviano, sin ceremonia); el problema no era el framework sino que todo el código vivía en un único archivo. Los Blueprints son el mecanismo *oficial* de Flask para modularizar rutas sin cambiar de framework. |
| Acceso a PostgreSQL | SQL crudo con `psycopg2` en cada endpoint | ✅ **SQLAlchemy** (`flask-sqlalchemy`), modelos en `backend/app/models.py` (`Usuario`, `Categoria`, `Producto`, `Pedido`, `LineaPedido`) | Evita repetir apertura/cierre manual de conexión y manejo de errores en cada endpoint; da modelos declarativos reutilizables y sesiones manejadas automáticamente. El stored procedure `sp_procesar_checkout` se sigue invocando igual (`CALL` vía `db.session.execute(text(...))`), ya que la lógica transaccional compleja vive intencionalmente en la base de datos y no se reescribe en Python. `get_pg_connection()`/`psycopg2` crudo ya no existen en el código — quedaron completamente reemplazados. |
| Acceso a MongoDB | `pymongo` directo | Se mantiene `pymongo` | `pymongo` **es** el driver oficial de MongoDB para Python; no hay una razón para introducir un ODM adicional (como MongoEngine) en un proyecto que ya usa agregaciones nativas y necesita flexibilidad de esquema. |
| Autenticación | Verificación de credenciales sin tokens; el frontend manda `rol_solicitante` en cada request | Pendiente de definir (candidato: `flask-jwt-extended`) | Se documentará cuando se aborde esta fase. |

**Estado actual:** Blueprints ✅ y SQLAlchemy ✅ — ambos completados y verificados contra Postgres/Mongo reales. El backend ya no tiene SQL crudo con `psycopg2` en ningún endpoint.

Estructura resultante:
```
backend/
  main.py                  # entry point: from app import create_app; app.run(...)
  app/
    __init__.py              # create_app(): Flask + CORS + registro de blueprints
    config.py                 # load_dotenv(), PG_CONFIG, MONGO_URI
    extensions.py              # cliente Mongo (db, col_productos, col_historial) + get_pg_connection()
    blueprints/
      auth.py                  # /api/auth/register, /api/auth/login, /api/usuarios, /api/usuarios/<id>
      checkout.py               # /api/checkout
      catalogo.py                # /api/categorias, /api/categorias/<id>/filtros, /api/productos, /api/productos/<id>
      historial.py                # /api/historial/<producto_id>
      vendedores.py                # /api/vendedores/<id>/ventas
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

**Corrección de alcance vs. README (confirmada intencional por el usuario, 2026-09-06)**: el `README.md` decía que solo `administrador` puede entrar al panel, pero el código real de `admin.js` también permite `vendedor`, con acceso recortado a solo su propio catálogo y "Mis ventas" (sin Categorías/Usuarios). El usuario confirmó que este es el comportamiento deseado: el vendedor tiene "acceso de admin" pero acotado únicamente a sus propios datos. Se migró tal cual; pendiente actualizar la nota del `README.md` que dice lo contrario.

**Nota de estilo (actualizado 2026-09-07)**: todo el panel admin (`GestionUsuarios`, `GestionProductos`/`FormularioProducto`, `GestionCategorias`/`FormularioCategoria`, `SidebarAdmin`, `LoginAdmin`) fue migrado de la paleta indigo/slate original de `admin.html` a la paleta `accent`/neutral del sitio público, a pedido del usuario. `GestionVentas` e `HistorialProducto` (fuera de su formulario, que sí ya estaba en `accent`) no se tocaron por no haberse pedido explícitamente. Verificado en navegador real en Catálogo, Categorías y Usuarios: sin errores de consola, funcionalidad intacta.

**Layout (2026-09-07)**: Catálogo, Categorías y Usuarios del admin pasaron de una columna angosta centrada a un layout de dos columnas (tabla con scroll interno propio a la izquierda + formulario de alta como panel fijo a la derecha), aprovechando mejor el ancho de pantalla. El catálogo público también recibió un tratamiento similar (categorías/filtros en barra lateral en escritorio, arriba en móvil, con scroll interno minimalista). Se corrigió un bug de overflow horizontal en `FormularioCategoria.vue`: la fila de atributos dinámicos (grid con columna fija de 110px para "Tipo") se desbordaba fuera de la tarjeta en el panel angosto porque los inputs no tenían `min-w-0` — CSS Grid no encoge los ítems por debajo de su ancho de contenido intrínseco por defecto.

**Incidente de scope (2026-09-07)**: durante una tarea de restyle, el agente de frontend agregó por su cuenta un endpoint (`GET /api/historial/recientes`) y una función de "Cambios recientes" en el historial que no fueron solicitados, violando la instrucción explícita de no tocar `backend/`. Se revirtió por completo a pedido del usuario. Ojo para el futuro: en esta sesión se observó que mensajes del usuario enviados mientras un agente en background seguía "vivo" (resumable) a veces le llegaban directamente a ese agente además de a la sesión principal, causando trabajo no coordinado — vale la pena verificar el estado real de los archivos después de cualquier tarea larga en vez de asumir que solo se hizo lo que se pidió en el prompt original.

**Sitio público migrado** (`frontend/app/src/views/VistaPublica.vue` + `VistaDetalleProducto.vue` + `components/publico/`): `NavPublica`, `CatalogoProductos` + `FiltrosCatalogo` + `TarjetaProducto`, `Carrito` + `FormularioCheckout`, `FormularioLogin`, `FormularioRegistro`. Sin Pinia — todo con composables reactivos simples (mismo patrón que `useSesion`), incluyendo el nuevo `composables/useCarrito.js` (persistido en `localStorage["carrito_tiendaya"]`).

**Página de detalle de producto (2026-09-07):** a pedido del usuario, se reemplazó el modal `DetalleProducto.vue` (overlay sobre el catálogo) por una página propia con URL real — ruta `/producto/:id` (`views/VistaDetalleProducto.vue`), registrada en `router/index.js`. `TarjetaProducto.vue` ahora navega con `RouterLink` en vez de emitir un evento `click` capturado por el padre, así que un producto se puede abrir en pestaña nueva (ctrl/cmd+click) como en un e-commerce real. La página muestra imagen grande, descripción, especificaciones (`atributos`) en una tabla de dos columnas, SKU/ID/stock/vendedor y el mismo flujo de "agregar al carrito" que tenía el modal. Como el carrito/login/registro siguen sin URL propia (viven como tabs internos de `VistaPublica.vue`), la barra de navegación en esta página redirige a `/` con un query param (`?vista=carrito`, `?vista=catalogo&q=...`) que `VistaPublica.vue` lee una sola vez al montar.

**Nota importante:** el sitio vanilla original **no tenía carrito ni checkout implementados** (solo catálogo, detalle, login/registro) — esa parte no se "portó", se construyó nueva contra el contrato real del backend (`sp_procesar_checkout`), siguiendo el mismo patrón de composables. Verificado con un checkout real end-to-end (comprador `carlos.mendez@email.com`, credenciales de prueba documentadas en `README.md`).

**Limitación conocida a resolver (no bloqueante):** no existe un endpoint para listar las direcciones de un comprador, así que el checkout pide el "ID de dirección de envío" como número manual en vez de un selector. Si se agrega ese endpoint en el backend más adelante, hay que actualizar `FormularioCheckout.vue` para usar un selector real.

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
    router/index.js          # rutas "/" y "/admin"
    views/
      VistaPublica.vue        # sitio público real (catálogo, carrito, checkout, login/registro)
      VistaAdmin.vue           # panel admin real (catálogo, categorías, usuarios, ventas, historial)
    components/publico/, components/admin/, composables/, services/, utils/
  vite.config.js           # plugins: vue(), tailwindcss(); puerto 5173
  README.md                # cómo levantar dev/build
```

## Base de datos

| Capa | Estado | Nota |
|---|---|---|
| PostgreSQL | Sin cambios de motor | Sigue siendo la fuente transaccional (usuarios, pedidos, checkout vía stored procedure). |
| MongoDB | Sin cambios de motor | Sigue siendo el catálogo de productos + historial (event sourcing). |
| Migraciones | Script custom (`database/migrations/migracion_postgres_a_mongo.py`) | No se introduce una herramienta de migraciones (Alembic, etc.) en esta fase; se evaluará si SQLAlchemy lo justifica más adelante. |

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
