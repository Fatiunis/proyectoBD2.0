# ADR-007 — Detección de fraude ampliada: 4 patrones nuevos sobre un grafo ampliado

Fecha: 2026-10-07 (después de la Entrega 3)

**Amplía** la detección de fraude de [ADR-002](ADR-002-grafos-vs-columnar.md) sin reemplazarla: la elección de Neo4j y la consulta original de anillos de 3 cuentas (`GET /api/fraude/alertas`) siguen vigentes y sin cambios. El detalle técnico de lo que se construyó está en [`docs/deteccion-fraude-ampliada.md`](../deteccion-fraude-ampliada.md).

## Contexto

La detección de la Entrega 2 busca un solo patrón: tríos de cuentas que se ponen 5 estrellas en al menos 3 productos en común, con a lo sumo 6 horas entre las reseñas de cada producto. La usuaria pidió cubrir tres casos que ese patrón no ve:

1. Campañas con **reseñas malas**, no solo buenas.
2. **Grupos de cualquier tamaño**, no solo tríos (un grupo de 5 sale como 10 tríos superpuestos, y una cadena A-B-C en la que A y C no coinciden no sale).
3. **Una sola cuenta** que reseña muchos productos en poco tiempo sin compra verificada.

Dos señales útiles para esos casos no estaban en el grafo de la Entrega 2: si la reseña tiene compra verificada y a qué vendedor pertenece el producto. Una tercera, la dirección de envío, permite detectar varias cuentas de una misma persona.

## Alternativas consideradas

1. **Más patrones.** Durante el desarrollo hubo patrones además de los 4 elegidos, entre ellos `ataque_competencia` y `rafaga_producto`. Con más patrones se cubren más casos, pero se solapan entre sí (una misma cuenta sale en varias pestañas por el mismo comportamiento), hay más umbrales que calibrar con una semilla pequeña y cuesta más explicar cada alerta en el informe.
2. **Usar el plugin Graph Data Science (GDS) de Neo4j** para los grupos (algoritmo de componentes conexas, WCC). Es la herramienta natural, pero el contenedor `neo4j:5-community` del `docker-compose.yml` del curso no lo trae: habría que cambiar la imagen o instalar el plugin en cada máquina del equipo.
3. **Mantener tríos y extender solo a reseñas positivas en más productos**, ajustando los parámetros de la consulta original. Es el cambio más pequeño, pero no cubre ninguno de los tres casos pedidos: ni reseñas malas, ni grupos de otro tamaño, ni cuentas que actúan solas.
4. **4 patrones nuevos, uno por caso pedido más el de cuentas vinculadas, sobre un grafo ampliado de forma aditiva**, con las componentes conexas calculadas en Python.

## Decisión

Alternativa 4:

- **Patrones:** `cuenta_rafaga`, `grupo_coordinado` (positivo y negativo, de cualquier tamaño), `sesgo_vendedor_sin_compra` (promotor y detractor) y `cuentas_vinculadas`. Cada uno es una consulta Cypher de varios saltos con parámetros ajustables, un score de 0 a 100 calculado en Python y un nivel (alto desde 70, medio desde 40).
- **Grafo ampliado de forma aditiva:** nodos `Vendedor` y `Direccion`, relaciones `VENDIDO_POR` y `ENVIA_A`, y las propiedades `Producto.id_vendedor` y `CALIFICO.compra_verificada`. No se borra ni se renombra nada de la Entrega 2.
- **`compra_verificada` con el mismo criterio que el listado de reseñas**, que no excluye pedidos cancelados, para que el panel de reseñas y el grafo digan lo mismo.
- **Grupos con union-find en Python:** Cypher devuelve los pares de cuentas enlazadas y Python arma las componentes conexas, sin depender de GDS.
- **La consulta original se queda como está**, con su endpoint, su formato de respuesta y su pestaña en el panel. La API nueva va aparte (`/api/fraude/patrones`, `/api/fraude/alertas/<tipo>`, `/api/fraude/resumen`).
- **Sincronización en mejor esfuerzo** desde `resenas.py` y `direcciones.py`, con `database/migrations/sincronizar_grafo_fraude.py` como backfill idempotente, igual que el espejo de reseñas de la Entrega 2.

La ampliación la pidió la usuaria y se implementó el 2026-10-07.

## Justificación

- **Cada patrón cubre un caso pedido con una señal distinta**: el tiempo en una sola cuenta (`cuenta_rafaga`), la coincidencia entre cuentas (`grupo_coordinado`), la concentración en un vendedor sin compra (`sesgo_vendedor_sin_compra`) y el vínculo físico por dirección (`cuentas_vinculadas`). Así, cuando una cuenta aparece en dos patrones, son dos indicios independientes, y el resumen lo puede premiar.
- **Todos son consultas de varios saltos**, que es lo que justificó elegir una base de grafos en ADR-002. Por ejemplo, `sesgo_vendedor_sin_compra` recorre `Cuenta → Producto → Vendedor` y `cuentas_vinculadas` recorre `Cuenta → Direccion ← Cuenta → Producto ← Cuenta`.
- **Hacerlo aditivo protege lo ya entregado.** La evidencia y el informe de la Entrega 2 siguen siendo reproducibles, y la prueba `backend/scripts/prueba_fraude_ampliado.py` comprueba que `GET /api/fraude/alertas` mantiene su formato y sus resultados.
- **Union-find es poco código y no agrega infraestructura.** Con el volumen del curso (decenas de pares enlazados) no hay diferencia de rendimiento que justifique instalar GDS.

## Consecuencias

**Beneficios:**
- Se detectan campañas negativas, grupos de cualquier tamaño, cuentas que actúan solas y varias cuentas de una misma persona.
- El panel explica cada alerta en palabras (`motivo`) y con números (`evidencia`), y deja ajustar los umbrales de cada patrón.
- Cada umbral está demostrado con un escenario positivo y un control en `database/migrations/sembrar_fraude_ampliado.py` (11 escenarios). La prueba automatizada pasó 59 de 59 verificaciones el 2026-10-07.

**Limitaciones asumidas:**
- Algunas cuentas aparecen en varios patrones a la vez. Con los datos actuales, las cuentas del anillo de la Entrega 2 (4, 5, 12 y 13) salen también en `grupo_coordinado` y en `sesgo_vendedor_sin_compra`, y las de la prueba manual del 2026-09-23 (16, 18, 20 y 21) en `grupo_coordinado`. Es fraude de prueba, no falsos positivos.
- `compra_verificada` cuenta los pedidos cancelados como compra.
- El grafo puede quedar desactualizado si Neo4j falla durante una sincronización (incluida una carrera conocida al editar direcciones casi a la vez). Se corrige con `sincronizar_grafo_fraude.py`.
- Los umbrales por defecto están calibrados con la semilla del curso. `sembrar_resenas_fraude.py` borra todas las reseñas, y si se vuelve a correr hay que revisar los umbrales (en particular `min_resenas` de `sesgo_vendedor_sin_compra`).
- Si el grafo creciera mucho, los topes de candidatos por consulta (500, o 5 000 pares en `grupo_coordinado`) y la ventana deslizante de `cuenta_rafaga` (cuadrática por cuenta) habría que revisarlos. En ese escenario, GDS volvería a ser una alternativa razonable.
