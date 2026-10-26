# ADR-008 — Componente vectorial: PostgreSQL + pgvector en un contenedor dedicado

Fecha: 2026-10-21 (entrega final)

## Contexto

La entrega final pide "recomendación de productos por similitud semántica de su descripción, visible en la página de producto o en la página principal", implementada "mediante representaciones vectoriales, ya sea sobre una extensión de la base relacional o sobre un componente vectorial dedicado".

Lo que había antes no sirve para esto:

- **Elasticsearch** (Entrega 3) y el índice `$text` de MongoDB comparan **palabras**. Para la frase "regalo para alguien que ama la música" Elasticsearch devuelve 0 resultados, y para "reloj que mida mis pasos y el ritmo cardiaco" devuelve barras olímpicas, porque coincide "ritmo" y "pasos" con descripciones de pesas ([evidencia](../evidencia/prueba_recomendacion.txt), bloque R3).
- No existía ninguna función de "productos relacionados".

Datos del problema concreto:

- **1019 productos** en 24 categorías, con descripciones cortas en español. Muchos productos son **variantes** casi idénticas (la misma laptop con otra RAM, la misma playera en otra talla).
- La consulta típica es "los k vecinos más cercanos de este producto", siempre filtrando productos activos. No hay joins, ni agregaciones, ni escrituras frecuentes: los embeddings cambian solo cuando el admin edita el nombre, la categoría o la descripción.
- El equipo trabaja en Windows. PostgreSQL 18 está instalado **localmente** en cada máquina y **no trae pgvector**: instalarlo en Windows exige compilarlo con Visual Studio (`nmake`). Lo que sí corre igual en las tres máquinas es Docker.

## Alternativas consideradas

1. **No introducir un componente vectorial**: "relacionados" = otros productos de la misma categoría, ordenados por precio o ventas. Barato, pero no es similitud semántica (no cumple el requisito) y no ayuda a la búsqueda por frase.
2. **pgvector en el PostgreSQL local existente**: la opción de referencia del curso, pero obliga a cada integrante a compilar la extensión en Windows; el costo de instalación cae en tres máquinas distintas.
3. **pgvector en un contenedor dedicado** (`pgvector/pgvector:0.8.1-pg17`, puerto 5433), junto a Redis, Neo4j y Elasticsearch en el `docker-compose.yml`.
4. **`dense_vector` + kNN en el Elasticsearch existente**: cero componentes nuevos y el outbox ya lo sincroniza. Pero mezcla dos responsabilidades en el mismo índice (reindexar el buscador recalcularía o copiaría vectores), y el componente vectorial no queda como pieza identificable ni con sus propios permisos.
5. **Base vectorial dedicada no relacional (Qdrant)**: muy buena para esto, pero es una tecnología, un lenguaje de consulta y una API más que el equipo tiene que operar y defender, para 1019 vectores.

## Decisión

Alternativa 3: **PostgreSQL 17 + pgvector 0.8.1 en el contenedor `vectores`**, con la tabla `producto_embedding` (`vector(384)`), un índice **HNSW** con distancia coseno y roles de mínimo privilegio. Los embeddings los calcula el backend con el modelo **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** (multilingüe, 384 dimensiones, corre en CPU, sin API externa).

El componente es una **proyección derivada**, igual que Elasticsearch y Neo4j: la fuente de verdad del catálogo sigue siendo MongoDB, y la tabla se reconstruye entera con `database/migrations/generar_embeddings_productos.py`.

## Justificación

- **Patrón de consulta.** "k vecinos por coseno, solo activos, opcionalmente de la misma categoría" es exactamente `ORDER BY embedding <=> :v LIMIT k` con un `WHERE`. pgvector 0.8 agrega `hnsw.iterative_scan`, que sigue buscando en el índice cuando el filtro descarta vecinos, así que el `LIMIT` se llena aunque haya productos inactivos.
- **Consistencia.** Se usa el mismo mecanismo que ya está probado para Elasticsearch: al guardar un producto en el admin, `catalogo.py` recalcula el embedding en el acto, y si pgvector no responde queda un evento `embedding_producto` en el outbox que el relevo reintenta. Cada fila guarda el SHA-256 del texto y el modelo con que se calculó, así que recalcular es idempotente: guardar un producto sin cambiar su texto no vuelve a vectorizar. La ventana de inconsistencia aceptada: un producto recién editado puede recomendarse con su descripción anterior hasta que el relevo lo procese (15 s en el peor caso normal).
- **Costo operativo.** Es PostgreSQL: el equipo ya sabe SQL, roles, `EXPLAIN` y pgAdmin. Al ir en Docker, ponerlo en marcha es `docker compose up -d`; nadie compila nada. El modelo se descarga solo la primera vez (~460 MB) y vectorizar los 1019 productos tarda 7.5 s en CPU.
- **Escalabilidad.** Para 1019 vectores el recorrido exacto cuesta 0.9 ms y el planificador lo prefiere al HNSW (0.4 ms forzado), con 100 % de recall. El índice HNSW ya está creado y verificado (bloque R4 de la evidencia): a medida que el catálogo crezca a decenas de miles de productos, el planificador lo empezará a usar sin cambiar código.
- **Separación de responsabilidades.** Una instancia aparte del PostgreSQL transaccional: un problema en los vectores (o recalcularlos enteros) no compite por recursos con el checkout, y sus roles se administran por separado.

### Decisiones de diseño dentro del componente

- **Texto que se vectoriza:** nombre + categoría + descripción. Los atributos técnicos (RAM, talla) se excluyen a propósito: los resuelven mejor las facetas del buscador y aquí meterían ruido numérico.
- **Modelo:** se comparó con `intfloat/multilingual-e5-small` (mismo tamaño, entrenado para recuperación pregunta→documento). Los dos aciertan en las mismas consultas de prueba salvo una cada uno, y MiniLM da mejores "productos parecidos", que es la función principal. Se quedó MiniLM.
- **Diversificación:** sin ella, los relacionados de una laptop eran 4 variantes de la misma laptop. Se piden 5× candidatos y se descarta uno si su similitud con otro ya elegido supera 0.93 (medido sobre el catálogo: las variantes quedan entre 0.93 y 0.996). Con eso, los 6 relacionados de PROD-0005 pasan de 2 a 6 modelos distintos. `?diversificar=0` lo apaga para comparar.
- **Carga perezosa del modelo:** los relacionados solo comparan vectores ya guardados y no cargan el modelo; el servidor arranca igual de rápido que antes.

## Consecuencias

**Beneficios:**
- Página de producto con "Productos relacionados": 90 % de las recomendaciones son de la misma categoría y 100 % de la misma o de una afín (bloque R2); mediana de 31 ms por petición.
- Búsqueda por frase que complementa al buscador léxico: 6 de 8 frases de prueba encuentran la categoría esperada, contra 3 de 8 de Elasticsearch con las mismas frases (en 2 no devuelve nada y en 3 devuelve otra categoría).
- Si el contenedor se cae, el portal sigue funcionando: el endpoint responde `503 VECTORES_NO_DISPONIBLE`, la franja de recomendaciones se oculta, y al volver el contenedor todo se recupera solo (bloque R7).

**Limitaciones asumidas:**
- **Calidad del modelo pequeño:** "fragancia elegante para una cena" devuelve cuchillos (lo arrastra "cena") y "algo para preparar el desayuno" devuelve utensilios en vez de electrodomésticos. Se documenta como tasa de acierto (6/8), no se ajustaron las consultas para que pasen. Un modelo más grande o una búsqueda híbrida (léxica + vectorial) lo mejorarían.
- **Dependencia pesada:** `sentence-transformers` trae PyTorch (unos 550 MB instalado en el `venv`, versión CPU) y el modelo ocupa unos 460 MB en la caché de Hugging Face (`~/.cache/huggingface`).
- **Un motor más que levantar:** el `docker-compose.yml` pasa a cinco servicios.
- **Dos PostgreSQL:** quien inspeccione los datos debe recordar que los vectores están en el 5433, no en el 5432.

## Cuándo se replantearía

- Si el catálogo pasara de ~1 millón de vectores o se necesitara filtrar por muchos atributos a la vez, evaluar una base vectorial dedicada (Qdrant) o el `dense_vector` de Elasticsearch para hacer búsqueda híbrida en una sola consulta.
- Si el equipo pudiera instalar pgvector en el PostgreSQL principal (por ejemplo, en un despliegue en Linux), moverlo ahí ahorraría un servicio, a cambio de compartir recursos con el checkout.
