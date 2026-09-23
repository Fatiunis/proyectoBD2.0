# ADR-003 — Almacén clave-valor (Redis) para el carrito de compra y la oferta de inventario limitado

Fecha: 2026-09-22 (documenta decisiones tomadas el 2026-09-13, al iniciar la Entrega 2)

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
- El precio guardado en el carrito es informativo: el precio que se cobra es el vigente en PostgreSQL al momento del checkout.

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

Alternativa 3: cada oferta usa dos claves en Redis:

- `oferta:{producto_id}:stock`: el contador que se descuenta;
- `oferta:{producto_id}:limite`: el límite original, para mostrar "quedan X de Y".

Ambas se crean con el **mismo TTL**, que es la duración de la oferta indicada al crearla, así que la oferta termina sola al vencer la ventana. La reserva ejecuta `backend/app/lua/reservar_oferta.lua` con `EVALSHA`: el script lee el contador, comprueba que alcanza y lo descuenta, todo dentro de una única ejecución atómica del servidor Redis. Solo el vendedor dueño del producto o un administrador pueden crear o cerrar una oferta.

### Justificación

- **Consistencia**: Redis ejecuta cada script Lua completo sin intercalar ningún otro comando, así que el "comprobar y descontar" no tiene ventana de carrera. No hacen falta `WATCH`/`MULTI` ni locks en Python.
- **Escalabilidad bajo contención**: las alternativas 1 y 2 son correctas en PostgreSQL, pero en una flash sale todas las solicitudes compiten por **la misma fila** de inventario. Con `FOR UPDATE` se serializan, y cada una mantiene abierta una transacción y una conexión del pool mientras espera: el pico de tráfico de la oferta degradaría también al checkout normal y al resto del sistema. En Redis cada reserva es una operación en memoria de microsegundos que no ocupa conexiones de la base transaccional.
- **Patrón de consulta**: el acceso es un único contador por clave, decrementado miles de veces en poco tiempo, que es justo el caso de uso nativo de un almacén clave-valor.
- **Ventana de tiempo**: el TTL de Redis implementa directamente "disponible durante una ventana de tiempo determinada". En PostgreSQL haría falta una columna de fin y filtrar por fecha en cada solicitud.
- **Costo operativo**: reutiliza el mismo servicio Redis del carrito, sin un componente adicional.

### Evidencia

`backend/scripts/prueba_concurrencia_oferta.py` lanza 50 solicitudes concurrentes de "reservar 1 unidad" contra una oferta con límite de 10. El resultado esperado y obtenido es: **10 reservas exitosas, 40 rechazadas y stock final en Redis igual a 0**, sin sobreventa. El servidor Flask corre con `threaded=True` para que las solicitudes lleguen realmente en paralelo.

### Consecuencias

**Beneficios:**
- Sin sobreventa bajo concurrencia, sin locks de aplicación y sin cargar la base transaccional durante el pico.
- La oferta vence sola al terminar su ventana, sin procesos de limpieza.

**Limitaciones asumidas:**
- El cupo de la oferta es **independiente del inventario real** de PostgreSQL: es una bolsa de unidades apartada para la promoción, y no se sincroniza con `inventario`.
- La reserva descuenta el cupo, pero todavía no genera un pedido ni aplica un precio de oferta: convertirla en compra es trabajo pendiente.
- Si Redis se reinicia durante una oferta, el contador depende de la persistencia AOF; una oferta en curso podría perderse.
- El backend carga el script Lua al arrancar, así que **el servidor no inicia si Redis no está disponible**.
