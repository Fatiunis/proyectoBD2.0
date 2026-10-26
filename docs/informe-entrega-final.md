# TiendaYa — Informe de la entrega final

Bases de Datos 2 · Semana 15 · Operación, seguridad y bases vectoriales · 2026-10-21

Repositorio: este mismo. Instrucciones para levantar el sistema completo: [`README.md`](../README.md) (sección "Novedades de la entrega final" si ya se tenía el proyecto montado, o "Instalación" desde cero).

---

## 1. Distribución de responsabilidades ✏️

| Integrante | Responsabilidades en esta entrega |
|---|---|
| Diego Rueda | ✏️ |
| Marcos Pineda | ✏️ |
| Fátima Ramazzini | ✏️ |

---

## 2. Resumen de la entrega

| Requerimiento del enunciado | Qué se hizo | Dónde |
|---|---|---|
| Búsqueda semántica con representaciones vectoriales | PostgreSQL 17 + **pgvector** en un contenedor dedicado; embeddings de 384 dimensiones del nombre, categoría y descripción de cada producto; índice HNSW (coseno) | [ADR-008](decisiones/ADR-008-componente-vectorial.md), `backend/app/vectores.py`, `database/vectores/01_esquema.sql` |
| Recomendación visible en la página de producto o la principal | Franja **"Productos relacionados"** en la página de cada producto, y **búsqueda por significado** en los resultados del buscador | `ProductosSemanticos.vue`, `backend/app/blueprints/recomendaciones.py` |
| Autenticación y autorización en al menos un componente NoSQL, con roles acotados por servicio | **Redis con ACL**: `default` deshabilitado y un usuario por servicio (API, relevo del outbox, visor de solo lectura, administrador), limitado por prefijo de key y por lista de comandos | [ADR-009](decisiones/ADR-009-control-acceso-redis.md), `database/redis/users.acl` |
| Evidencia de que un usuario sin permisos no puede operar fuera de su alcance | Prueba automática, 37/37 | [`evidencia/prueba_control_acceso_redis.txt`](evidencia/prueba_control_acceso_redis.txt) |
| Diagrama de arquitectura final | Seis componentes de persistencia, sus relaciones, los usuarios con que se accede a cada uno y una tabla de control de acceso por componente | [`arquitectura-final.html`](arquitectura-final.html), [`arquitectura.md`](arquitectura.md) |
| Documento de retrospectiva | 7 decisiones que se sostienen y 5 que se replantean, cada una con su evidencia | [`retrospectiva.md`](retrospectiva.md) |

Además, como trabajo de cierre: el componente vectorial entra al **outbox** de la Entrega 3 (evento `embedding_producto`), el panel admin de Sincronización muestra la cobertura de embeddings, y el `docker-compose.yml` levanta todo lo que no es PostgreSQL ni MongoDB locales.

---

## 3. Recomendación semántica (pgvector)

### Diagnóstico

El portal solo comparaba **palabras**. Elasticsearch (Entrega 3) tolera errores de tipeo y sinónimos, pero para "regalo para alguien que ama la música" no devuelve nada, y para "reloj que mida mis pasos y el ritmo cardiaco" devuelve barras olímpicas porque coinciden "pasos" y "ritmo". Tampoco existía una forma de sugerir productos parecidos al que se está viendo.

### Decisión

Se compararon cinco alternativas (no introducir nada, pgvector en el PostgreSQL local, pgvector en un contenedor, `dense_vector` en Elasticsearch y Qdrant). Se eligió **pgvector en un contenedor dedicado** (ADR-008):

- el patrón de consulta ("k vecinos por coseno, solo activos") es un `ORDER BY embedding <=> v LIMIT k` en SQL;
- se integra con el mismo mecanismo de consistencia que ya funcionaba para Elasticsearch: proyección reconstruible desde MongoDB, recálculo al guardar, outbox si falla;
- en Docker nadie del equipo tiene que compilar la extensión para Windows.

### Implementación

- **Esquema** (`database/vectores/01_esquema.sql`, lo ejecuta el contenedor al crearse): tabla `producto_embedding (producto_id, id_categoria, activo, texto_hash, modelo, embedding vector(384), actualizado_en)`, índice `hnsw (embedding vector_cosine_ops)`, roles `vectores_app` (solo filas) y `vectores_lector` (solo lectura).
- **Embeddings** (`backend/app/vectores.py`): texto = nombre + categoría + descripción; modelo `paraphrase-multilingual-MiniLM-L12-v2` en CPU, cargado solo cuando hace falta vectorizar texto; vectores normalizados. Cada fila guarda el SHA-256 del texto y el modelo, así que recalcular es idempotente.
- **Consultas**: vecinos por distancia coseno con `hnsw.iterative_scan` (pgvector 0.8) para que el filtro de activos no deje el resultado corto. Los relacionados se **diversifican**: se descartan variantes con similitud > 0.93 a un producto ya elegido (H-029).
- **API**: `GET /api/productos/<id>/relacionados`, `GET /api/busqueda/semantica?q=`, `GET /api/vectores/estado`. pgvector devuelve ids y similitud; los datos de las tarjetas se leen de MongoDB, la fuente de verdad (un producto desactivado en Mongo no se recomienda aunque pgvector todavía lo tenga activo).
- **Sincronización**: `catalogo.py` recalcula el embedding al guardar un producto; si pgvector no responde, registra `embedding_producto` en el outbox y el relevo lo reintenta. Carga completa: `database/migrations/generar_embeddings_productos.py` (1019 productos en 7.5 s; la segunda corrida no recalcula nada).
- **Frontend**: `ProductosSemanticos.vue` en el detalle de producto y bajo los resultados de búsqueda. Si el componente responde 503, la franja no se muestra.

### Evidencia

[`evidencia/prueba_recomendacion.txt`](evidencia/prueba_recomendacion.txt) — `python backend/scripts/prueba_recomendacion.py --caida-real`, **20/20**:

| Bloque | Qué verifica | Resultado |
|---|---|---|
| R1 | Un embedding por producto del catálogo | 1019 / 1019 |
| R2 | Relacionados de un producto por categoría (24 categorías) | 90 % de la misma categoría, 100 % de la misma o afín; mediana 31 ms; diversificación: de 2 a 6 modelos distintos |
| R3 | 8 frases en lenguaje natural vs. buscador léxico | 6/8 aciertan la categoría (umbral exigido 75 %). Elasticsearch, con las mismas frases: 3/8 (en 2 no devuelve nada y en 3 devuelve otra categoría) |
| R4 | Índice HNSW | Existe y es utilizable (0.4 ms forzado); con 1019 filas el planificador prefiere el recorrido exacto (0.9 ms), lo cual es correcto (H-026) |
| R5 | Sincronización por hash | Guardar sin cambios no recalcula; cambiar la descripción sí; deshacer vuelve al original |
| R6 | Roles de pgvector | `vectores_app` no puede borrar ni crear tablas; `vectores_lector` no puede modificar |
| R7 | Caída real del contenedor | 503 `VECTORES_NO_DISPONIBLE`; detalle de producto y buscador siguen funcionando; al volver, las recomendaciones vuelven solas |

Los dos fallos de R3 ("fragancia elegante para una cena" → cuchillos; "algo para preparar el desayuno" → utensilios en vez de electrodomésticos) se muestran en la evidencia y están registrados como limitación (H-027): no se cambiaron las frases para que pasen.

---

## 4. Control de acceso (Redis ACL)

### Diagnóstico

Hasta la Entrega 3, cualquiera que llegara al puerto 6379 podía leer carritos, subir el cupo de una oferta (rompiendo la garantía de "sin sobreventa" de la Entrega 2) o borrar todo con `FLUSHALL`. Redis lo usan tres servicios con necesidades distintas: la API, el relevo del outbox y los visores.

### Decisión

Se compararon `requirepass` (una contraseña con todos los permisos), ACL de Redis, seguridad de Elasticsearch y autenticación en MongoDB (ADR-009). Se eligió **ACL de Redis con un usuario por servicio**, porque es el componente donde una operación indebida hace más daño, sus keys ya tenían prefijos por dominio, y se configura con un archivo versionado que cada integrante obtiene con `git pull`.

| Usuario | Servicio | Keys | Comandos |
|---|---|---|---|
| `default` | — | — | deshabilitado |
| `tiendaya_api` | API web | `carrito:*`, `oferta:*` | los 25 que usa el código (inventariados con `grep` sobre Python y Lua) |
| `tiendaya_relevo` | relevo del outbox | `carrito:*`, `oferta:*:reservas` | `HGET`, `HDEL`, scripts |
| `tiendaya_lectura` | RedisInsight | todas, solo lectura | `@read`, `INFO`, `SCAN` |
| `tiendaya_admin` | operación | todas | todos |

Las contraseñas están en el archivo como SHA-256. En el backend, el relevo tiene su propio cliente de Redis (`redis_relevo`).

### Evidencia

[`evidencia/prueba_control_acceso_redis.txt`](evidencia/prueba_control_acceso_redis.txt) — `python backend/scripts/prueba_control_acceso_redis.py`, **37/37**. Entre lo denegado:

- conexión sin credenciales (`NOAUTH`) y `AUTH default` (`user is disabled`);
- `tiendaya_api`: leer o escribir una key fuera de sus prefijos, `FLUSHALL`, `KEYS *`, `CONFIG GET`, `ACL LIST`, `SHUTDOWN`, y **scripts Lua** que intentan leer una key ajena o hacer `FLUSHALL` (Redis aplica la ACL también dentro del script);
- `tiendaya_relevo`: agregar al carrito, leer o subir el stock de una oferta, borrar un carrito entero, un script que hace `SET`;
- `tiendaya_lectura`: cualquier escritura, `FLUSHDB` y scripts.

**Sin regresiones** con las ACL activas: `prueba_concurrencia_oferta.py` PASS (50 reservas concurrentes, 10 aceptadas, 0 sobreventa) y `prueba_fallas_checkout.py` 40/40 (el relevo ya usa `tiendaya_relevo`).

### Hallazgo: H-025

La primera configuración dejaba `default` deshabilitado y sin permisos. Al reiniciar Redis se perdían los cambios hechos por scripts Lua: el AOF los guarda como `MULTI ... EXEC` y Redis 7.4 los vuelve a validar con los permisos de `default` al reproducirlos. Se reprodujo, se corrigió (`default` deshabilitado pero con permisos para el replay) y se verificó que lo escrito por un script sobrevive al reinicio. Detalle en ADR-009 y [`hallazgos.md`](hallazgos.md).

### Los demás componentes

Tabla completa en la sección 5 de [`arquitectura-final.html`](arquitectura-final.html): pgvector también usa roles (verificado en R6); Neo4j tiene un solo usuario (Community no tiene roles); Elasticsearch y MongoDB siguen sin autenticación, y es lo primero que haríamos a continuación con el mismo criterio.

---

## 5. Arquitectura final

[`arquitectura-final.html`](arquitectura-final.html) (abrir en el navegador) contiene:

1. **Vista general**: los 14 Blueprints agrupados por su motor principal, los seis componentes de persistencia y el usuario con que se accede a cada uno.
2. **Checkout distribuido**: las tres fases (compensación antes del COMMIT, una transacción, outbox después), con el relevo usando su usuario restringido.
3. **Recomendación y búsqueda semántica**: el flujo navegador → `recomendaciones.py` → pgvector → MongoDB, y cómo se mantienen los embeddings al día.
4. **Matriz** de qué módulo habla con qué motor, distinguiendo fuente de verdad y copias.
5. **Control de acceso** por componente, con lo que tiene y lo que no.

La versión en Mermaid y las notas de consistencia de cada integración están en [`arquitectura.md`](arquitectura.md).

---

## 6. Retrospectiva

Documento completo: [`retrospectiva.md`](retrospectiva.md). En resumen:

- **Se sostienen**: PostgreSQL como único árbitro del dinero; no migrar pagos a NewSQL; outbox + idempotencia en vez de 2PC (terminó siendo el mecanismo de toda la arquitectura); Redis + Lua para la oferta; Neo4j para fraude y no implementar la columnar; Elasticsearch como proyección con alias; pgvector como proyección (con el matiz de que el segundo PostgreSQL existe por cómo se instaló el primero).
- **Se replantean**: el producto duplicado entre MongoDB y PostgreSQL (con ≈1000 productos, `JSONB` en PostgreSQL habría resuelto la heterogeneidad sin dos fuentes de verdad); las copias a Neo4j fuera del outbox; dejar la seguridad para el final (la API no verifica el rol, y el problema del AOF apareció en la última semana); el relevo como hilo dentro de Flask; el carrito sin expiración por defecto.

---

## 7. Limitaciones conocidas

- Búsqueda semántica con un modelo pequeño en CPU: 6 de 8 frases de prueba aciertan (H-027). Complementa al buscador, no lo reemplaza.
- Dependencia pesada: PyTorch (~550 MB) y el modelo (~460 MB, se descarga la primera vez).
- Dos PostgreSQL: el transaccional en el 5432 (local) y el vectorial en el 5433 (Docker).
- Elasticsearch y MongoDB sin autenticación; Neo4j con un solo usuario; la API no verifica el rol con un token.
- Contraseñas de desarrollo en `.env.example` y `docker-compose.yml`; sin TLS entre servicios.
- El resto de limitaciones heredadas de entregas anteriores está en "Limitaciones conocidas" del [README](../README.md).

---

## 8. Cómo reproducir la evidencia

Con todo levantado según el README (contenedores, backend y embeddings generados):

```bash
# Control de acceso en Redis (no necesita el backend)
python backend/scripts/prueba_control_acceso_redis.py

# Recomendación y búsqueda semántica (R7 detiene y vuelve a levantar el contenedor vectores)
python backend/scripts/prueba_recomendacion.py --caida-real

# Regresión con las ACL activas
python backend/scripts/prueba_concurrencia_oferta.py
python backend/scripts/prueba_fallas_checkout.py      # requiere PERMITIR_FALLAS_SIMULADAS=1 en el .env
```

Para verlo en la interfaz: abrir cualquier producto (sección "Productos relacionados" al final), buscar "regalo para alguien que ama la música" (sección "Productos por significado"), y en el panel admin → Sincronización, la línea "Componente vectorial".
