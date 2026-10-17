# Guion de la demostración en vivo — Entrega 3

TiendaYa · Bases de Datos 2 · preparado el 8 de octubre de 2026

Este guion sirve para presentar en vivo lo que se construyó en la Entrega 3: el buscador con Elasticsearch, la consistencia del checkout (idempotencia, outbox y compensación), la prueba de falla simulada, la evaluación NewSQL y la arquitectura. Dura unos 10-15 minutos. El detalle técnico de cada tema está en el [informe de la Entrega 3](informe-entrega-3.md), la [estrategia de consistencia del checkout](estrategia-consistencia-checkout.md), [ADR-004](decisiones/ADR-004-motor-de-busqueda.md), [ADR-005](decisiones/ADR-005-newsql-pagos.md) y la [arquitectura](arquitectura.md).

Lo marcado **(verificado el 2026-10-08)** se comprobó ese día contra el sistema que estaba corriendo, solo con consultas de lectura: no se hizo ningún checkout ni se detuvo ningún contenedor. Los resultados de las compras y de las fallas no se volvieron a ejecutar para este guion: lo que se espera ver sale del código (`checkout.py`, `FormularioCheckout.vue`, `sincronizacion.py`) y de la evidencia guardada del 5 de octubre ([`prueba_fallas_checkout.txt`](evidencia/prueba_fallas_checkout.txt), 45/45). Conviene ensayar el guion completo una vez antes de presentar.

---

## 1. Dónde está cada aplicación

| Aplicación | Dirección | Para qué sirve en la demo | Credenciales |
|---|---|---|---|
| Sitio público (Vite) | `http://127.0.0.1:5173`, o `http://127.0.0.1:5300` si Windows reservó el 5173 (ver el paso 7 del [README](../README.md#7-levantar-el-frontend)) | Buscador, carrito y checkout con el selector "Simular falla (solo desarrollo)" | Comprador `maria.torres@email.com` / `Tiendaya123!` |
| Panel admin | La misma dirección + `/admin/sincronizacion` | Pestaña **Sincronización**: eventos del outbox `pendiente`, `procesado` y `fallido`, con su último error | `admin@tiendaya.com` / `Tiendaya123!` |
| API Flask | `http://127.0.0.1:8000` | Mostrar las respuestas crudas (ver abajo) | Sin autenticación; las rutas de admin piden `rol_solicitante=administrador` |
| Elasticsearch | `http://localhost:9200` | Mostrar el índice y el mapping deliberado | Sin autenticación (`xpack.security.enabled=false`) |
| Neo4j Browser | `http://localhost:7474` (bolt en `7687`) | No es parte de la Entrega 3; solo si preguntan por el fraude de la Entrega 2 | `neo4j` / `tiendaya123` |
| PostgreSQL | `localhost:5432`, base `tiendaya_db` | Consultar pedidos y la tabla del outbox | Usuario `postgres` y la contraseña de tu `.env` |
| MongoDB | `mongodb://localhost:27017/`, base `tiendaya_nosql` | Ver el stock copiado en el documento del producto | Sin autenticación |
| Redis | `localhost:6379` (Docker) | Ver el carrito de María (`carrito:<id_usuario>`) | Sin autenticación |

Los puertos de Redis, Neo4j y Elasticsearch salen de `docker-compose.yml`, y los de PostgreSQL y MongoDB, de `.env.example`.

**Endpoints que conviene tener a mano:**

| Endpoint | Qué muestra |
|---|---|
| `GET /api/busqueda?q=laptp` | Resultados, `sugerencia`, `facetas` y `motor` (`elasticsearch`) |
| `GET /api/busqueda/autocompletar?q=iph` | Hasta 8 sugerencias del autocompletado |
| `GET /api/productos?q=celular` | La búsqueda vieja (`$text` de MongoDB), que también es el respaldo del buscador |
| `GET /api/checkout/fallas-simuladas` | Si las fallas simuladas están habilitadas (`habilitadas`) y la lista de puntos |
| `GET /api/sincronizacion/eventos?rol_solicitante=administrador` | El outbox: `resumen` por estado y la lista de `eventos` (acepta `&estado=pendiente`) |

**En Elasticsearch:** `http://localhost:9200/_cat/indices?v` (el índice `productos_v<fecha>`), `http://localhost:9200/_cat/aliases?v` (el alias `productos`) y `http://localhost:9200/productos/_mapping` (el mapping). Se abren directo en el navegador.

**Consultas rápidas a cada base** (en Windows, `psql` y `mongosh` no siempre están en el PATH; por eso va también la variante en Python, con el `venv` activado):

```bash
# PostgreSQL: últimos pedidos y estado del outbox
psql -U postgres -d tiendaya_db -c "SELECT estado, count(*) FROM eventos_sincronizacion GROUP BY estado;"
python -c "import psycopg2, os; from dotenv import load_dotenv; load_dotenv(); c=psycopg2.connect(host=os.getenv('PG_HOST'), port=os.getenv('PG_PORT'), dbname=os.getenv('PG_DBNAME'), user=os.getenv('PG_USER'), password=os.getenv('PG_PASSWORD')); cur=c.cursor(); cur.execute('SELECT estado, count(*) FROM eventos_sincronizacion GROUP BY estado'); print(cur.fetchall())"

# MongoDB: stock de un producto en el catálogo (cambia el SKU)
mongosh tiendaya_nosql --eval "db.productos.findOne({sku: 'SKU-AQUI'}, {nombre: 1, stock_disponible: 1})"
python -c "from pymongo import MongoClient; print(MongoClient('mongodb://localhost:27017/')['tiendaya_nosql'].productos.find_one({'sku': 'SKU-AQUI'}, {'nombre': 1, 'stock_disponible': 1}))"

# Redis: carrito de María (id_usuario 12 en la base de Fátima; confírmalo en la tuya)
docker compose exec redis redis-cli HGETALL carrito:12
```

En PowerShell, `curl` es un alias de otro comando: usa `curl.exe` con las mismas opciones, o abre las URL de tipo `GET` directo en el navegador.

---

## 2. Preparación antes de presentar

Hacerla con al menos 10 minutos de margen. Cada punto dice cómo verificarlo y qué hacer si no está.

| # | Qué | Cómo verificarlo | Si no está |
|---|---|---|---|
| 1 | Docker Desktop abierto | El ícono de la ballena dice "Engine running" | Abrirlo y esperar a que arranque |
| 2 | Contenedores arriba | `docker compose ps`: `redis`, `neo4j` y `elasticsearch` en `Up` | `docker compose up -d` desde la raíz del repo |
| 3 | Elasticsearch `healthy` | `docker compose ps` lo muestra `(healthy)`; `curl http://localhost:9200/_cluster/health` responde `"status":"green"` (o `yellow`) | Esperar 20-40 s después de levantarlo |
| 4 | Índice cargado | `curl "http://localhost:9200/_cat/indices?v"`: `productos_v<fecha>` con `docs.count` igual a los productos de MongoDB | `python database/migrations/indexar_productos_elasticsearch.py` |
| 5 | Migración de la Entrega 3 aplicada | `GET /api/sincronizacion/eventos?rol_solicitante=administrador` responde con `resumen` (y no un error de tabla inexistente) | `psql -U postgres -d tiendaya_db -f database/postgres/migracion_entrega3_consistencia.sql` (o el atajo en Python del paso 3 del README) |
| 6 | `PERMITIR_FALLAS_SIMULADAS=1` en el `.env` y backend reiniciado | `curl http://127.0.0.1:8000/api/checkout/fallas-simuladas` responde `"habilitadas": true` y 5 puntos | Editar el `.env`, detener el backend (Ctrl+C) y volver a lanzar `python backend/main.py`. **Sin reiniciar, el cambio no se aplica** |
| 7 | Backend arriba, con el relevo | La consola mostró `[relevo] Relevo de eventos de sincronización activo` | `python backend/main.py` |
| 8 | Vite arriba | Abrir el sitio; carga el catálogo | `npm run dev` en `frontend/app/` (o `npm run dev -- --port 5300` si falla con `listen EACCES`) |
| 9 | Outbox limpio | `resumen` con `"pendiente": 0` y `"fallido": 0` | En el panel → Sincronización: "Procesar pendientes ahora" o "Volver a encolar fallidos" |
| 10 | Carrito de María con un producto | Entrar como María: el carrito muestra 1 producto | Buscar `mouse`, abrir un producto con stock y agregarlo |
| 11 | Pestañas abiertas | Ver la lista de abajo | — |

Comprobación rápida de todo junto (Git Bash o macOS/Linux; en PowerShell, `curl.exe`):

```bash
docker compose ps
curl -s http://localhost:9200/_cluster/health
curl -s "http://localhost:9200/_cat/indices?v"
curl -s http://127.0.0.1:8000/api/checkout/fallas-simuladas
curl -s "http://127.0.0.1:8000/api/sincronizacion/eventos?rol_solicitante=administrador&limite=1"
```

**Pestañas del navegador, en este orden:**

1. `docs/arquitectura.md` en GitHub (renderiza el diagrama Mermaid).
2. El sitio público con la sesión de María.
3. El panel admin, `/admin/sincronizacion`, con la sesión del administrador. La sesión se guarda en el `localStorage` del navegador, que es uno solo por dirección: si María y el administrador usan la misma, la segunda sesión reemplaza a la primera. Para tener las dos a la vez, abrir el admin en una ventana de incógnito o en la otra dirección del mismo servidor (`http://localhost:5300` en vez de `http://127.0.0.1:5300`). (No se comprobó en el navegador; ensayarlo.)
4. `http://localhost:9200/productos/_mapping`.
5. Una terminal en la raíz del repo, con el `venv` activado.

**Estado verificado el 2026-10-08** en la máquina de Fátima: los tres contenedores `Up` y Elasticsearch `(healthy)`, con estado `green`; índice `productos_v20261006181736` con 1015 documentos y el alias `productos` apuntando a él; las tablas `checkout_idempotencia` y `eventos_sincronizacion` existen; el outbox con 42 eventos `procesado` y ninguno `pendiente` ni `fallido`; backend en `:8000` y Vite en `:5300` (el `:5173` no respondía). **Faltaba** para la demo: `PERMITIR_FALLAS_SIMULADAS` estaba en `0` (la API respondía `"habilitadas": false`) y el carrito de María (`carrito:12`) estaba vacío.

---

## 3. Guion

Total estimado: unos 14 minutos. La asignación de bloques la decide el equipo.

| Bloque | Tiempo | Presenta |
|---|---|---|
| 3.1 Introducción y arquitectura | 1,5 min | ✏️ |
| 3.2 Buscador | 4 min | ✏️ |
| 3.3 Checkout feliz y reintento con la misma clave | 2 min | ✏️ |
| 3.4 Fallas simuladas (E2 y E4) | 3 min | ✏️ |
| 3.5 Caída real de Elasticsearch | 2,5 min | ✏️ |
| 3.6 NewSQL | 1 min | ✏️ |
| 3.7 Cierre | 0,5 min | ✏️ |

Presentadores: Diego Rueda, Marcos Pineda y Fátima Ramazzini.

### 3.1 Introducción y arquitectura (1,5 min) — ✏️

- **Qué hacer:** abrir `docs/arquitectura.md` en GitHub y señalar Elasticsearch, el relevo del outbox y las tablas `checkout_idempotencia` y `eventos_sincronizacion` en PostgreSQL.
- **Qué decir:** "La Entrega 3 tenía dos temas: recuperar información y mantener la consistencia cuando una operación toca varios motores. Agregamos Elasticsearch como buscador, que es una copia de solo lectura del catálogo de MongoDB, y rediseñamos el checkout, que ahora toca cuatro motores. Las líneas continuas son escrituras en la fuente de verdad; las punteadas, copias que pueden quedar atrasadas unos segundos y que el relevo del outbox corrige solo."
- **Qué debe verse:** el diagrama con PostgreSQL, MongoDB, Redis, Neo4j y Elasticsearch, y las flechas punteadas del checkout y del relevo hacia Redis, MongoDB y Elasticsearch.

### 3.2 Buscador (4 min) — ✏️

Todo en el sitio público, en la barra "Buscar productos...". Los números son los del 2026-10-08; si cambia el catálogo, pueden variar un poco.

1. **El problema de antes.** Abrir `http://127.0.0.1:8000/api/productos?q=celular` (la búsqueda vieja, `$text` de MongoDB).
   - **Qué decir:** "Así buscaba TiendaYa antes: `celular` traía solo tablets que dicen 'Wi-Fi + Celular' en el nombre, y cualquier error de tipeo daba cero resultados."
   - **Qué debe verse:** `"total": 14`, todas tablets "Wi-Fi + Celular" **(verificado el 2026-10-08)**. Con `?q=laptp`, `"total": 0` **(verificado el 2026-10-08)**.
2. **Errores de tipeo.** Buscar `laptp` y presionar Enter; luego `audifnos` y `celulr`.
   - **Qué decir:** "Elasticsearch tolera errores con coincidencia aproximada (`fuzziness: AUTO`) y, además, nos propone la palabra correcta."
   - **Qué debe verse:** `laptp` → 105 resultados, todos laptops primero, y arriba "¿Quisiste decir **laptop**?"; `audifnos` → 50 audífonos y "¿Quisiste decir audifonos?"; `celulr` → 74 resultados, los primeros iPhone de la categoría Celulares, y "¿Quisiste decir celular?" **(verificado el 2026-10-08 por la API)**. La evidencia del 5 de octubre dice 106 para `laptp`; hoy hay un producto de prueba menos en el índice.
3. **Sinónimos.** Buscar `portatil` y luego `auriculares`.
   - **Qué decir:** "Ninguna laptop dice 'portátil' en el nombre. Los sinónimos se aplican solo al buscar, así que no hay que reindexar para agregar uno."
   - **Qué debe verse:** `portatil` → 105 laptops, sin "¿Quisiste decir…?"; `auriculares` → 50 audífonos **(verificado el 2026-10-08)**.
4. **Relevancia: `celular` ahora.** Buscar `celular`.
   - **Qué debe verse:** 74 resultados, los primeros de la categoría Celulares (iPhone 13, Pixel 8a, Galaxy S24), y en la faceta Categoría "Celulares 60" y "Tablets 14" **(verificado el 2026-10-08)**. Antes eran 14 tablets y ningún celular.
5. **Autocompletado.** Escribir despacio `iph` y luego `lapt`, sin presionar Enter. Moverse con ↑/↓.
   - **Qué decir:** "El autocompletado usa un subcampo con *edge n-grams*: el índice ya guarda los prefijos de cada palabra."
   - **Qué debe verse:** una lista desplegable de hasta 8 productos: `iph` → "Apple iPhone 15 256GB Grafito", "Apple iPhone 13 256GB Blanco"…; `lapt` → "Laptop Gamer 16 Pulgadas", "Laptop Lenovo Legion Pro 5" y también "Mochila para Laptop…" **(verificado el 2026-10-08 por la API)**.
6. **Facetas disyuntivas.** Buscar `mouse`; en la faceta Marca, elegir **Logitech**.
   - **Qué decir:** "Las facetas son agregaciones del motor. Son disyuntivas: cada una se calcula con los filtros de las demás, así que elegir Logitech no esconde las otras marcas y puedo cambiar de marca con un clic."
   - **Qué debe verse:** `mouse` → 40 resultados, con las facetas Categoría (Mouse 40), Marca (Logitech 20, Genius 6, Redragon 4, Apple 3, Microsoft 3, Glorious 2, Razer 2), Precio y Tienda. Con Logitech: 20 resultados, igual al conteo de la faceta; la faceta Marca sigue mostrando las 7 marcas, y la de Precio se recalcula (Menos de Q100: 2, Q100 a Q500: 7, Q500 a Q1,000: 4, Q1,000 a Q5,000: 7) **(verificado el 2026-10-08 por la API)**.
7. **Rango de precio.** Sin quitar Logitech, elegir "Q1,000 a Q5,000" y ordenar por "Precio: menor a mayor".
   - **Qué debe verse:** 7 resultados ordenados de menor a mayor, de Q1,289 a Q1,409 **(verificado el 2026-10-08 por la API)**. La evidencia del 5 de octubre usa `laptop` en el mismo rango: 14 resultados, de Q1,029 a Q4,759 (igual el 2026-10-08).
8. **El mapping.** Abrir la pestaña `http://localhost:9200/productos/_mapping`.
   - **Qué decir:** "El mapping está hecho a mano y con `dynamic: strict`: un campo que no está declarado se rechaza. `nombre` usa un analizador en español sin acentos y tiene tres subcampos: autocompletado, orden y sugerencia. Los atributos, que varían por categoría, van en un solo campo `flattened` para no crear más de cien campos, y el precio es `scaled_float`."
   - **Qué debe verse:** `"dynamic": "strict"`, `nombre` con `es_texto` / `es_texto_busqueda` y los subcampos `autocompletado`, `orden` y `sugerencia`; `atributos` de tipo `flattened`; `precio_base` de tipo `scaled_float`; `marca` de tipo `keyword` **(verificado el 2026-10-08)**.

### 3.3 Checkout feliz y reintento con la misma clave (2 min) — ✏️

1. **Compra normal desde el sitio.** Como María, abrir el carrito (ya tiene un producto), ir a "Finalizar compra", dejar "Sin falla" en **Simular falla (solo desarrollo)** y presionar **Confirmar compra**.
   - **Qué decir:** "En una sola transacción de PostgreSQL se guardan la clave de idempotencia, el pedido con su pago e inventario, y los eventos del outbox. Después del COMMIT esos eventos se ejecutan al instante: limpiar el carrito y copiar el stock a MongoDB y a Elasticsearch."
   - **Qué debe verse:** el aviso "Compra confirmada · Pedido #N · Referencia TY-…", el resumen de la compra con "Dejar reseña" y el carrito vacío. En el panel → Sincronización, los eventos nuevos de ese pedido en `procesado`, con 1 intento.
2. **Reintento con la misma clave.** El sitio cambia de clave después de una compra confirmada, así que este caso se muestra desde la terminal, como si el cliente repitiera la petición porque se perdió la respuesta. Antes, agregar otra vez un producto al carrito de María. Después, mandar **dos veces** la misma petición (los ID son los de la base de Fátima: confirma los tuyos con `GET /api/usuarios/12/direcciones`):

   ```bash
   # Git Bash o macOS/Linux
   curl -s -X POST http://127.0.0.1:8000/api/checkout -H "Content-Type: application/json" -d '{"id_comprador": 12, "id_direccion": 3, "metodo_pago": "tarjeta_credito", "clave_idempotencia": "demo-entrega3-0001"}'
   ```

   ```powershell
   # PowerShell
   $body = '{"id_comprador": 12, "id_direccion": 3, "metodo_pago": "tarjeta_credito", "clave_idempotencia": "demo-entrega3-0001"}'
   Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/checkout -ContentType "application/json" -Body $body
   ```

   Si se ensaya antes, usar otra clave el día de la demo (por ejemplo `demo-entrega3-0002`): la que ya se usó responde `repetido` desde la primera vez.
   - **Qué decir:** "La segunda petición es idéntica. El backend encuentra la clave en `checkout_idempotencia` y devuelve el mismo pedido sin cobrar de nuevo. Es el caso más peligroso de un pago: el cliente no sabe si se le cobró y vuelve a intentar."
   - **Qué debe verse:** la primera, `201` con `id_pedido` y `referencia_pago`; la segunda, `200` con `"repetido": true`, el **mismo** `id_pedido` y `"mensaje": "Este pedido ya se había confirmado; no se volvió a cobrar."`. En "Mi cuenta" → "Mis pedidos" de María aparece un solo pedido nuevo. (Respuesta tomada del código de `checkout.py` y del escenario E0 de la evidencia; no se ejecutó el 2026-10-08.)

### 3.4 Fallas simuladas en vivo (3 min) — ✏️

Las opciones del selector **Simular falla (solo desarrollo)** son, textualmente (de `PUNTOS_DE_FALLA` en `backend/app/blueprints/checkout.py`):

| Opción del selector | Punto | Escenario |
|---|---|---|
| Sin falla | — | — |
| Redis no responde al leer el carrito (antes de tocar nada). | `redis_lectura_carrito` | E1 |
| PostgreSQL se cae después de ejecutar el procedimiento y antes del COMMIT. | `postgres_antes_commit` | E2 |
| Redis no responde después de confirmar el pedido (cerrar reservas y limpiar el carrito). | `redis_post_commit` | E3 |
| MongoDB no responde al copiar el stock después de confirmar el pedido. | `mongo_post_commit` | E4 |
| Elasticsearch no responde al copiar el stock después de confirmar el pedido. | `elasticsearch_post_commit` | — |

Cada opción lanza una excepción real en ese punto del flujo. El selector solo aparece si `GET /api/checkout/fallas-simuladas` responde `"habilitadas": true`.

**E2: PostgreSQL cae antes del COMMIT.**

1. Agregar un producto al carrito de María (si quedó vacío tras el bloque anterior, recargar la página primero). Ir a "Finalizar compra", elegir "PostgreSQL se cae después de ejecutar el procedimiento y antes del COMMIT." y presionar **Confirmar compra**.
   - **Qué decir:** "El procedimiento ya descontó el inventario dentro de la transacción, pero la conexión se cae antes del COMMIT. PostgreSQL hace rollback de todo, incluida la clave de idempotencia, y si había una reserva de oferta relámpago se devuelve al cupo: eso es la compensación."
   - **Qué debe verse:** un aviso rojo con el título **"Tu compra no se completó"** y el texto "No pudimos confirmar tu pago. No se realizó ningún cobro y tu carrito sigue intacto; intenta de nuevo."; el botón cambia a **"Reintentar compra"**; el carrito sigue con su producto y en "Mis pedidos" no hay pedido nuevo.
2. Volver a elegir **"Sin falla"** (el selector conserva la opción anterior; si no se cambia, la falla se repite) y presionar **Reintentar compra**.
   - **Qué decir:** "El reintento usa la misma clave de idempotencia. Como el intento anterior se revirtió entero, la clave estaba libre y ahora sí compra, una sola vez."
   - **Qué debe verse:** "Compra confirmada · Pedido #N · Referencia TY-…". Un solo pedido nuevo. El número de pedido puede saltarse uno: el intento revertido consumió su número de la secuencia (`SERIAL`), y eso es normal.
   - **Opcional, si hay tiempo:** hacer E2 con una línea "Oferta relámpago" en el carrito para mostrar que la reserva vuelve al cupo. La reserva dura solo 60 s (`RESERVA_OFERTA_TTL_SEGUNDOS`), así que hay que hacerlo rápido.

**E4: MongoDB cae después del COMMIT.**

1. Agregar un producto al carrito, elegir "MongoDB no responde al copiar el stock después de confirmar el pedido." y confirmar.
   - **Qué decir:** "Ahora el pedido sí se confirma: después del COMMIT es definitivo y no se deshace porque falló una copia. Lo que falló queda como evento pendiente en el outbox."
   - **Qué debe verse:** "Compra confirmada · Pedido #N…" y, además, el aviso "Tu pedido está confirmado. El stock del catálogo y tu carrito pueden tardar unos segundos en actualizarse.".
2. Cambiar a la pestaña del panel admin → **Sincronización** (se refresca sola cada 5 s).
   - **Qué decir:** "El relevo es un hilo del backend que cada 15 s reintenta los eventos pendientes, con espera creciente. Copiar el stock es idempotente, porque fija el valor de PostgreSQL en vez de restar, así que repetirlo no hace daño."
   - **Qué debe verse:** el evento "Copiar stock a MongoDB" de ese pedido en `pendiente`, con 1 intento y el último error `FallaSimulada: Falla simulada (mongo_post_commit): el motor no respondió`. Entre 5 y 20 s después pasa a `procesado`, con 2 intentos; el error se conserva para mostrar por qué falló el primero. En la evidencia tardó 20 s. Si se quiere acelerar, el botón **"Procesar pendientes ahora"** lo procesa en el acto.

### 3.5 Caída real de Elasticsearch (2,5 min) — ✏️

Aquí no se simula nada: se detiene el contenedor.

1. En la terminal: `docker compose stop elasticsearch`.
2. En el sitio, buscar `laptop` y presionar Enter.
   - **Qué decir:** "El backend responde `503 BUSCADOR_NO_DISPONIBLE` y el frontend repite la búsqueda contra el índice de texto de MongoDB. El sitio sigue funcionando, con menos funciones."
   - **Qué debe verse:** el aviso amarillo "El buscador avanzado no está disponible en este momento. Te mostramos una búsqueda simplificada: sin filtros por categoría o marca y sin corrección de errores de escritura.", resultados de laptops (104 con la búsqueda de MongoDB, **verificado el 2026-10-08** con `GET /api/productos?q=laptop`), sin facetas ni selector de orden. El autocompletado no muestra nada.
3. Agregar un producto al carrito y comprar con "Sin falla".
   - **Qué decir:** "El checkout no depende del buscador: el pago se decide solo en PostgreSQL. La copia del stock a Elasticsearch queda pendiente."
   - **Qué debe verse:** la compra confirmada, con el aviso de que el stock puede tardar unos segundos en actualizarse. En Sincronización, el evento "Copiar stock a Elasticsearch" de ese pedido en `pendiente`, con un `ConnectionError` como último error (así quedó en la evidencia de E5).
4. En la terminal: `docker compose start elasticsearch`. Esperar a que vuelva (20-40 s; `docker compose ps` lo muestra `healthy`).
   - **Qué debe verse:** el evento pasa a `procesado` en el siguiente ciclo del relevo (en la evidencia, 25 s después de levantarlo). Buscar `laptp` otra vez: vuelven las facetas y "¿Quisiste decir laptop?".

### 3.6 NewSQL (1 min) — ✏️

- **Qué hacer:** mostrar [ADR-005](decisiones/ADR-005-newsql-pagos.md), sección "Decisión".
- **Qué decir (la conclusión en tres frases):** "Evaluamos mover los pagos a un motor NewSQL y decidimos no migrar. Mover solo `pagos` empeoraría la consistencia, porque hoy pedido, pago e inventario se confirman en una sola transacción local y separarlos crearía una transacción distribuida justo en el dato más sensible. Mover todo el núcleo transaccional, por ejemplo a YugabyteDB, es viable, pero cuesta al menos 3 nodos y más latencia por escritura, y solo se justificaría con escritura multirregión, disponibilidad sin failover manual con RPO = 0, un volumen de escritura medido que supere a PostgreSQL o residencia de datos por país."

### 3.7 Cierre (0,5 min) — ✏️

- **Qué decir:** "En resumen: el buscador tolera errores, entiende sinónimos, autocompleta y filtra con facetas, y si se cae, el sitio sigue buscando. El checkout nunca cobra dos veces, nunca sobrevende y siempre le dice al comprador si se le cobró. Todo está respaldado por dos scripts que verifican el estado real de los motores: 21 de 21 en el buscador y 45 de 45 en el checkout."

---

## 4. Plan B

| Si pasa esto | Hacer esto |
|---|---|
| Elasticsearch tarda en volver después del `start` | Seguir con el bloque siguiente y volver al final a mostrar el evento `procesado`. Si no vuelve, mostrar la evidencia (abajo) |
| Vite no arranca: `listen EACCES` en el 5173 | `npm run dev -- --port 5300` en `frontend/app/` (Windows reservó ese puerto, ver el paso 7 del README) |
| El backend se cae al guardar un archivo, con `OSError: [WinError 10038]` | Volver a lanzar `python backend/main.py` ([H-019](hallazgos.md)). No editar archivos del backend durante la demo |
| No aparece el selector "Simular falla" | Revisar `PERMITIR_FALLAS_SIMULADAS=1` en el `.env`, reiniciar el backend y recargar la página |
| Neo4j lento o caído | No afecta la Entrega 3: Neo4j no participa del checkout ni del buscador |
| Algo no responde como se espera | Mostrar la evidencia guardada o correr los scripts (abajo) |

**Evidencia guardada** (corridas reales del 5 de octubre de 2026):

- [`docs/evidencia/prueba_fallas_checkout.txt`](evidencia/prueba_fallas_checkout.txt): **45/45** verificaciones, escenarios E0 a E5.
- [`docs/evidencia/prueba_buscador.txt`](evidencia/prueba_buscador.txt): **21/21** verificaciones, bloques B1 a B7.

**Correr los scripts en vivo** (con el backend arriba y `PERMITIR_FALLAS_SIMULADAS=1`; cada uno detiene y vuelve a levantar Elasticsearch, así que tardan algunos minutos; crean pedidos reales de `maria.torres@email.com`):

```bash
python backend/scripts/prueba_buscador.py --caida-real
python backend/scripts/prueba_fallas_checkout.py --caida-real
```

---

## 5. Preguntas probables del catedrático

**¿Por qué no usaron 2PC?**
Redis, MongoDB y Elasticsearch no participan en transacciones XA con PostgreSQL. Y aunque lo hicieran, 2PC ataría la disponibilidad del pago a la del buscador: con Elasticsearch caído no se podría comprar, y si el coordinador cae, todos quedan bloqueados.

**¿Por qué no una saga pura?**
Porque "copiar el stock al catálogo" no tiene una compensación con sentido. Si falla, lo correcto es completarlo, no deshacer el pago. Usamos compensación solo antes del COMMIT (las reservas de oferta) y reintentos idempotentes después.

**¿Qué pasa si el relevo está caído?**
El relevo es un hilo del backend. Si Flask está detenido, nadie reintenta, pero los eventos ya están guardados en `eventos_sincronizacion` en la misma transacción que el pedido, así que se procesan al volver. Un evento que falla 10 veces queda `fallido` y se vuelve a encolar desde el panel. Nunca afecta pedidos, pagos ni inventario, solo las copias de lectura.

**¿Por qué `flattened` para los atributos?**
Cada categoría tiene sus propios atributos: son cerca de 125 claves distintas. Con un mapping dinámico, cada clave sería un campo nuevo del índice (la "explosión de campos"). `flattened` los guarda en un solo campo y permite filtrar por valor exacto, que es lo que necesitamos.

**¿Qué garantiza exactamente la idempotencia?**
Que la misma compra no se cobre dos veces. El navegador genera una clave por intento y la conserva entre reintentos. La clave se guarda en la misma transacción que el pedido: si el pago se confirmó, un reintento devuelve ese pedido (`200 repetido`); si se revirtió, la clave queda libre y el reintento compra. Si dos peticiones con la misma clave llegan a la vez, el índice único hace que gane una sola. No protege a un cliente que no mande la clave (en la API es opcional; el frontend siempre la manda).

**¿Por qué no NewSQL?**
Ver el bloque 3.6. En corto: el problema que resuelve NewSQL (escalar la escritura y sobrevivir a la caída de nodos sin failover manual) no es un problema que TiendaYa tenga hoy, y mover solo los pagos rompería la atomicidad pedido-pago.

---

## 6. Después de la demo

1. Volver a poner `PERMITIR_FALLAS_SIMULADAS=0` en el `.env`.
2. Reiniciar el backend (Ctrl+C y `python backend/main.py`). Comprobar que `curl http://127.0.0.1:8000/api/checkout/fallas-simuladas` responde `"habilitadas": false`.
3. Comprobar que Elasticsearch quedó arriba (`docker compose ps`, `healthy`).
4. Verificar que el outbox no tenga eventos pendientes ni fallidos: `curl "http://127.0.0.1:8000/api/sincronizacion/eventos?rol_solicitante=administrador&estado=pendiente"` debe devolver `"eventos": []`, y el `resumen`, `"pendiente": 0` y `"fallido": 0`. Si queda alguno, en el panel → Sincronización: "Procesar pendientes ahora" o "Volver a encolar fallidos".
5. Los pedidos de la demo quedan en la base local de quien presentó; no hace falta borrarlos.
