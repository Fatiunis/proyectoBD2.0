# ADR-004 — Motor de búsqueda (Elasticsearch) para el catálogo

Fecha: 2026-10-05 (Entrega 3)

## Contexto

Hasta la Entrega 2, la búsqueda del catálogo usaba el índice de texto de MongoDB (`idx_texto_busqueda`, `$text` con stemming en español), sobre los 1015 productos de la semilla (15 originales + 1000 de la semilla masiva; la versión inicial de este ADR decía 1019; cifra corregida el 2026-10-06 contra MongoDB). Funciona con palabras completas y bien escritas, pero no cumple lo que pide la Entrega 3: tolerancia a variaciones, relevancia y filtros facetados. Mismas búsquedas, contra el sistema real, el 5 de octubre de 2026:

| Búsqueda | MongoDB `$text` | Qué buscaba el usuario |
|---|---|---|
| `laptp` | **0** resultados | laptops (error de tipeo) |
| `audifnos` | **0** | audífonos |
| `celulr` | **0** | celulares |
| `lapt` | **0** | laptops (palabra a medio escribir) |
| `auriculares` | **0** | audífonos (sinónimo) |
| `celular` | 14, **todos tablets** "Wi-Fi + Celular", ningún celular | celulares |

Los motivos son estructurales, no de configuración:

- `$text` no tiene coincidencia aproximada (fuzzy), ni por prefijo, ni sinónimos.
- Su relevancia (`textScore`) no se puede ajustar por campo ni combinar con otras señales. La categoría "Celulares" no pesa más que la palabra "Celular" dentro del nombre de una tablet.
- Las facetas habría que calcularlas con agregaciones aparte, una por faceta, sobre el mismo filtro de texto.

## Alternativas consideradas

1. **No introducir cambios**: seguir con `$text` de MongoDB y agregar facetas con `$facet` de su marco de agregación.
2. **Búsqueda de texto completo de PostgreSQL** (`tsvector` + `pg_trgm` para similitud), sobre una tabla de productos.
3. **Atlas Search** (motor Lucene integrado en MongoDB).
4. **Elasticsearch** (u OpenSearch, equivalente), como índice de búsqueda dedicado y alimentado desde MongoDB.

## Decisión

Alternativa 4: **Elasticsearch 8.15**, un nodo en `docker-compose.yml`. El índice es una **proyección de solo lectura** de la colección `productos` de MongoDB, que sigue siendo la fuente de verdad del catálogo. Se consulta siempre por un **alias** (`productos`) que apunta a un índice versionado (`productos_v<fecha>`), así que reindexar no corta el servicio.

## Justificación

- **Patrón de consulta**: la búsqueda de texto libre con errores de tipeo, sinónimos, prefijos y relevancia ajustable por campo es el caso de uso para el que Lucene fue construido. Una sola consulta devuelve los resultados ordenados por relevancia (BM25), las facetas (agregaciones `terms` y `range`) y la sugerencia de corrección (`phrase suggester`).
- **Frente a la alternativa 1**: `$facet` resolvería las facetas, pero no la tolerancia a errores, los sinónimos ni la relevancia, que son la mitad del requerimiento.
- **Frente a la alternativa 2**: `pg_trgm` da similitud por trigramas, pero el catálogo **no vive en PostgreSQL** desde la Entrega 1 (sus atributos variables están en MongoDB). Habría que replicarlo en una tabla, con el mismo problema de sincronización que Elasticsearch, y con menos capacidades: sin analizadores configurables por campo, sin sugerencias y con facetas a mano.
- **Frente a la alternativa 3**: Atlas Search solo existe en MongoDB Atlas (la nube); la MongoDB Community que usa el proyecto en local no lo trae.
- **Consistencia**: buscar tolera datos levemente desactualizados (un precio o un stock de hace unos segundos). La fuente de verdad sigue siendo MongoDB para el catálogo y PostgreSQL para el stock. El índice se actualiza al guardar un producto en el admin y, para el stock, mediante el outbox del checkout (ver [`docs/estrategia-consistencia-checkout.md`](../estrategia-consistencia-checkout.md)). Si se pierde, se reconstruye entero con un script.
- **Escalabilidad**: las búsquedas dejan de cargar a MongoDB. El índice se puede repartir en shards y réplicas si el catálogo crece (hoy usa 1 shard y 0 réplicas, que es lo correcto para un nodo).
- **Costo operativo**: un contenedor más, con una JVM (limitada a 512 MB de heap en `docker-compose.yml`), y un script de indexación que hay que correr al montar el proyecto. Es el costo más alto de las cuatro alternativas, aceptado porque es la única que cubre el requerimiento completo.

## Diseño del índice (mapping deliberado)

Definición completa en [`database/elasticsearch/productos_indice.json`](../../database/elasticsearch/productos_indice.json). Cada decisión responde a un problema concreto del catálogo:

| Campo / pieza | Definición | Por qué |
|---|---|---|
| `dynamic: strict` | Rechaza campos no declarados | Un campo nuevo no puede colarse con un tipo adivinado por Elasticsearch: el mapping es explícito o falla |
| Analizador `es_texto` (indexar) | `standard` + `lowercase` + `asciifolding` + stop words en español + `stemmer_override` + `light_spanish` | "Audífonos", "audifonos" y "AUDÍFONOS" se indexan igual (sin acentos ni mayúsculas); "mochilas" y "mochila" comparten raíz |
| Analizador `es_texto_busqueda` (buscar) | Lo mismo más `synonym_graph` | Los sinónimos se aplican **solo al buscar**: los documentos indexados no cambian, así que un sinónimo nuevo no obliga a reindexar el catálogo, solo a actualizar la configuración del índice. `synonym_graph` maneja sinónimos de varias palabras ("teléfono móvil") |
| `plurales_prestados` (`stemmer_override`) | `laptops => laptop`, `tablets => tablet`… | El stemmer en español no sabe quitar la "s" a plurales en inglés: sin esto, "laptop" no coincidía con la categoría "Laptops" |
| `nombre.autocompletado` | `edge_ngram` 2-20 al indexar, sin n-gramas al buscar | Autocompletado por prefijo ("lapt" → Laptop) sin inflar la consulta |
| `nombre.sugerencia` | Solo minúsculas y sin acentos, **sin stemming** | El corrector ("¿quisiste decir?") debe proponer palabras reales, no raíces como "audifon" |
| `nombre.orden` | `keyword` con normalizador | Desempate alfabético estable |
| `categoria.nombre`, `marca`, `vendedor.nombre_comercial` | `keyword` | Facetas (`terms`): necesitan el valor exacto, no tokens |
| `atributos` | `flattened` | Cada categoría tiene atributos distintos (unas 125 claves distintas en el catálogo: la versión inicial decía 126 y se midieron 124 el 2026-10-06; varía con los atributos personalizados que se cargan desde el admin). Con mapeo dinámico, cada clave sería un campo nuevo (*mapping explosion*); `flattened` los guarda en un solo campo que igual se puede filtrar por clave |
| `precio_base` | `scaled_float` (factor 100) | Precio con 2 decimales exactos, más compacto que `double`, para filtros de rango y orden |
| `imagen_portada` | `keyword` con `index: false` | Solo se muestra; no se busca ni se agrega por él |

## Cómo se consulta

`GET /api/busqueda` ([`backend/app/busqueda_es.py`](../../backend/app/busqueda_es.py)) arma un `bool.should` que suma varias señales de relevancia:

- `multi_match` con `fuzziness: AUTO` sobre nombre (×3), categoría (×2), marca (×2) y descripción: tolera errores de tipeo.
- Puntaje fijo (`constant_score`, 25) si lo buscado coincide con el nombre de una **categoría**. Como "Celulares" se repite en sus 60 productos, su IDF es bajo; sin esta señal, una tablet "Wi-Fi + Celular" le ganaba a un celular de verdad.
- `match_phrase` sobre el nombre, solo con 2 o más palabras: premia la frase exacta. Con una palabra, solo volvería a contar la misma coincidencia.
- El campo de autocompletado, con poco peso (palabras a medio escribir), y el SKU exacto (×10).

Las facetas (categoría, marca, tienda y rangos de precio) son **disyuntivas**: los filtros elegidos van en `post_filter`, y cada agregación aplica los filtros de las *otras* facetas. Así, elegir "Logitech" no hace desaparecer las demás marcas de la lista, pero sí recalcula las tiendas y los precios.

Mismas búsquedas que en el Contexto, ahora con Elasticsearch ([evidencia completa](../evidencia/prueba_buscador.txt)):

| Búsqueda | Elasticsearch |
|---|---|
| `laptp` | 106 resultados, primero "Laptop triple AAA", sugiere "laptop" |
| `audifnos` | 50 resultados, primero unos Audio-Technica ATH-M50x, sugiere "audifonos" |
| `celulr` | 74 resultados, primero iPhone 13, sugiere "celular" |
| `lapt` (autocompletado) | Laptop triple AAA, Laptop Gamer 16 Pulgadas… |
| `auriculares` | Audífonos (por sinónimo) |
| `celular` | Los 5 primeros son de la categoría Celulares |

## Consecuencias

**Beneficios:**
- Búsqueda tolerante a errores, sinónimos y prefijos, con relevancia ajustada al catálogo real y facetas en una sola consulta.
- Si Elasticsearch no está disponible, la búsqueda **se degrada** (no se rompe): `GET /api/busqueda` responde `503 BUSCADOR_NO_DISPONIBLE`, el frontend repite la búsqueda contra el `$text` de MongoDB y le avisa al usuario que es una búsqueda simplificada.
  - *Nota (2026-10-06):* la decisión no cambia, pero se precisó cuándo se responde `503`. Antes, cualquier error de Elasticsearch (incluido un `400` porque la consulta pedía una página más allá de su ventana de 10 000 resultados) se trataba como una caída y mandaba al respaldo con el motor funcionando. Ahora el `503 BUSCADOR_NO_DISPONIBLE` es solo para conexión, timeout, índice o alias inexistente (`404`), `401`/`403`, `429` y `5xx`; un `400` de Elasticsearch se responde `400 BUSQUEDA_NO_VALIDA`, sin respaldo. Las páginas fuera de esa ventana responden `200` con `items` vacíos (con el total y las facetas reales), `total_paginas` cuenta solo las páginas alcanzables, y un `precio_min`/`precio_max` no finito (`nan`, `inf`) responde `400`. Ver [H-002 y H-003](../hallazgos.md).
- Reindexar (por ejemplo, para cambiar el mapping) no corta el servicio: se construye un índice nuevo, se verifica la cantidad de documentos y recién entonces se mueve el alias.

**Limitaciones asumidas:**
- **Un componente más que operar**: hay que levantar el contenedor y correr `indexar_productos_elasticsearch.py` al montar el proyecto, y otra vez si se cambia el mapping o si la migración completa de MongoDB recrea el catálogo.
- **Consistencia eventual** con MongoDB: un producto editado en el admin se reindexa en el acto, o por el outbox si Elasticsearch no respondía. El stock que muestra el buscador puede tener unos segundos de atraso tras una compra.
- **Sin seguridad**: el contenedor corre con `xpack.security.enabled=false`. El control de acceso a los componentes NoSQL es requisito de la entrega final.
- **Los sinónimos y plurales están escritos a mano** en el JSON del índice. Para agregar uno, lo más simple es editar el JSON y volver a correr el script de indexación, que no corta el servicio.
- **Algunas categorías no tienen el atributo `marca`** (por ejemplo, Laptops), así que en esas búsquedas no aparece la faceta de marca.
