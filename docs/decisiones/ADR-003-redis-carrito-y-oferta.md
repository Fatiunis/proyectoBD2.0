# ADR-003 — Almacén clave-valor (Redis) para el carrito de compra y la oferta de inventario limitado

Fecha: 2026-09-22 (documenta decisiones tomadas el 2026-09-13, al iniciar la Entrega 2). Actualizado el 2026-09-23: la oferta pasó a tener precio de oferta y reserva temporal en el carrito, y el cupo se descuenta al comprar.

Este registro cubre las dos funcionalidades de la Entrega 2 que se asignaron a un almacén clave-valor. Aunque ambas terminan en Redis, se evalúan por separado porque el problema de fondo es distinto: el carrito es un problema de **patrón de acceso sobre datos transitorios**; la oferta es un problema de **concurrencia sobre un contador compartido**.

---

## Decisión 1 — Carrito de compra

### Contexto

Antes de la Entrega 2 el carrito vivía solo en el navegador (`localStorage`): no existía en el servidor, no sobrevivía a un cambio de dispositivo y no tenía forma de expirar. El enunciado pide un carrito persistente por sesión, con expiración automática por inactividad.

El patrón de acceso del carrito es muy distinto al de los datos de negocio que ya viven en PostgreSQL:

- **Escrituras muy frecuentes y de vida corta**: cada "agregar", "cambiar cantidad" o "quitar" es una escritura, y la mayoría de los carritos nunca se convierte en pedido.
- **Lectura siempre por una sola clave**: el carrito del usuario X. Nunca se consulta "todos los carritos que contienen el producto Y" ni se cruza con otras tablas.
- **Sin valor histórico**: un carrito abandonado no tiene que conservarse. Lo que importa conservar (el pedido, sus líneas y el pago) ya queda registrado en PostgreSQL al hacer checkout.

### Alternativas consideradas

1. **No introducir cambios**: mantener el carrito solo en el navegador.
2. **Tabla `carritos` / `lineas_carrito` en PostgreSQL**, con una columna `ultima_actividad` y una tarea programada que borre los carritos inactivos.
3. **Hash en Redis por usuario** (`carrito:{id_usuario}`) con TTL que se renueva en cada operación.

### Decisión

Alternativa 3: un hash de Redis por usuario, `carrito:{id_usuario}`, donde cada campo es el id del producto y el valor es el ítem serializado. El TTL es de **1800 segundos (30 minutos) de inactividad**, configurable con la variable `CARRITO_TTL_SEGUNDOS`, y se renueva (`EXPIRE`) en cada lectura o escritura.

### Justificación

- **Patrón de consulta**: el acceso es siempre "dame o modifica el carrito de este usuario", que en Redis es una sola operación sobre una clave (`HGETALL`, `HSET`, `HDEL`). En PostgreSQL requeriría un `SELECT` con `JOIN` entre carrito y líneas en cada vista, más `INSERT`/`UPDATE`/`DELETE` en cada interacción, para datos que en su mayoría se descartan.
- **Expiración**: el TTL nativo de Redis resuelve la expiración por inactividad sin código adicional. En PostgreSQL habría que implementar y operar una tarea periódica de limpieza (cron o `pg_cron`), y entre ejecuciones quedarían carritos vencidos todavía visibles.
- **Consistencia**: el carrito no necesita garantías ACID entre múltiples filas ni integridad referencial fuerte, porque no es un registro de negocio. La validación que importa (precio vigente y stock real) la hace el checkout contra PostgreSQL dentro de `sp_procesar_checkout`. Perder un carrito por un reinicio de Redis es un costo aceptable, y además se mitiga con la persistencia AOF activada en `docker-compose.yml` (`--appendonly yes`).
- **Escalabilidad**: separar este tráfico de escritura intensiva y descartable de la base transaccional evita que compita por conexiones y por espacio de WAL con los pedidos y los pagos reales.
- **Costo operativo**: Redis es un servicio más que desplegar, pero es liviano y se levanta con el mismo `docker-compose.yml` que Neo4j. La alternativa 1 no cumple el requerimiento (no hay expiración ni persistencia en el servidor), y la alternativa 2 tiene un costo de desarrollo y operación mayor para un resultado equivalente.

### Consecuencias

**Beneficios:**
- Expiración por inactividad nativa y configurable, sin tareas de limpieza.
- El carrito queda en el servidor, asociado al usuario: sobrevive a recargar la página y a cambiar de navegador.
- La base transaccional solo recibe el pedido final.

**Limitaciones asumidas:**
- El carrito exige sesión iniciada: ya no hay carrito anónimo.
- El checkout toma los productos del carrito guardado en Redis, no de lo que muestra el navegador. Si el carrito expiró, el checkout lo rechaza y el usuario debe volver a agregar los productos.
- El precio guardado en el carrito es informativo: el precio que se cobra es el vigente en PostgreSQL al momento del checkout. La excepción son las líneas de oferta relámpago, que se cobran al precio de oferta guardado en la reserva (ver Decisión 2).

---

## Decisión 2 — Oferta de inventario limitado (flash sale)

### Contexto

La oferta pone a la venta una cantidad limitada de unidades de un producto durante una ventana de tiempo, y muchas solicitudes concurrentes compiten por esas unidades. El riesgo concreto es la **sobreventa**: con un esquema ingenuo de "leer el stock, comprobar que alcanza y descontar" hecho en dos pasos, dos solicitudes simultáneas pueden leer el mismo valor, ambas creen que hay stock y ambas descuentan.

El enunciado exige resolverlo con operaciones atómicas del almacén clave-valor, con evidencia bajo concurrencia simulada y **sin bloqueos a nivel de aplicación**.

### Alternativas consideradas

1. **No introducir cambios**: vender la oferta con el mismo `sp_procesar_checkout` de PostgreSQL, que ya bloquea la fila de inventario con `SELECT ... FOR UPDATE`.
2. **`UPDATE` condicional en PostgreSQL** (`UPDATE ... SET stock = stock - n WHERE stock >= n`), que también es atómico.
3. **Contador en Redis decrementado por un script Lua** que comprueba y descuenta en una sola operación del servidor.

### Decisión

Alternativa 3. Cada oferta usa estas claves en Redis:

- `oferta:{producto_id}:stock`: el cupo **sin vender**. No baja al reservar, solo cuando un checkout consume la reserva;
- `oferta:{producto_id}:limite`: el límite original, para mostrar "quedan X de Y";
- `oferta:{producto_id}:precio`: el precio de oferta, fijo (no hay edición: para cambiarlo se finaliza la oferta y se crea otra);
- `oferta:{producto_id}:id`: un id único de esa oferta, para que las reservas de una oferta anterior del mismo producto no cuenten en la nueva;
- `oferta:{producto_id}:reservas`: un hash `id_usuario → reserva` (cantidad, precio, vencimiento y estado `activa` / `en_pago`).

Las cuatro primeras se crean juntas, en un solo script (`crear_oferta.lua`), con el **mismo TTL**, que es la duración de la oferta indicada al crearla (`duracion_minutos`, de 1 a 10 080). Así la oferta termina sola al vencer la ventana. El hash de reservas vive la ventana más la duración de una reserva, para que una reserva hecha en el último segundo se respete completa.

La compra pasa por dos etapas:

1. **Reserva** (`reservar_oferta.lua`): calcula `disponible = cupo sin vender − reservas activas`, comprueba que alcanza y guarda la reserva, todo en una única ejecución atómica del servidor Redis. La reserva dura `RESERVA_OFERTA_TTL_SEGUNDOS` (60 por defecto) y agrega al carrito una línea aparte, con el precio de oferta. Si vence sin comprarse, la siguiente operación sobre la oferta la purga y las unidades vuelven a estar disponibles; quitar la línea o vaciar el carrito la libera en el acto.
2. **Checkout**: `consumir_reserva_oferta.lua` pasa la reserva a `en_pago` y descuenta el cupo; luego `sp_procesar_checkout` cobra el precio de oferta y descuenta el `inventario` real de PostgreSQL. Si el pedido se confirma, `confirmar_reserva_oferta.lua` cierra la reserva como vendida; si PostgreSQL falla, `compensar_reserva_oferta.lua` devuelve las unidades. Si la reserva ya venció, el checkout responde `409 RESERVA_OFERTA_EXPIRADA`.

Todas las horas se toman de `TIME` de Redis, no del reloj de cada proceso Flask. Solo el vendedor dueño del producto o un administrador pueden crear o cerrar una oferta; solo un comprador puede reservar.

### Justificación

- **Consistencia**: Redis ejecuta cada script Lua completo sin intercalar ningún otro comando, así que el "comprobar y descontar" no tiene ventana de carrera. No hacen falta `WATCH`/`MULTI` ni locks en Python.
- **Escalabilidad bajo contención**: las alternativas 1 y 2 son correctas en PostgreSQL, pero en una flash sale todas las solicitudes compiten por **la misma fila** de inventario. Con `FOR UPDATE` se serializan, y cada una mantiene abierta una transacción y una conexión del pool mientras espera: el pico de tráfico de la oferta degradaría también al checkout normal y al resto del sistema. En Redis cada reserva es una operación en memoria de microsegundos que no ocupa conexiones de la base transaccional.
- **Patrón de consulta**: el acceso es un único contador por clave, decrementado miles de veces en poco tiempo, que es justo el caso de uso nativo de un almacén clave-valor.
- **Ventana de tiempo**: el TTL de Redis implementa directamente "disponible durante una ventana de tiempo determinada". En PostgreSQL haría falta una columna de fin y filtrar por fecha en cada solicitud.
- **Costo operativo**: reutiliza el mismo servicio Redis del carrito, sin un componente adicional.

### Evidencia

`backend/scripts/prueba_concurrencia_oferta.py` lanza 50 reservas concurrentes de 1 unidad (50 compradores distintos, 20 hilos) contra una oferta con límite de 10. Resultado de la corrida del 2026-09-23 contra el servidor real:

- **10 reservas exitosas y 40 rechazadas** (`409 Stock insuficiente en la oferta`), sin sobreventa;
- después de reservar: `stock_restante = 0`, `unidades_reservadas = 10` y `unidades_vendidas = 0` (reservar no es vender);
- al vaciar los carritos de los 10 ganadores, `stock_restante` vuelve a 10.

El servidor Flask corre con `threaded=True` para que las solicitudes lleguen realmente en paralelo.

### Consecuencias

**Beneficios:**
- Sin sobreventa bajo concurrencia, sin locks de aplicación y sin cargar la base transaccional durante el pico.
- La oferta vence sola al terminar su ventana, sin procesos de limpieza.

**Limitaciones asumidas:**
- El cupo de la oferta es una bolsa de unidades apartada para la promoción, **independiente del inventario real**: crear una oferta no descuenta nada de PostgreSQL. Las unidades que se venden en oferta sí se descuentan del `inventario` al confirmar la compra, igual que una compra normal.
- El precio de oferta se valida contra el `precio_base` de MongoDB al crear la oferta, y contra el de PostgreSQL en el checkout. Si un producto se editó solo en Mongo y los dos precios no coinciden, una oferta creada sin problema puede fallar al pagar; en ese caso el checkout devuelve las unidades a la oferta.
- Si el proceso Flask muere a mitad de un checkout, la reserva queda `en_pago` hasta 5 minutos (`MARGEN_PAGO_MS`) y luego se purga. Sus unidades se quedan contadas como vendidas: nunca hay sobreventa, a lo sumo alguna unidad sin vender.
- Si Redis se reinicia durante una oferta, el cupo y las reservas dependen de la persistencia AOF; una oferta en curso podría perderse.
- Los scripts Lua se cargan en Redis la primera vez que se usan (y se recargan solos si Redis perdió su caché), así que el backend arranca aunque Redis esté caído; mientras tanto, las rutas que usan Redis responden `500`.
