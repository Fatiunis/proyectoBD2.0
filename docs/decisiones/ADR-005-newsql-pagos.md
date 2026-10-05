# ADR-005 — Evaluación de un motor NewSQL para el módulo de pagos

Fecha: 2026-10-05 (Entrega 3, evaluación opcional)

**Conclusión: no migrar.** El módulo de pagos se queda en PostgreSQL. Al final se documentan las condiciones bajo las que sí convendría migrar y cómo habría que hacerlo.

Esta es una evaluación documental, contrastada con el código y los datos reales del proyecto. No se montó un clúster NewSQL ni se hicieron pruebas de rendimiento comparativas.

## Contexto

Hoy, el módulo de pagos es la tabla `pagos` de PostgreSQL. Cada pago se escribe dentro de `sp_procesar_checkout`, en **la misma transacción** que el pedido (`pedidos`), sus líneas (`lineas_pedido`) y el descuento de inventario (`inventario`, con `SELECT ... FOR UPDATE`). `pagos.id_pedido` es `UNIQUE` y `pagos.referencia_transaccion` también: un pedido tiene exactamente un pago, y una referencia nunca se repite.

Los motores NewSQL (CockroachDB, YugabyteDB, TiDB, Google Spanner) prometen lo mismo que PostgreSQL (SQL y transacciones ACID serializables), pero **repartido en varios nodos**: los datos se dividen en rangos replicados con un protocolo de consenso (Raft o Paxos). Se tolera la caída de un nodo sin perder datos y se escala la escritura agregando nodos. La pregunta es si esas capacidades le resuelven a TiendaYa un problema que hoy tenga.

## Alternativas consideradas

1. **No introducir cambios**: pagos (y todo el núcleo transaccional) en un PostgreSQL.
2. **Migrar solo la tabla `pagos`** a un motor NewSQL, dejando pedidos e inventario en PostgreSQL.
3. **Migrar todo el núcleo transaccional** (usuarios, pedidos, líneas, pagos, inventario y el procedimiento de checkout) a un motor NewSQL compatible con PostgreSQL, como **YugabyteDB** (reusa la capa de consultas de PostgreSQL) o **CockroachDB** (compatible con su protocolo).

## Criterios aplicados al caso

### Consistencia

- **Alternativa 2 empeora la consistencia en vez de mejorarla.** Hoy el pedido y su pago son atómicos porque viven en la misma base. Con `pagos` en otro motor, el checkout pasaría a ser una transacción distribuida entre dos bases SQL distintas. Volveríamos al problema que resuelve la [estrategia de consistencia](../estrategia-consistencia-checkout.md), pero **en el registro más sensible del sistema**: podría quedar un pedido "pagado" sin pago, o un pago sin pedido. Esta alternativa queda descartada por sí sola.
- **La alternativa 3 conserva la atomicidad**, porque todo sigue en una base, y además la vuelve tolerante a la caída de un nodo. Pero no agrega ninguna garantía que TiendaYa no tenga hoy: PostgreSQL ya da transacciones ACID, y con `SELECT ... FOR UPDATE` en el procedimiento no se puede vender de más.

### Patrón de consulta y contención

- El checkout bloquea **filas calientes**: la fila de `inventario` de un producto popular, y sobre todo la de un producto en oferta relámpago. En un motor distribuido, cada escritura confirmada pasa por consenso entre réplicas. Las transacciones que compiten por la misma fila se serializan igual que en PostgreSQL, pero cada una tarda más y aparecen errores de reintento por serialización (`40001`) que la aplicación debe manejar. NewSQL escala bien cuando las escrituras se reparten en muchas filas distintas, no cuando todas compiten por la misma.
- El pico de contención real de TiendaYa, la oferta relámpago, ya se sacó de la base relacional en la Entrega 2: se resuelve en Redis con scripts Lua atómicos ([ADR-003](ADR-003-redis-carrito-y-oferta.md)), y a PostgreSQL solo llegan las compras ya reservadas.

### Escalabilidad

- El escenario es una plataforma "de escala intermedia". Su volumen de pagos (como mucho, unas decenas por segundo en un pico) está muy por debajo de lo que un solo servidor PostgreSQL escribe. El cuello de botella no es la escritura de pagos.
- El crecimiento de lectura (reportes, panel de ventas) se resuelve con **réplicas de lectura** de PostgreSQL, sin cambiar de motor.

### Compatibilidad y costo de migración

- `sp_procesar_checkout` está escrito en **PL/pgSQL**, con `SELECT ... FOR UPDATE`, `jsonb_array_elements ... WITH ORDINALITY` y manejo de excepciones. YugabyteDB, que reusa el motor de consultas de PostgreSQL, es el que mejor lo soportaría. CockroachDB habla el protocolo de PostgreSQL, pero su soporte de procedimientos en PL/pgSQL es más reciente y parcial, y habría que verificarlo función por función. TiDB es compatible con MySQL: implicaría reescribir el procedimiento.
- Habría que adaptar SQLAlchemy (dialecto propio de cada motor), las secuencias (`SERIAL` es un punto caliente en un motor distribuido; se recomiendan UUID) y el manejo de reintentos por serialización en el backend.

### Costo operativo

- Un clúster NewSQL necesita **al menos 3 nodos** para tolerar la caída de uno. Hoy el proyecto corre PostgreSQL, MongoDB, Redis, Neo4j y Elasticsearch: sumaría tres procesos más, para resolver un problema (disponibilidad ante la caída de un nodo de base) que no está en los requerimientos del curso.
- También cambia la licencia: CockroachDB modificó la suya en 2024 (hay que revisar los términos vigentes); YugabyteDB y TiDB son de código abierto.

## Decisión

Alternativa 1: **el módulo de pagos se queda en PostgreSQL**, en la misma base y la misma transacción que pedidos e inventario. La alternativa 2 se descarta porque rompe la atomicidad pedido-pago. La alternativa 3 es técnicamente viable, pero su costo (operación, migración del procedimiento, reintentos por serialización, más latencia por escritura) no compra nada que TiendaYa necesite hoy.

## Cuándo sí estaría justificado migrar

Migrar el **núcleo transaccional completo** (nunca solo `pagos`) a un motor NewSQL compatible con PostgreSQL, preferentemente YugabyteDB por compatibilidad con el procedimiento, si se cumple al menos una de estas condiciones:

1. **Escritura multirregión activa-activa**: compradores en varios países que deben poder pagar contra una región cercana, con baja latencia, y sin que todas las escrituras viajen a un único servidor principal.
2. **Disponibilidad sin intervención manual**: un requisito de negocio de que el pago siga funcionando ante la caída de un servidor o de una zona entera, sin perder ninguna transacción confirmada (RPO = 0) y sin un failover manual. Con PostgreSQL esto exige réplicas síncronas y herramientas de failover (Patroni u otras) que hay que operar.
3. **Volumen de escritura** sostenido que supere lo que da un PostgreSQL escalado verticalmente, medido con métricas reales de producción (no estimado) y con las escrituras repartidas entre muchas filas, no concentradas en unas pocas.
4. **Requisitos regulatorios de residencia de datos** que obliguen a guardar los pagos de cada país en su territorio sin partir la base en varias independientes. Algunos motores NewSQL permiten fijar filas a regiones.

Si alguna se cumple, la migración debería hacerse con el procedimiento y la estrategia de consistencia actuales como contrato. También habría que agregar reintentos ante errores de serialización (`40001`) en `checkout.py`, que la clave de idempotencia ya vuelve seguros: reintentar un pago con la misma clave nunca cobra dos veces.

## Consecuencias

**Beneficios de no migrar:**
- Pedido, líneas, pago e inventario siguen confirmándose en una sola transacción local, sin coordinación distribuida.
- Ningún componente más que operar; el procedimiento y SQLAlchemy siguen igual.

**Limitaciones asumidas:**
- PostgreSQL corre en un solo nodo: si se cae, no se puede pagar hasta que vuelva. El checkout lo informa con `503 PAGO_NO_CONFIRMADO` y garantiza que no se cobró (ver la [estrategia de consistencia](../estrategia-consistencia-checkout.md), punto F5).
- Escalar la escritura más allá de un servidor exigiría replantear esta decisión.
