# ADR-002 — Base de grafos vs. columnar para los dos requerimientos de análisis de la Entrega 2

Fecha: 2026-09-13

## Contexto

La Entrega 2 plantea dos necesidades de análisis independientes, cada una candidata a un motor de base de datos distinto al modelo relacional:

1. **Detección de fraude en reseñas**: identificar conjuntos de cuentas que se califican entre sí de forma reiterada sobre los mismos productos — un patrón de manipulación coordinada del catálogo (reseñas falsas para inflar la reputación de un vendedor).
2. **Panel de tendencias de venta**: visualizar ventas por intervalos de tiempo e identificar productos en ascenso de demanda.

El enunciado del curso exige evaluar de forma comparativa una base de grafos y una base columnar frente a ambos problemas, y seleccionar al menos una de las dos familias para implementación real.

Al momento de esta decisión, TiendaYa no tenía ningún sistema de reseñas (ni modelo de datos ni UI) — construirlo formaba parte del alcance necesario para poder analizar fraude, sin importar qué motor se eligiera para el análisis en sí.

## Alternativas consideradas

1. **No introducir ningún componente nuevo** (mantener el análisis, si se hiciera, sobre PostgreSQL con SQL puro).
2. **Base columnar (Cassandra/ScyllaDB)** para el panel de tendencias de venta, apoyada en los datos de `pedidos`/`lineas_pedido` que ya existen en Postgres.
3. **Base de grafos (Neo4j)** para la detección de fraude en reseñas, requiriendo construir primero el sistema de reseñas desde cero.

## Decisión

Se implementa **Neo4j** para la detección de fraude en reseñas. **No se implementa** la base columnar para el panel de tendencias de venta en esta entrega; se documenta más abajo bajo qué condiciones se justificaría incorporarla más adelante.

## Justificación

**Por qué grafos para fraude en reseñas — patrón de consulta:** el problema es, por definición, de relaciones entre entidades (cuentas que comparten productos calificados). Expresar "cuentas conectadas entre sí a través de 2+ saltos con ciertas condiciones en el camino" es exactamente el caso de uso nativo de una base de grafos — un `MATCH` de Cypher con varios saltos encadenados resuelve en una sola consulta declarativa lo que en SQL requeriría auto-joins sucesivos de complejidad creciente por cada salto adicional. En la implementación real, la consulta de 3 saltos (`Cuenta-CALIFICO->Producto<-CALIFICO-Cuenta` repetido para formar un trío) identificó correctamente, contra datos de prueba con 11 cuentas y 18 productos, el anillo de fraude sembrado (4 cuentas, 4 productos compartidos, calificación uniforme de 5 estrellas en una ventana de menos de 2 horas) sin ningún falso positivo, y excluyó correctamente un par de control que solo compartía 2 productos.

**Por qué NO columnar para tendencias de venta — costo operativo vs. patrón de consulta:** el volumen real de `pedidos`/`lineas_pedido` de TiendaYa (un proyecto de curso, no un sistema en producción con tráfico real) es de decenas o cientos de filas. PostgreSQL agrega ese volumen sin esfuerzo con `GROUP BY`/funciones de ventana sobre índices por fecha — no hay ningún patrón de consulta hoy que Postgres no pueda resolver con latencia aceptable. Cassandra/ScyllaDB justifican su costo operativo (un motor adicional a desplegar, operar y mantener consistente) cuando: (a) el volumen de escrituras de eventos de venta supera lo que un único Postgres puede absorber cómodamente (referencia: decenas de millones de filas/día), (b) hay ingestión distribuida desde múltiples regiones/fuentes que necesita alta disponibilidad de escritura sin coordinación central, o (c) los patrones de consulta están fijos de antemano y se pueden modelar como tablas desnormalizadas por partición (el modelo de datos "query-first" de Cassandra). Ninguna de estas tres condiciones se cumple hoy en TiendaYa.

**Consistencia:** ninguna de las dos alternativas nuevas participa en el checkout transaccional — ambas son analíticas/de solo lectura sobre datos ya persistidos en otro lado, así que no hay diferencia entre ellas en términos de consistencia transaccional. Donde sí hay diferencia es en la consistencia del propio dato analítico: el grafo de Neo4j se sincroniza de forma síncrona (mejor esfuerzo, sin 2PC) en el mismo request que crea la reseña en Mongo, así que queda al día casi en tiempo real; una base columnar para ventas normalmente se alimenta por un pipeline de ingesta separado (batch o streaming), lo que introduce una ventana de latencia adicional que hoy no se necesita.

**Escalabilidad:** Neo4j escala razonablemente para el tamaño de grafo de este dominio (cuentas × productos × reseñas de un catálogo de curso, órdenes de magnitud muy por debajo de donde un grafo empieza a requerir particionamiento). Cassandra está diseñada para escalar horizontalmente mucho más allá de lo que este proyecto necesita — es una capacidad que hoy no se aprovecha y que solo añade complejidad operativa sin beneficio medible.

## Consecuencias

**Beneficios:**
- La detección de fraude queda expresada como una consulta declarativa natural (Cypher), en vez de SQL recursivo o lógica de traversal implementada a mano en Python.
- El grafo es incremental: cada reseña nueva agrega un nodo/relación sin necesidad de recalcular nada del resto del grafo.
- Se evita el costo de operar un cuarto motor de persistencia (Cassandra) cuando ningún patrón de consulta real lo justifica todavía.

**Limitaciones asumidas:**
- Neo4j es un motor nuevo para el equipo y para el stack del proyecto — no había precedente de configuración/operación antes de esta entrega (a diferencia de Postgres/Mongo, ya maduros en el proyecto).
- La sincronización Mongo → Neo4j no es transaccional: si Neo4j no está disponible en el momento de crear una reseña, el grafo queda desactualizado respecto a Mongo hasta la siguiente escritura exitosa (se documenta como limitación conocida, mismo criterio ya aceptado entre Postgres y Mongo en el proyecto).
- El panel de tendencias de venta queda sin implementar en esta entrega. Si el volumen de pedidos creciera significativamente (ver condiciones (a)-(c) arriba), esta decisión debería revisitarse — probablemente primero explorando funciones de ventana/particionamiento nativo de PostgreSQL antes de introducir un motor columnar nuevo, dado que ninguna de las condiciones que lo justificarían se cumple hoy.
