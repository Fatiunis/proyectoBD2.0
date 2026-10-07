# ADR-006 — Carrito sin expiración por defecto (expiración configurable con `CARRITO_TTL_SEGUNDOS`)

Fecha: 2026-10-07 (después de la Entrega 3)

**Reemplaza** un punto de la Decisión 1 de [ADR-003](ADR-003-redis-carrito-y-oferta.md): el valor por defecto del TTL del carrito (antes `1800` segundos). El resto de ADR-003 sigue vigente: el carrito sigue siendo un hash de Redis por usuario (`carrito:{id_usuario}`) y la oferta de inventario limitado no cambia.

## Contexto

En la Entrega 2 el carrito expiraba a los 30 minutos de inactividad: `CARRITO_TTL_SEGUNDOS=1800`, con `EXPIRE` en cada lectura o escritura (ADR-003, Decisión 1).

El 2026-10-07 el valor por defecto de `CARRITO_TTL_SEGUNDOS` pasó a `0` (`backend/app/config.py` y `.env.example`). Con `0`, el carrito no expira: en cada lectura o escritura, `renovar_ttl_carrito()` (`backend/app/blueprints/carrito.py`) le hace `PERSIST`, que le quita el TTL que pudiera tener. Con un valor mayor que 0 hace `EXPIRE` y el carrito vence tras ese tiempo sin actividad, como en la Entrega 2.

El cambio choca con el enunciado. Para la Entrega 2 pide un "carrito de compra persistente por sesión, con expiración automática por inactividad" y "un tiempo de expiración configurado explícitamente y su efecto documentado sobre el flujo de checkout". La rúbrica de la Entrega 2 le da 1.5 puntos a "implementación del carrito sobre el almacén clave-valor, con expiración justificada". Por eso se registró como hallazgo ([H-016](../hallazgos.md)) y se pidió una decisión explícita del equipo.

## Alternativas consideradas

1. **Volver a un valor por defecto mayor que 0** (`1800` en `config.py` y en `.env.example`), conservando `0` como opción para desactivar la expiración.
2. **Mantener `0` por defecto** (el carrito no expira) y dejar la expiración por inactividad como un valor que se configura explícitamente en el `.env`.

## Decisión

Alternativa 2. El carrito **no expira por defecto** (`CARRITO_TTL_SEGUNDOS=0`, `PERSIST` en cada operación). Cualquier valor mayor que 0 en el `.env` reactiva la expiración por inactividad con el mecanismo de la Entrega 2 (`EXPIRE` renovado en cada operación).

La decisión la tomó el equipo el 2026-10-07.

## Justificación

- **La expiración sigue configurándose explícitamente.** El mecanismo de la Entrega 2 no se quitó: está detrás de una sola variable, `CARRITO_TTL_SEGUNDOS`, documentada en el `.env.example` y en el README. Lo único que cambió es el valor que se usa si nadie la define.
- **Lo que de verdad es escaso sigue venciendo.** Las líneas de oferta relámpago del carrito siguen venciendo a los `RESERVA_OFERTA_TTL_SEGUNDOS` (60 s por defecto) pase lo que pase con el carrito: si no se compran a tiempo, salen del carrito y las unidades vuelven a la oferta. Un carrito sin expiración no aparta nada: el precio y el stock que se cobran se validan en el checkout contra PostgreSQL.
- **Para demostrar la expiración se configura un valor mayor que 0.** En la demostración y la revisión de la Entrega 2 se pone, por ejemplo, `CARRITO_TTL_SEGUNDOS=1800` en el `.env` y se reinicia el backend. Con ese valor se reproduce la evidencia del [informe de la Entrega 2](../informe-entrega-2.md) (TTL de 1799 s tras una operación).

## Consecuencias

**Beneficios:**
- El comprador no pierde lo que agregó al carrito por dejarlo un rato sin tocar.
- Un carrito que quedó con TTL de la configuración anterior deja de vencer en cuanto se lee o se modifica (`PERSIST`), sin migrar datos.
- Volver a la expiración por inactividad no requiere tocar código: basta con un valor mayor que 0 en el `.env`.

**Limitaciones asumidas:**
- Con el valor por defecto, los carritos abandonados no se borran solos y se acumulan en la memoria de Redis. Para el volumen del curso no es un problema; en un despliegue real habría que configurar un valor mayor que 0.
- Quien instale el proyecto desde cero con el `.env.example` tiene un carrito sin expiración. Para cumplir el requerimiento de "expiración automática por inactividad" en una demostración hay que cambiar la variable a mano.
- La limitación de ADR-003 "si el carrito expiró, el checkout lo rechaza" solo aplica cuando `CARRITO_TTL_SEGUNDOS` es mayor que 0.
- Cómo comprobar el modo vigente: después de agregar un producto, `docker compose exec redis redis-cli TTL carrito:<id_usuario>` responde `-1` con `0` (sin expiración) y un número de segundos cercano al configurado con un valor mayor que 0.
