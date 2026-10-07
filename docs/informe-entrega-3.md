# TiendaYa — Informe de la Entrega 3

**Curso:** Bases de Datos 2 — Universidad del Istmo
**Catedrático:** Ing. Javier Álvarez
**Integrantes:** Diego Rueda, Marcos Pineda, Fátima Ramazzini
**Repositorio:** github.com/Fatiunis/proyectoBD2.0
**Tema de la entrega:** recuperación de información y consistencia en operaciones distribuidas (motores de búsqueda, transacciones, NewSQL)

> **Borrador.** Las secciones marcadas con ✏️ las completa el equipo. La evidencia técnica corresponde a pruebas ejecutadas contra el sistema real (PostgreSQL 18, MongoDB 8, Redis 7, Neo4j 5 y Elasticsearch 8.15) el 5 de octubre de 2026.

---

## 1. Distribución de responsabilidades ✏️

| Integrante | Responsabilidades en esta entrega |
|---|---|
| Diego Rueda | ✏️ |
| Marcos Pineda | ✏️ |
| Fátima Ramazzini | ✏️ |

---

## 2. Resumen de la entrega

| Requerimiento del enunciado | Componente | Dónde está |
|---|---|---|
| Búsqueda de texto libre con tolerancia a variaciones y orden por relevancia | Elasticsearch | `backend/app/busqueda_es.py`, `backend/app/blueprints/busqueda.py` |
| Índice con un mapping construido deliberadamente | Elasticsearch | `database/elasticsearch/productos_indice.json` |
| Autocompletado y corrección de errores ortográficos | Elasticsearch | `GET /api/busqueda/autocompletar`, `phrase suggester` en `GET /api/busqueda` |
| Filtros facetados con agregaciones del motor | Elasticsearch | Facetas de categoría, marca, tienda y precio en `GET /api/busqueda` |
| Documento de estrategia de consistencia del checkout | Documento | [`docs/estrategia-consistencia-checkout.md`](estrategia-consistencia-checkout.md) |
| Manejo explícito de fallos parciales, comunicado al usuario | PostgreSQL (idempotencia + outbox) + Redis (compensación) | `backend/app/blueprints/checkout.py`, `backend/app/sincronizacion.py`, `FormularioCheckout.vue` |
| Evidencia de prueba de falla simulada | Script + salida | `backend/scripts/prueba_fallas_checkout.py`, [`docs/evidencia/prueba_fallas_checkout.txt`](evidencia/prueba_fallas_checkout.txt) |
| Evaluación opcional NewSQL para pagos | Documento de decisión | [`docs/decisiones/ADR-005-newsql-pagos.md`](decisiones/ADR-005-newsql-pagos.md) |
| Diagrama de arquitectura actualizado | Mermaid | [`docs/arquitectura.md`](arquitectura.md) |
| Justificación de incorporar el motor de búsqueda | Documento de decisión | [`docs/decisiones/ADR-004-motor-de-busqueda.md`](decisiones/ADR-004-motor-de-busqueda.md) |
| Instrucciones para levantar el sistema completo | README | `README.md` (Docker Compose con Elasticsearch, script de indexación, migración SQL) |

---

## 3. Buscador del catálogo (Elasticsearch)

### Diagnóstico

La búsqueda anterior usaba el índice de texto de MongoDB (`$text`). Contra el catálogo real de 1015 productos, `laptp`, `audifnos`, `celulr`, `lapt` y `auriculares` devolvían **0 resultados**, y `celular` devolvía 14 tablets ("Wi-Fi + Celular") y ningún celular. `$text` no tiene coincidencia aproximada, ni por prefijo, ni sinónimos, y su relevancia no se puede ajustar. El análisis de alternativas (no cambiar, texto completo de PostgreSQL, Atlas Search, Elasticsearch) está en **ADR-004**.

### Implementación

- **Índice** `productos` (alias de `productos_v<fecha>`): 1 shard, 0 réplicas, `dynamic: strict`. Es una proyección de solo lectura de la colección Mongo `productos`, que sigue siendo la fuente de verdad.
- **Mapping deliberado** (detalle campo por campo en ADR-004):
  - Un analizador en español sin acentos ni mayúsculas, con stemming suave y una lista de plurales en inglés ("laptops" → "laptop").
  - Sinónimos aplicados solo al buscar ("portátil" → laptop, "auriculares" → audífonos, "smartphone" → celular).
  - Un subcampo con *edge n-grams* para autocompletar y otro sin stemming para el corrector.
  - `keyword` para las facetas, `flattened` para las cerca de 125 claves de atributos variables por categoría (124 al 2026-10-06) (evita la explosión de campos) y `scaled_float` para el precio.
- **Relevancia**: combina coincidencia aproximada (`fuzziness: AUTO`) por campo con pesos, un puntaje fijo cuando lo buscado nombra una categoría, frase exacta (con 2 o más palabras), prefijos y SKU exacto.
- **Autocompletado**: `GET /api/busqueda/autocompletar` sobre el subcampo de *edge n-grams*, con un error de tipeo permitido. En la barra de búsqueda se ve como una lista desplegable que se navega con el teclado.
- **"¿Quisiste decir…?"**: un `phrase suggester` que solo corrige palabras que no existen en el índice.
- **Facetas** de categoría, marca, tienda y rangos de precio, calculadas con agregaciones `terms` y `range` del motor. Son **disyuntivas**: cada faceta se calcula con los filtros de las demás, así que elegir una marca no hace desaparecer las otras.
- **Sincronización**: guardar un producto en el admin lo reindexa en el acto (si Elasticsearch no responde, queda un evento en el outbox). El stock se actualiza tras cada compra por el outbox del checkout. `database/migrations/indexar_productos_elasticsearch.py` reconstruye el índice completo sin cortar el servicio: crea uno nuevo, verifica la cantidad y mueve el alias.
- **Degradación**: si Elasticsearch no responde, `GET /api/busqueda` devuelve `503 BUSCADOR_NO_DISPONIBLE`, y el frontend repite la búsqueda contra `$text` de MongoDB con un aviso de "búsqueda simplificada".

### Evidencia

Script: `backend/scripts/prueba_buscador.py --caida-real` ([salida completa](evidencia/prueba_buscador.txt)): **21/21 verificaciones correctas**.

| Caso | Resultado |
|---|---|
| `laptp`, `audifnos`, `celulr` (errores de tipeo) | 106, 50 y 74 resultados; sugiere "laptop", "audifonos" y "celular" |
| `portatil`, `auriculares` (sinónimos) | Laptops y audífonos primero |
| `celular` | Los 5 primeros son de la categoría Celulares (antes, solo tablets) |
| `smartphone samsung` / `mochila laptop` | Celulares Samsung primero / mochilas para laptop, no laptops |
| Autocompletado de `iph`, `lapt`, `aufi` | iPhone…, Laptop…, Audífonos… |
| Facetas de `mouse` | 4 facetas; marca Logitech = 20 resultados, igual al conteo de la faceta; las otras 6 marcas siguen visibles |
| Precio Q1,000–Q5,000 ordenado de menor a mayor | 14 resultados, de Q1,029 a Q4,759, en orden |
| Elasticsearch detenido de verdad | `503 BUSCADOR_NO_DISPONIBLE`; la búsqueda de respaldo de MongoDB respondió (105 resultados); al levantarlo, volvió a responder |

---

## 4. Estrategia de consistencia del checkout

El documento completo, con la tabla de los 14 puntos de falla y su mitigación, está en **[`estrategia-consistencia-checkout.md`](estrategia-consistencia-checkout.md)**. En resumen:

- **Componentes**: PostgreSQL (pedido, pago e inventario; fuente de verdad), Redis (carrito y reservas de oferta), MongoDB y Elasticsearch (copias del stock para leer).
- **Mecanismo elegido**: una **transacción local** en PostgreSQL. Lo que pasa antes del COMMIT se **compensa** (las reservas de oferta vuelven al cupo). En el COMMIT se guardan juntos el pedido, la **clave de idempotencia** y los **eventos del outbox**. Lo que pasa después se completa con **reintentos idempotentes** (outbox + relevo con espera exponencial). Se acepta una **ventana de consistencia eventual**, medida, en las copias de lectura.
- **Se descartó 2PC** porque Redis, MongoDB y Elasticsearch no participan en transacciones XA, y porque ataría la disponibilidad del pago a la del buscador. **Se descartó una saga pura** porque "copiar el stock" no tiene una compensación con sentido: hay que completarlo, no deshacer el pago.
- **Garantías**: nunca se cobra dos veces la misma compra (ni por un reintento del cliente ni por un carrito sin limpiar), nunca se sobrevende, el pedido es atómico y, una vez confirmado, es definitivo. El usuario siempre recibe un mensaje que dice si se le cobró y si puede reintentar.

### Comunicación al usuario

| Situación | Lo que ve el comprador |
|---|---|
| Falla antes de cobrar (Redis o PostgreSQL) | Aviso rojo "Tu compra no se completó · No se realizó ningún cobro y tu carrito sigue intacto; intenta de nuevo", y el botón cambia a "Reintentar compra" |
| Se perdió la respuesta (sin conexión) | Aviso amarillo "No sabemos si se completó… Puedes reintentar con tranquilidad: si ya se había confirmado, no se te cobrará dos veces" (el reintento usa la misma clave) |
| Reintento de un pago que sí se había confirmado | "Tu pedido #N ya estaba confirmado; no se cobró dos veces" |
| Pedido confirmado, pero falló una copia en otro motor | Compra confirmada, más "El stock del catálogo y tu carrito pueden tardar unos segundos en actualizarse" |
| Buscador caído | Aviso "El buscador avanzado no está disponible… búsqueda simplificada" |

Para el equipo administrativo, el panel tiene una pestaña nueva, **Sincronización**, con los eventos pendientes, procesados y fallidos, su último error y botones para procesarlos ya o volver a encolar los fallidos.

---

## 5. Prueba de falla simulada

Con `PERMITIR_FALLAS_SIMULADAS=1`, el checkout acepta un punto de falla que lanza una excepción real en ese lugar del flujo. Hay cinco puntos: Redis al leer el carrito, PostgreSQL antes del COMMIT, y Redis, MongoDB o Elasticsearch después del COMMIT. Además, se probó una caída **real** de Elasticsearch, deteniendo su contenedor.

Script: `backend/scripts/prueba_fallas_checkout.py --caida-real` ([salida completa](evidencia/prueba_fallas_checkout.txt)): **45/45 verificaciones correctas**, comprobadas directamente en los cuatro motores.

| Escenario | Respuesta | Estado verificado |
|---|---|---|
| **E0** Compra normal + reintento con la misma clave | 201, luego 200 `repetido` | Un solo pedido; stock igual en PostgreSQL, MongoDB y Elasticsearch; carrito limpio |
| **E1** Redis cae al leer el carrito | 503 `CARRITO_NO_DISPONIBLE` | Sin pedido, sin cambio de stock, carrito intacto |
| **E2** PostgreSQL cae antes del COMMIT (con oferta relámpago) | 503 `PAGO_NO_CONFIRMADO` | Rollback completo, incluida la clave de idempotencia. **Compensación**: la reserva volvió a `activa` (0 vendidas). Reintentar con la misma clave compró: 2 vendidas en la oferta, 2 menos en PostgreSQL |
| **E3** Redis cae después del COMMIT | 201 con `sincronizacion_pendiente` | Lo pagado seguía en el carrito, pero un checkout con **otra** clave respondió `409 CARRITO_VACIO` y el reintento con la misma, `200 repetido`: **nunca hubo un segundo pedido** |
| **E4** MongoDB cae después del COMMIT | 201 con `sincronizacion_pendiente` | MongoDB con stock viejo (37 contra 36). El relevo lo corrigió solo en **20 s** (2.º intento) |
| **E5** Caída real de Elasticsearch | Búsqueda 503; checkout 201 | El checkout no depende del buscador. Al levantar el contenedor, el relevo actualizó su stock en **25 s** |

### Demostración en vivo (para la presentación)

1. Con `PERMITIR_FALLAS_SIMULADAS=1` en el `.env`, entrar como `maria.torres@email.com` y agregar un producto al carrito.
2. En "Finalizar compra", elegir en **Simular falla (solo desarrollo)** la opción "PostgreSQL se cae después de ejecutar el procedimiento…" y confirmar: aparece el aviso rojo y el carrito sigue igual.
3. Volver a "Sin falla" y presionar **Reintentar compra**: la compra se confirma, con un solo pedido.
4. Repetir con "MongoDB no responde…" y abrir, como `admin@tiendaya.com`, la pestaña **Sincronización** del panel: el evento aparece `pendiente` con su error y, en unos segundos, pasa a `procesado` (2 intentos).
5. Para la caída real: `docker compose stop elasticsearch`, buscar algo (aparece el aviso de búsqueda simplificada), comprar (funciona), `docker compose start elasticsearch` y ver en Sincronización cómo se procesa el evento pendiente.

---

## 6. Evaluación opcional: NewSQL para el módulo de pagos

Análisis completo en **ADR-005**. **Conclusión: no migrar.**

- Migrar **solo** `pagos` a un motor NewSQL **empeoraría** la consistencia: hoy pedido, pago e inventario se confirman en una transacción local, y separarlos los convertiría en una transacción distribuida justo en el registro más sensible.
- Migrar **todo** el núcleo transaccional (por ejemplo, a YugabyteDB, compatible con el procedimiento en PL/pgSQL) es viable. Pero no resuelve un problema que TiendaYa tenga hoy: el volumen de pagos está muy por debajo de lo que un PostgreSQL escribe, y la contención de la oferta relámpago ya se resolvió en Redis. A cambio, cuesta al menos 3 nodos, más latencia por escritura (consenso) y manejar los reintentos por serialización.
- El ADR documenta cuándo sí convendría: escritura multirregión activa-activa, disponibilidad sin failover manual con RPO = 0, un volumen de escritura medido que supere a un PostgreSQL escalado, o residencia de datos por país.

---

## 7. Arquitectura actualizada

El diagrama está en [`docs/arquitectura.md`](arquitectura.md). Agrega **Elasticsearch** (búsqueda, con respaldo en MongoDB), las tablas `checkout_idempotencia` y `eventos_sincronizacion` en PostgreSQL, y el **relevo del outbox**, que conecta PostgreSQL con Redis, MongoDB y Elasticsearch. Distingue las escrituras en la fuente de verdad (líneas continuas) de las copias con consistencia eventual (líneas punteadas).

---

## 8. Limitaciones conocidas

- **Sin autenticación en el servidor**: el rol y el `id_usuario` los envía el cliente. Elasticsearch y Redis corren sin autenticación (`xpack.security.enabled=false`). El control de acceso a componentes NoSQL es requisito de la entrega final.
- **El relevo del outbox es un hilo dentro de Flask**: si el backend está caído, nadie reintenta (los eventos quedan guardados y se procesan al volver).
- **La clave de idempotencia es opcional en la API**: el frontend siempre la envía, pero un cliente que no la mande no queda protegido contra reintentos.
- **El precio editado en el admin solo vive en MongoDB y Elasticsearch**; el checkout cobra el de PostgreSQL (limitación conocida desde la Entrega 1).
- **Algunas categorías no tienen el atributo `marca`** (por ejemplo, Laptops), así que en esas búsquedas no aparece esa faceta.
- **La prueba de falla crea pedidos reales** en la base local, y un pedido revertido deja un hueco en la numeración (`SERIAL`).

---

## 9. Cómo reproducir la evidencia

Con el sistema levantado según el `README.md` (incluidos el contenedor de Elasticsearch, el script de indexación y la migración `migracion_entrega3_consistencia.sql`), y con `PERMITIR_FALLAS_SIMULADAS=1` en el `.env`:

```bash
# Buscador (B7 detiene y vuelve a levantar Elasticsearch)
python backend/scripts/prueba_buscador.py --caida-real

# Fallas simuladas del checkout (E5 detiene y vuelve a levantar Elasticsearch)
python backend/scripts/prueba_fallas_checkout.py --caida-real

# Estado del outbox
curl "http://127.0.0.1:8000/api/sincronizacion/eventos?rol_solicitante=administrador"
```
