# TiendaYa — Reporte del trabajo de la Entrega 3

**Curso:** Bases de Datos 2 — Universidad del Istmo
**Integrantes:** Diego Rueda, Marcos Pineda, Fátima Ramazzini
**Fecha del reporte:** 8 de octubre de 2026

Este documento cuenta **cómo se hizo** la Entrega 3: qué se construyó, por qué se eligió cada mecanismo, cómo se probó, qué falló en la verificación posterior y cómo se corrigió, y qué queda pendiente. No reemplaza al informe formal que se entrega al catedrático, [`informe-entrega-3.md`](informe-entrega-3.md), que resume los resultados; este reporte da el detalle y remite a los documentos de diseño. Para la demostración en vivo hay un guion aparte: [`guion-demostracion-entrega-3.md`](guion-demostracion-entrega-3.md).

**Cómo leer las cifras.** Se distinguen tres orígenes:

- **Evidencia guardada**: la salida real de los scripts del 5 de octubre de 2026, en [`evidencia/prueba_buscador.txt`](evidencia/prueba_buscador.txt) y [`evidencia/prueba_fallas_checkout.txt`](evidencia/prueba_fallas_checkout.txt).
- **Verificación del 6 de octubre**: las corridas de la verificación posterior, registradas en [`hallazgos.md`](hallazgos.md).
- **Consultado hoy (2026-10-08)**: lecturas hechas contra el sistema que está corriendo, sin modificar datos. Se marcan como "verificado hoy".

---

## 1. Resumen ejecutivo

### Qué pedía el enunciado

Según [`Proyecto_TiendaYa_BasesDeDatos2.pdf`](Proyecto_TiendaYa_BasesDeDatos2.pdf) (Entrega 3, semana 12, "Recuperación de información y consistencia en operaciones distribuidas", 15 puntos):

- Búsqueda de productos por texto libre, con tolerancia a variaciones ortográficas y orden por relevancia.
- Filtros facetados calculados con las agregaciones del motor de búsqueda.
- Manejo explícito de fallos parciales en el checkout, con un comportamiento definido y comunicado al usuario ante al menos una falla simulada.
- Un índice con un mapping construido deliberadamente, no el que el motor pone por defecto.
- Al menos una funcionalidad de autocompletado o de corrección ortográfica, y al menos una agregación para las facetas.
- Un documento de estrategia de consistencia del checkout: componentes, puntos de falla y mecanismo de mitigación (reintentos idempotentes, compensación o una ventana de consistencia eventual aceptada y documentada).
- Evidencia de al menos una prueba de falla simulada.
- **Opcional**: evaluar la migración del módulo de pagos a un motor NewSQL (puede sumar puntos, sea cual sea la conclusión).
- Entregable: el buscador, el documento de estrategia con la evidencia, y el diagrama de arquitectura actualizado.

### Rúbrica y estado de cada punto

| Criterio de la rúbrica | Peso | Estado | Evidencia |
|---|---|---|---|
| Buscador implementado, con tolerancia a variaciones y filtros facetados | 5 pts | Cumplido | Sección 2 de este reporte; [ADR-004](decisiones/ADR-004-motor-de-busqueda.md); `prueba_buscador.py --caida-real` 21/21 ([evidencia](evidencia/prueba_buscador.txt)) |
| Documento de estrategia de consistencia para el checkout distribuido | 5 pts | Cumplido | [`estrategia-consistencia-checkout.md`](estrategia-consistencia-checkout.md) (14 puntos de falla, F1-F14); sección 3 de este reporte |
| Evidencia de la prueba de falla simulada y su manejo | 4 pts | Cumplido | `prueba_fallas_checkout.py --caida-real` 45/45, con 4 fallas simuladas y una caída real de Elasticsearch ([evidencia](evidencia/prueba_fallas_checkout.txt)); sección 4 |
| Calidad del informe y del repositorio | 1 pt | Cumplido en lo técnico, con dos pendientes del equipo | [`informe-entrega-3.md`](informe-entrega-3.md) sigue marcado "Borrador" y su sección 1 (distribución de responsabilidades) está sin llenar (ver sección 9) |
| Evaluación NewSQL para pagos (opcional) | adicional | Cumplido | [ADR-005](decisiones/ADR-005-newsql-pagos.md): no migrar, con las condiciones en que sí convendría; sección 5 |
| Diagrama de arquitectura actualizado (entregable) | — | Cumplido | [`arquitectura.md`](arquitectura.md) |

---

## 2. Buscador (Elasticsearch)

### 2.1 Diagnóstico previo

Hasta la Entrega 2, la búsqueda usaba el índice de texto de MongoDB (`idx_texto_busqueda`, `$text`). Se probó contra el catálogo real (1015 productos) el 5 de octubre de 2026 ([ADR-004](decisiones/ADR-004-motor-de-busqueda.md), Contexto):

| Búsqueda | MongoDB `$text` | Qué buscaba el usuario |
|---|---|---|
| `laptp` | 0 resultados | laptops (error de tipeo) |
| `audifnos` | 0 | audífonos |
| `celulr` | 0 | celulares |
| `lapt` | 0 | laptops (palabra a medio escribir) |
| `auriculares` | 0 | audífonos (sinónimo) |
| `celular` | 14, todos tablets "Wi-Fi + Celular" | celulares |

La causa es estructural: `$text` no tiene coincidencia aproximada, ni por prefijo, ni sinónimos, y su relevancia no se puede ajustar por campo. Se evaluaron cuatro alternativas (no cambiar y usar `$facet`; texto completo de PostgreSQL con `pg_trgm`; Atlas Search; Elasticsearch). Se eligió **Elasticsearch 8.15** porque es la única que cubre a la vez tolerancia, sinónimos, relevancia ajustable, sugerencias y facetas en una sola consulta. PostgreSQL quedó descartado porque el catálogo no vive ahí desde la Entrega 1, y Atlas Search porque solo existe en la nube, no en la MongoDB Community del proyecto.

### 2.2 Diseño del índice y mapping

El índice es una **proyección de solo lectura** de la colección `productos` de MongoDB, que sigue siendo la fuente de verdad del catálogo. Se consulta siempre por el alias `productos`, que apunta a un índice versionado `productos_v<fecha>`; así, reindexar no corta el servicio. 1 shard y 0 réplicas, porque corre en un solo nodo (`docker-compose.yml`, heap de 512 MB, sin seguridad).

Definición completa en [`database/elasticsearch/productos_indice.json`](../database/elasticsearch/productos_indice.json). Resumen, campo por campo:

| Pieza | Definición | Por qué |
|---|---|---|
| `dynamic: strict` | Rechaza campos no declarados | Ningún campo entra con un tipo adivinado por el motor |
| Analizador `es_texto` (al indexar) | `standard` + minúsculas + `asciifolding` + stop words en español + `stemmer_override` + `light_spanish` | "Audífonos", "audifonos" y "AUDÍFONOS" se indexan igual; "mochilas" y "mochila" comparten raíz |
| Analizador `es_texto_busqueda` (al buscar) | Lo mismo más `synonym_graph` | Los sinónimos ("celular, smartphone, telefono movil", "laptop, portatil, notebook", "audifonos, auriculares, headphones, cascos" y otros seis grupos) se aplican solo al buscar: agregar uno no obliga a reindexar |
| `stemmer_override` (`plurales_prestados`) | `laptops => laptop`, `tablets => tablet`… (9 reglas) | El stemmer en español no quita la "s" de plurales en inglés |
| `nombre.autocompletado` | `edge_ngram` de 2 a 20 al indexar | Autocompletado por prefijo ("lapt" → Laptop) |
| `nombre.sugerencia` | Minúsculas y sin acentos, sin stemming | El corrector debe proponer palabras reales, no raíces |
| `nombre.orden` | `keyword` normalizado | Desempate alfabético estable |
| `categoria.nombre`, `marca`, `vendedor.nombre_comercial` | `keyword` | Las facetas necesitan el valor exacto |
| `atributos` | `flattened` | Unas 125 claves distintas según la categoría (124 medidas el 2026-10-06); con mapeo dinámico, cada clave sería un campo nuevo (*mapping explosion*) |
| `precio_base` | `scaled_float` (factor 100) | Dos decimales exactos, para rangos y orden |
| `imagen_portada` | `keyword` con `index: false` | Solo se muestra |

### 2.3 Relevancia

`buscar()` en [`backend/app/busqueda_es.py`](../backend/app/busqueda_es.py) arma un `bool.should` que suma varias señales:

- `multi_match` con `fuzziness: AUTO` sobre nombre (×3), categoría (×2), marca (×2) y descripción.
- Un puntaje fijo (`constant_score`, 25) si lo buscado nombra una **categoría**. Sin esto, como "Celulares" se repite en todos sus productos y su IDF es bajo, una tablet "Wi-Fi + Celular" le ganaba a un celular.
- `match_phrase` sobre el nombre, solo con 2 o más palabras (con una sola volvería a contar la misma coincidencia).
- El subcampo de autocompletado con poco peso (×0.5) y el SKU exacto (×10).

Órdenes disponibles: relevancia (con desempate alfabético), precio ascendente y precio descendente.

### 2.4 Autocompletado y corrector

- **Autocompletado**: `GET /api/busqueda/autocompletar` busca sobre `nombre.autocompletado` con un error de tipeo permitido (`fuzziness: AUTO`) y premia el prefijo de frase. Verificado hoy: `lapt` devuelve "Laptop Gamer 16 Pulgadas" y otras laptops.
- **"¿Quisiste decir…?"**: `phrase suggester` sobre `nombre.sugerencia` en modo `missing`, para que solo corrija palabras que no existen en el índice (no "corrige" una marca como "sony").

### 2.5 Facetas disyuntivas

`GET /api/busqueda` devuelve facetas de categoría, marca, tienda y rango de precio (cinco rangos fijos, de "Menos de Q100" a "Más de Q5,000"), con agregaciones `terms` y `range`. Son **disyuntivas**: los filtros elegidos van en `post_filter` y cada agregación aplica los filtros de las *otras* facetas. Por eso, elegir "Logitech" no hace desaparecer las demás marcas, pero sí recalcula tiendas y precios.

### 2.6 Sincronización con MongoDB

- **Al guardar un producto en el admin**, `catalogo.py` lo reindexa en el acto. Si Elasticsearch no responde, registra un evento `indexar_producto` en el outbox y lo reintenta el relevo (sección 3).
- **El stock** se actualiza tras cada compra con el evento `stock_elasticsearch` del outbox del checkout.
- **Reconstrucción completa**: [`database/migrations/indexar_productos_elasticsearch.py`](../database/migrations/indexar_productos_elasticsearch.py) crea un índice nuevo, verifica que tenga la misma cantidad de documentos que MongoDB y recién entonces mueve el alias.

Verificado hoy: el alias `productos` apunta a `productos_v20261006181736` y tiene **1015 documentos**, los mismos que MongoDB y que la tabla `productos` de PostgreSQL. El stock coincide en los 1015 productos entre los tres motores (0 desfases).

### 2.7 Degradación a MongoDB

Si el motor no está disponible (conexión, timeout, índice o alias inexistente, `401`/`403`, `429` o `5xx`), `GET /api/busqueda` responde `503 BUSCADOR_NO_DISPONIBLE`. Es el **frontend** (`ResultadosBusqueda.vue`) el que entonces repite la búsqueda contra `GET /api/productos?q=` (el `$text` de MongoDB) y muestra "El buscador avanzado no está disponible en este momento. Te mostramos una búsqueda simplificada". Si Elasticsearch está arriba pero rechaza la consulta, la API responde `400 BUSQUEDA_NO_VALIDA` y no se cae al respaldo (precisión agregada el 2026-10-06, H-002).

### 2.8 Frontend

- **Barra de búsqueda** (`NavPublica.vue`): lista desplegable de autocompletado que se navega con ↑/↓, Enter y Esc.
- **Página de resultados** (`ResultadosBusqueda.vue`): resultados por relevancia, facetas con el conteo de cada opción, orden por precio, "¿Quisiste decir…?", paginación (`Paginacion.vue`) y el aviso de búsqueda simplificada.

### 2.9 Archivos

`backend/app/busqueda_es.py`, `backend/app/blueprints/busqueda.py`, `backend/app/blueprints/catalogo.py` (reindexado al guardar), `backend/app/config.py` (`ELASTICSEARCH_URL`, `ES_ALIAS_PRODUCTOS`), `backend/app/extensions.py` (cliente), `database/elasticsearch/productos_indice.json`, `database/migrations/indexar_productos_elasticsearch.py`, `docker-compose.yml`, `requirements.txt` (`elasticsearch`), `frontend/app/src/components/publico/NavPublica.vue`, `frontend/app/src/components/publico/ResultadosBusqueda.vue`, `backend/scripts/prueba_buscador.py`.

---

## 3. Consistencia del checkout

El documento de diseño es [`estrategia-consistencia-checkout.md`](estrategia-consistencia-checkout.md). Aquí se resume qué se construyó y por qué.

### 3.1 Componentes

| Motor | Papel en el checkout |
|---|---|
| PostgreSQL | **Fuente de verdad**: `sp_procesar_checkout` crea pedido, líneas y pago y descuenta el `inventario` en una transacción con `SELECT ... FOR UPDATE` |
| Redis | Estado transitorio: el carrito (`carrito:{id}`) y las reservas de oferta relámpago (scripts Lua) |
| MongoDB | Copia del stock en el documento del producto (lo que ve el comprador) |
| Elasticsearch | Copia del stock en el índice del buscador |

### 3.2 El problema de partida

En la Entrega 2, las copias del stock a MongoDB eran de "mejor esfuerzo", sin reintentos. Si MongoDB fallaba, su stock quedaba mal hasta la próxima compra de ese producto. Si el cliente reintentaba tras un timeout, o si Redis no podía borrar el carrito, **se podía cobrar dos veces**. Y nadie se enteraba de lo que había fallado.

### 3.3 Mecanismo elegido

La regla es que **solo PostgreSQL decide si hubo compra**. Lo que pasa antes del COMMIT se compensa; lo que pasa después se completa, nunca se deshace.

1. **Idempotencia**: el navegador genera una clave (`crypto.randomUUID()`) por intento de compra y la conserva entre reintentos; solo la cambia cuando la compra se confirma. Si la clave ya existe, el backend devuelve el mismo pedido (`200`, `"repetido": true`) sin cobrar. Si llega con otro comprador, responde `409 CLAVE_IDEMPOTENCIA_AJENA`.
2. **Compensación antes del COMMIT**: las reservas de oferta se consumen en Redis antes de llamar al procedimiento (`consumir_reserva_oferta.lua`, pasan a `en_pago`). Si algo falla antes del COMMIT, `compensar_reserva_oferta.lua` las devuelve al cupo. Se consumen antes, y no después, para que nunca haya sobreventa.
3. **Una transacción local con tres escrituras**: la clave de idempotencia (primero, para que el índice único serialice dos peticiones simultáneas con la misma clave), el pedido (`sp_procesar_checkout`, sin cambios) y los eventos del outbox. O se confirman las tres o ninguna: todo pedido confirmado tiene registrado su trabajo pendiente, aunque Flask muera un milisegundo después.
4. **Outbox después del COMMIT**: el mismo request ejecuta los eventos al instante (`sincronizacion.procesar`). Hay cinco tipos, todos idempotentes:
   - `confirmar_reserva_oferta` y `limpiar_carrito` (Redis, con Lua que solo borra lo que no cambió).
   - `stock_mongo` y `stock_elasticsearch`: fijan el valor absoluto que hay en PostgreSQL, no restan.
   - `indexar_producto` (Elasticsearch, desde el admin).
5. **Relevo con backoff**: un hilo de fondo ([`backend/app/sincronizacion.py`](../backend/app/sincronizacion.py)) revisa cada 15 s (`OUTBOX_INTERVALO_SEGUNDOS`) los eventos pendientes con `FOR UPDATE SKIP LOCKED` y los reintenta con espera exponencial: 5 s, 10 s, 20 s… hasta 5 min. Tras 10 intentos (`OUTBOX_MAX_INTENTOS`) el evento queda `fallido`, para revisión manual. Se arranca una sola vez desde `backend/main.py`, que distingue el proceso del recargador de Flask con `WERKZEUG_RUN_MAIN`.

**Un hueco que se encontró y se cerró durante el desarrollo**: si Redis fallaba después del COMMIT, lo pagado quedaba en el carrito y un checkout con **otra** clave lo podía cobrar de nuevo. Ahora todo checkout aplica antes la limpieza de carrito pendiente de ese comprador, y en ese caso responde `409 CARRITO_VACIO` (escenario E3).

### 3.4 Por qué no 2PC ni una saga

- **2PC (XA)**: Redis, MongoDB y Elasticsearch no participan en transacciones XA con PostgreSQL. Aunque lo hicieran, 2PC bloquea a todos si el coordinador cae y ata la disponibilidad del pago a la del buscador: una caída de Elasticsearch impediría comprar.
- **Saga pura**: "copiar el stock al catálogo" no tiene una compensación con sentido. Deshacer un pago porque falló el buscador sería peor que tener el buscador atrasado unos segundos; lo correcto es completar la copia.

### 3.5 Garantías

1. Nunca se cobra dos veces la misma compra (ni por un reintento ni por un carrito sin limpiar).
2. Nunca se vende más de lo que hay (inventario ni cupo de oferta).
3. Pedido, líneas, pago e inventario son atómicos.
4. Un pedido confirmado es definitivo: lo que falta se completa solo.
5. El usuario siempre sabe si se le cobró y si puede reintentar.

Lo que se acepta a propósito es una **ventana de consistencia eventual** en las copias de lectura (stock en MongoDB y Elasticsearch, contenido del carrito), porque el checkout valida siempre contra PostgreSQL.

### 3.6 Puntos de falla

La estrategia identifica 14 puntos (F1-F14), con su estado resultante, mitigación, mensaje al usuario y escenario de prueba. Los que tienen prueba automática son F1 (E1), F5 (E2), F6 (E0), F10 (E3), F11 (E4) y F12 (E5). La tabla completa está en la [sección 5 de la estrategia](estrategia-consistencia-checkout.md#5-puntos-de-falla-y-su-mitigación).

Los errores se clasifican así: un error de negocio del procedimiento (sin stock, dirección ajena) responde `400`; una falla de infraestructura (`OperationalError` de PostgreSQL, Redis caído) responde `503`, siempre con "no se realizó ningún cobro".

### 3.7 Comunicación al usuario

En `FormularioCheckout.vue`:

| Situación | Lo que ve el comprador |
|---|---|
| Falla antes de cobrar | Aviso rojo "Tu compra no se completó · No se realizó ningún cobro y tu carrito sigue intacto"; el botón pasa a "Reintentar compra" |
| Se perdió la respuesta | Aviso amarillo de que no se sabe si se completó y de que reintentar es seguro. `apiFetch` (`frontend/app/src/services/api.js`) convierte el error de red en `status 0` / `SIN_CONEXION` |
| Reintento de un pago ya confirmado | "Tu pedido #N ya estaba confirmado; no se cobró dos veces" |
| Pedido confirmado con una copia pendiente | Compra confirmada, más el aviso de que el stock y el carrito pueden tardar unos segundos en actualizarse (`sincronizacion_pendiente`) |
| Buscador caído | Aviso de búsqueda simplificada |

Con `PERMITIR_FALLAS_SIMULADAS=1`, el formulario muestra además el selector "Simular falla (solo desarrollo)", para la demostración.

### 3.8 Panel Sincronización

Pestaña nueva del panel admin, solo para el administrador (`GestionSincronizacion.vue`; el vendedor no la ve, `SidebarAdmin.vue`). Muestra los eventos pendientes, procesados y fallidos con su último error, y tiene botones para procesarlos ya y para volver a encolar los fallidos. La respaldan tres rutas del blueprint `sincronizacion.py`: `GET /api/sincronizacion/eventos`, `POST /api/sincronizacion/procesar` y `POST /api/sincronizacion/reintentar-fallidos`.

Verificado hoy: `GET /api/sincronizacion/eventos?rol_solicitante=administrador` responde **42 procesados, 0 pendientes y 0 fallidos** (14 `stock_mongo`, 14 `stock_elasticsearch`, 11 `limpiar_carrito` y 3 `confirmar_reserva_oferta`). El evento más antiguo que guarda la tabla es del 6 de octubre.

### 3.9 Tablas SQL nuevas

[`database/postgres/migracion_entrega3_consistencia.sql`](../database/postgres/migracion_entrega3_consistencia.sql) (también incluidas en `ddl_tiendaya.sql` para bases nuevas; la migración no toca datos y se puede repetir):

- **`checkout_idempotencia`**: `clave` (PK, hasta 64 caracteres), `id_comprador` (FK a `usuarios`), `id_pedido` (FK a `pedidos`), `referencia_pago`, `creado_en`.
- **`eventos_sincronizacion`**: `id_evento` (`BIGSERIAL`), `tipo` (con `CHECK` sobre los cinco tipos), `payload` (`JSONB`), `id_pedido`, `estado` (`pendiente`, `procesado` o `fallido`), `intentos`, `ultimo_error`, `proximo_intento`, `creado_en`, `procesado_en`. Índices `idx_eventos_pendientes` e `idx_eventos_pedido`.

Los modelos SQLAlchemy correspondientes son `CheckoutIdempotencia` y `EventoSincronizacion` (`backend/app/models.py`).

### 3.10 Archivos

`backend/app/blueprints/checkout.py`, `backend/app/sincronizacion.py`, `backend/app/blueprints/sincronizacion.py`, `backend/app/lua/limpiar_carrito_comprado.lua`, `backend/app/models.py`, `backend/app/config.py` (`OUTBOX_*`, `PERMITIR_FALLAS_SIMULADAS`), `backend/main.py`, `database/postgres/migracion_entrega3_consistencia.sql`, `database/postgres/ddl_tiendaya.sql`, `frontend/app/src/components/publico/FormularioCheckout.vue`, `frontend/app/src/components/publico/Carrito.vue`, `frontend/app/src/services/api.js`, `frontend/app/src/components/admin/GestionSincronizacion.vue`, `frontend/app/src/components/admin/SidebarAdmin.vue`, `frontend/app/src/views/VistaAdmin.vue`, `backend/scripts/prueba_fallas_checkout.py`, `.env.example`.

---

## 4. Pruebas y evidencia

### 4.1 Buscador: `backend/scripts/prueba_buscador.py`

Hace búsquedas reales contra la API. Con `--caida-real` detiene y vuelve a levantar el contenedor de Elasticsearch (B7).

| Caso | Qué verifica | Resultado en la evidencia (2026-10-05) |
|---|---|---|
| B1 Errores de tipeo | `laptp`, `audifnos`, `celulr` encuentran resultados y sugieren la palabra correcta | 106, 50 y 74 resultados; sugiere "laptop", "audifonos", "celular" |
| B2 Sinónimos y raíces | `portatil` → laptops, `auriculares` → audífonos, `mochilas` → mochilas | Correcto (40 mochilas) |
| B3 Relevancia | `celular` (5 primeros de Celulares), `smartphone samsung`, `mochila laptop` | Celulares primero, Samsung primero, mochilas para laptop y no laptops |
| B4 Autocompletado | `iph`, `lapt`, `aufi` | iPhone…, Laptop…, Audífonos… |
| B5 Facetas | `mouse` trae las 4 facetas; Logitech = 20, igual al conteo de la faceta; las demás marcas siguen visibles; las otras facetas se recalculan | Correcto (7 marcas visibles con Logitech elegida) |
| B6 Precio y orden | Rango Q1,000–Q5,000, orden ascendente | 14 resultados, de Q1,029 a Q4,759, en orden |
| B7 Caída real | `503 BUSCADOR_NO_DISPONIBLE`; el respaldo de MongoDB responde; el buscador vuelve al levantarlo | Correcto (respaldo con 105 resultados) |

**Resultado: 21/21 verificaciones correctas** (18 sin `--caida-real`). Se volvió a obtener 21/21 dos veces el 6 de octubre (antes y después de las correcciones) y 18/18 en la verificación final de ese día.

Verificado hoy, solo con búsquedas de lectura: `laptp` da **105** resultados (la evidencia guardada dice 106) y sugiere "laptop"; `audifnos` da 50 y `celulr` 74, iguales a la evidencia. La diferencia de uno en `laptp` y el primer resultado distinto ("Laptop Gamer 16 Pulgadas" en vez de "Laptop triple AAA") indican que el catálogo cambió levemente después de la corrida del 5 de octubre; no se investigó qué producto cambió. La verificación de B1 solo exige que haya resultados y la sugerencia, así que el caso sigue pasando.

### 4.2 Checkout: `backend/scripts/prueba_fallas_checkout.py`

Requiere `PERMITIR_FALLAS_SIMULADAS=1`. Hace compras reales del comprador `maria.torres@email.com` y, en cada escenario, consulta directamente PostgreSQL, Redis, MongoDB y Elasticsearch. Los puntos de falla simulada lanzan una excepción real en ese lugar del flujo: `redis_lectura_carrito`, `postgres_antes_commit`, `redis_post_commit`, `mongo_post_commit` y `elasticsearch_post_commit`.

| Escenario | Qué verifica | Resultado en la evidencia (2026-10-05) |
|---|---|---|
| E0 Camino feliz + reintento con la misma clave | 201, un pedido, stock igual en los tres motores, carrito limpio, eventos procesados; el reintento da `200 repetido` sin descontar otra vez | 10/10 |
| E1 Redis cae al leer el carrito | `503 CARRITO_NO_DISPONIBLE` con "no se realizó ningún cobro"; sin pedido, sin cambio de stock, carrito intacto, sin clave | 6/6 |
| E2 PostgreSQL cae antes del COMMIT, con oferta relámpago | `503 PAGO_NO_CONFIRMADO`; rollback incluida la clave; **compensación**: reserva `activa`, 0 vendidas; el reintento con la misma clave compra (2 vendidas, stock 31 → 29) | 9/9 |
| E3 Redis cae después del COMMIT | `201` con `sincronizacion_pendiente`; lo pagado sigue en el carrito; otra clave → `409 CARRITO_VACIO`; misma clave → `200 repetido`; nunca un segundo pedido | 10/10 |
| E4 MongoDB cae después del COMMIT | MongoDB con stock viejo (37 contra 36) mientras Elasticsearch sí se actualizó; el relevo lo corrige solo | 5/5, convergió en **20 s** (2.º intento) |
| E5 Caída real de Elasticsearch | Buscador `503`; checkout `201`; evento pendiente con `ConnectionError`; MongoDB al día; al levantar el contenedor, el relevo corrige el stock | 5/5, convergió **25 s** después de levantarlo |

**Resultado: 45/45 verificaciones correctas.**

Tiempos de convergencia en las tres corridas registradas (la diferencia depende de en qué momento del ciclo de 15 s del relevo cae el reintento):

| Corrida | E4 (MongoDB) | E5 (Elasticsearch, tras levantarlo) | Fuente |
|---|---|---|---|
| 2026-10-05 | 20 s | 25 s | Evidencia guardada |
| 2026-10-06, antes de las correcciones | 12 s | 31 s | [`hallazgos.md`](hallazgos.md) |
| 2026-10-06, después de las correcciones | 16 s | 15 s | [`hallazgos.md`](hallazgos.md) |

La evidencia guardada sigue siendo la del 5 de octubre: las corridas del 6 no la reemplazaron.

Además de los scripts, el 5 de octubre se hizo un recorrido en el navegador (Edge headless con `playwright-core`) del autocompletado, los resultados con facetas, un checkout con falla de PostgreSQL y reintento, y el panel de Sincronización ([`STACK.md`](STACK.md), bitácora). Ese recorrido no dejó un archivo de evidencia en `docs/evidencia/`.

### 4.3 Cómo reproducir

Con el sistema levantado según el [`README.md`](../README.md) (contenedor de Elasticsearch, script de indexación y migración `migracion_entrega3_consistencia.sql`) y `PERMITIR_FALLAS_SIMULADAS=1` en el `.env` (con el backend reiniciado):

```bash
python backend/scripts/prueba_buscador.py --caida-real          # B1-B7 (detiene y levanta Elasticsearch)
python backend/scripts/prueba_fallas_checkout.py                # E0-E4
python backend/scripts/prueba_fallas_checkout.py --caida-real   # E0-E5
curl "http://127.0.0.1:8000/api/sincronizacion/eventos?rol_solicitante=administrador"
```

En Windows, con el entorno virtual activado (`venv\Scripts\activate`), los mismos comandos funcionan en PowerShell. Las pruebas del checkout crean pedidos reales, y un pedido revertido (E2) deja un hueco en la numeración, que es el comportamiento normal de `SERIAL`.

Verificado hoy: `GET /api/checkout/fallas-simuladas` responde `habilitadas: false`, así que en el entorno actual las fallas simuladas están apagadas; para correr el script hay que activarlas en el `.env`.

---

## 5. NewSQL (ADR-005) y arquitectura actualizada

### 5.1 Evaluación NewSQL para pagos

[ADR-005](decisiones/ADR-005-newsql-pagos.md) es una evaluación documental, contrastada con el código; no se montó un clúster NewSQL. **Conclusión: no migrar.**

- **Migrar solo `pagos`** empeoraría la consistencia: hoy pedido, pago e inventario se confirman en una transacción local, y separarlos los convertiría en una transacción distribuida justo en el registro más sensible.
- **Migrar todo el núcleo transaccional** (por ejemplo a YugabyteDB, el más compatible con el procedimiento en PL/pgSQL) es viable, pero no resuelve un problema actual: el volumen de pagos está muy por debajo de lo que escribe un PostgreSQL, y la contención de la oferta relámpago ya se resolvió en Redis. A cambio exige al menos 3 nodos, más latencia por escritura y manejar reintentos por serialización (`40001`).
- **Cuándo sí convendría**: escritura multirregión activa-activa, disponibilidad sin failover manual con RPO = 0, un volumen de escritura medido que supere a un PostgreSQL escalado, o residencia de datos por país. En ese caso, la clave de idempotencia ya haría seguros los reintentos.

### 5.2 Arquitectura

[`arquitectura.md`](arquitectura.md) agrega al diagrama Mermaid:

- **Elasticsearch** y el blueprint `busqueda.py`, con el respaldo del frontend a `GET /api/productos?q=`.
- Las tablas `checkout_idempotencia` y `eventos_sincronizacion` en PostgreSQL.
- Las escrituras del checkout tras el COMMIT y el **relevo del outbox** hacia Redis, MongoDB y Elasticsearch.
- El panel `sincronizacion.py`.

Las líneas continuas son escrituras en la fuente de verdad; las punteadas, copias con consistencia eventual. El diagrama actual también incluye cambios posteriores a la Entrega 3 (ofertas y fraude ampliado), marcados con su fecha.

---

## 6. Verificación posterior y correcciones (H-001 a H-015)

El 6 de octubre se hizo una verificación completa del sistema: los dos scripts, 158 casos de la API (155 correctos y 3 hallazgos menores), la consistencia entre motores y `npm run build`. Se registró todo en [`hallazgos.md`](hallazgos.md). Las correcciones de código quedaron en el commit `06994dd`.

| ID | Síntoma | Severidad | Estado | Corrección |
|---|---|---|---|---|
| H-001 | La pestaña Historial del admin no cargaba ("data is not iterable") | bloqueante | Corregido (`06994dd`) | `HistorialProducto.vue` recorre todas las páginas del nuevo formato paginado de `GET /api/productos` |
| H-002 | Una página muy alta del buscador respondía `503` y mandaba al respaldo con el motor arriba | menor | Corregido (`06994dd`) | Fuera de la ventana de 10 000 resultados, `200` con `items` vacíos; un `400` de Elasticsearch se responde `400 BUSQUEDA_NO_VALIDA` |
| H-003 | `precio_min=nan` o `precio_max=inf` respondían `503` | menor | Corregido (`06994dd`) | `_decimal` rechaza los no finitos: `400` |
| H-004 | Reintentar el checkout con `id_comprador` como texto daba `409 CLAVE_IDEMPOTENCIA_AJENA` | menor | Corregido (`06994dd`) | `_id_entero` normaliza a entero; valor inválido → `400` |
| H-005 | Los resultados del buscador no muestran los chips de atributos | menor | **Abierto** (decisión del equipo) | Propuesta: devolver `atributos` desde `busqueda_es.py`, o descartarlo |
| H-006 | `docs/guia-funcionalidades.docx` refleja la Entrega 2 | documentación | Corregido (2026-10-08) | Guía regenerada con el estado actual del sistema |
| H-007 | `docs/hola.html` vacío | menor | Corregido (`06994dd`) | Archivo borrado |
| H-008 | `.gitignore` no ignoraba respaldos del `.env` | menor | Corregido (`06994dd`) | Reglas `.env.*` y `!.env.example` |
| H-009 | Discrepancias entre documentación y código (conteos, rutas, diagrama del respaldo, ventanas de consistencia) | documentación | Corregido (`06994dd`) | Cada documento corregido; en ADR-004 solo las cifras, con nota de fecha |
| H-010 | La paginación de `GET /api/productos` repetía y saltaba productos (1015 ítems, 1001 distintos) | menor | Corregido (`06994dd`) | Desempate por `_id` |
| H-011 | El Historial solo mostraba los 50 eventos más recientes (de 1016) | menor | Corregido (`06994dd`) | `GET /api/historial` paginado, con `total` y `total_paginas` |
| H-012 | Un número de página enorme respondía `500` en historial y catálogo | menor | Corregido (`06994dd`) | Tope del `$skip` en historial; el catálogo devuelve lista vacía si el salto pasa el total |
| H-013 | `Paginacion.vue` ignora el `total_paginas` del buscador | menor | **Abierto** (latente) | Propuesta: prop opcional `totalPaginas`. No se manifiesta con 1015 productos |
| H-014 | En el Historial, "Siguiente" paginaba con filtros que no se habían aplicado | menor | Corregido (`06994dd`) | Pagina con `filtrosAplicados` y solo avanza si la carga fue correcta |
| H-015 | Stock de PROD-0004 y PROD-0014 desfasado en una unidad (anterior al outbox) | menor | Corregido en la base local (ajuste de datos, sin código) | Se copió el stock desde PostgreSQL. Verificado hoy: 0 desfases en los 1015 productos |

Re-verificación del 6 de octubre después de las correcciones: buscador 21/21, fallas del checkout 45/45, outbox sin pendientes ni fallidos, 1015 productos en MongoDB y en Elasticsearch.

**Quedan abiertos dos**: H-005 y H-013 (H-006 se cerró el 2026-10-08 al regenerar la guía) (estado comprobado hoy en `hallazgos.md`). Hoy se confirmó además en el código que siguen igual: los resultados de `GET /api/busqueda` no traen `atributos` (H-005) y `ResultadosBusqueda.vue` sigue pasando solo `total` a `Paginacion.vue` (H-013).

---

## 7. Cronología del trabajo (según `git log`)

Solo lo de la Entrega 3. El autor es el que registra git; la distribución real de responsabilidades la completa el equipo en el informe (ver sección 9).

| Fecha | Commit | Autor en git | Qué |
|---|---|---|---|
| 2026-10-05 | `997f1e2` "elastic search y checkout" | Diego Rueda | El grueso de la entrega: 44 archivos, unas 3600 líneas agregadas. Buscador (Elasticsearch en `docker-compose.yml`, mapping, `busqueda_es.py`, `busqueda.py`, script de indexación, autocompletado y página de resultados), estrategia de consistencia (`checkout.py` reescrito, `sincronizacion.py`, outbox, idempotencia, Lua `limpiar_carrito_comprado.lua`, migración SQL, panel Sincronización, fallas simuladas), los dos scripts de prueba con su evidencia, ADR-004, ADR-005, la estrategia, el informe y la actualización de README, STACK, arquitectura y agentes |
| 2026-10-06 | `07e8bde` "Create guia-funcionalidades.docx" y merge `785789d` (PR #9) | Fatiunis | Se agrega la guía en Word por funcionalidad (refleja la Entrega 2; ver H-006) |
| 2026-10-06 | `06994dd` "Correcciones post-pruebas Entrega 3…" | Fatiunis | 22 archivos. Correcciones de H-001 a H-004, H-007, H-008 y H-010 a H-014; `docs/hallazgos.md` nuevo; documentos corregidos contra el código (H-009); agentes de pruebas y de documentación. Verificado: buscador 21/21, fallas del checkout 45/45, regresión de la API y build |

El commit anterior, `ff47d9b` (2026-10-01, "cambios fatima"), solo actualiza documentación de la Entrega 2 (ADR-003, informe de la Entrega 2, README y STACK) y no forma parte de esta entrega.

---

## 8. Mapa de archivos de la Entrega 3

| Área | Archivos nuevos | Archivos modificados |
|---|---|---|
| Backend | `backend/app/busqueda_es.py`, `backend/app/sincronizacion.py`, `backend/app/blueprints/busqueda.py`, `backend/app/blueprints/sincronizacion.py`, `backend/app/lua/limpiar_carrito_comprado.lua` | `backend/app/blueprints/checkout.py`, `backend/app/blueprints/catalogo.py`, `backend/app/blueprints/historial.py` (correcciones), `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/extensions.py`, `backend/app/models.py`, `backend/main.py`, `requirements.txt`, `.env.example` |
| Base de datos | `database/elasticsearch/productos_indice.json`, `database/migrations/indexar_productos_elasticsearch.py`, `database/postgres/migracion_entrega3_consistencia.sql` | `database/postgres/ddl_tiendaya.sql`, `docker-compose.yml` |
| Frontend | `frontend/app/src/components/publico/ResultadosBusqueda.vue`, `frontend/app/src/components/admin/GestionSincronizacion.vue` | `NavPublica.vue`, `FormularioCheckout.vue`, `Carrito.vue`, `SidebarAdmin.vue`, `HistorialProducto.vue` (correcciones), `services/api.js`, `views/VistaAdmin.vue`, `views/VistaPublica.vue` (todos bajo `frontend/app/src/`) |
| Scripts de prueba | `backend/scripts/prueba_buscador.py`, `backend/scripts/prueba_fallas_checkout.py` | — |
| Documentación | `docs/estrategia-consistencia-checkout.md`, `docs/decisiones/ADR-004-motor-de-busqueda.md`, `docs/decisiones/ADR-005-newsql-pagos.md`, `docs/informe-entrega-3.md`, `docs/evidencia/prueba_buscador.txt`, `docs/evidencia/prueba_fallas_checkout.txt`, `docs/hallazgos.md`, este reporte | `README.md`, `docs/STACK.md`, `docs/arquitectura.md`, `frontend/app/README.md` |
| Repositorio | `.claude/agents/documentacion.md` | `.gitignore`, `.claude/agents/backend.md`, `database.md`, `frontend.md`, `tester.md`; se borró `docs/hola.html` |

---

## 9. Limitaciones conocidas y pendientes

### Pendientes del equipo para cerrar la entrega

- **Distribución de responsabilidades**: la sección 1 del [informe](informe-entrega-3.md) tiene las tres filas con ✏️ sin llenar. El enunciado exige indicarla en cada entrega (sección 5.1).
- **Marca "Borrador"**: el informe sigue diciendo "Borrador. Las secciones marcadas con ✏️ las completa el equipo". Hay que quitarla al completar la sección 1.
- **Guía en Word** ([H-006](hallazgos.md)): se regeneró el 2026-10-08 (`docs/guia-funcionalidades.docx`) con el buscador, el outbox, la idempotencia, el panel Sincronización, las fallas simuladas y el resto del estado actual. El informe también está en Word: `docs/informe-entrega-3.docx`.
- **H-005** (atributos en los resultados de búsqueda) y **H-013** (`Paginacion.vue` y `total_paginas`) esperan una decisión del equipo. Ninguno afecta lo que se evalúa.

### Limitaciones aceptadas

- **Sin autenticación en el servidor**: el rol y el `id_usuario` los manda el cliente; Elasticsearch y Redis corren sin autenticación. El control de acceso es requisito de la entrega final.
- **El relevo es un hilo dentro de Flask**: si el backend está detenido, nadie reintenta (los eventos quedan guardados y se procesan al volver). Con varias instancias funcionaría igual gracias a `SKIP LOCKED`, pero lo natural sería un proceso aparte.
- **Un motor caído más de unos 25 minutos** deja sus eventos en `fallido` (10 intentos); hay que volver a encolarlos desde el panel. Nunca afecta pedidos, pagos ni inventario.
- **La clave de idempotencia es opcional en la API**: el frontend siempre la manda, pero un cliente que no la mande no queda protegido.
- **El precio editado en el admin solo vive en MongoDB y Elasticsearch**; el checkout cobra el de PostgreSQL (limitación desde la Entrega 1).
- **Algunas categorías no tienen el atributo `marca`** (por ejemplo, Laptops), así que en esas búsquedas no aparece esa faceta.
- **Sinónimos y plurales escritos a mano** en el JSON del índice; para agregar uno hay que reindexar (sin cortar el servicio).
- **La prueba de falla crea pedidos reales** y deja huecos en la numeración de `pedidos`.
- **ADR-005 es documental**: no hay mediciones propias de un motor NewSQL.

---

## 10. Nota: trabajo posterior a la Entrega 3

Después de la Entrega 3 se hicieron cambios que **no forman parte de lo entregado en ella** (y no son de la Entrega 4). Se listan solo para que no se confundan con esta entrega:

- **Ofertas flash en el sitio público y en el panel del vendedor** (commit `4aabb9c`, 2026-10-07): listado público `GET /api/ofertas`, botón "Ofertas", página y franja de ofertas, pestaña "Ofertas flash" del vendedor y "Mis ventas" para el administrador. Ver "Novedades después de la Entrega 3" en el [`README.md`](../README.md).
- **Carrito sin expiración por defecto** (mismo commit): `CARRITO_TTL_SEGUNDOS=0` por defecto, decidido en [ADR-006](decisiones/ADR-006-carrito-sin-expiracion-por-defecto.md), que reemplaza ese punto de ADR-003 (antecedente en H-016).
- **Detección de fraude ampliada** (commit `faa62fa`, 2026-10-08): cuatro patrones nuevos sobre el grafo de Neo4j, sin cambiar la consulta de la Entrega 2. Ver [ADR-007](decisiones/ADR-007-deteccion-fraude-ampliada.md) y [`deteccion-fraude-ampliada.md`](deteccion-fraude-ampliada.md).

Los hallazgos H-016 a H-024 de [`hallazgos.md`](hallazgos.md) corresponden a ese trabajo posterior.
