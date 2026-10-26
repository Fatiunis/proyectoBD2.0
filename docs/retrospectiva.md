# TiendaYa — Retrospectiva de las decisiones de arquitectura

Entrega final · 2026-10-21

Este documento revisa, componente por componente, qué decisiones de arquitectura **sostendríamos** si empezáramos TiendaYa otra vez y cuáles **replantearíamos**, con la evidencia que juntamos durante el semestre. Cada decisión original está en su registro (`docs/decisiones/ADR-*.md`) y cada problema mencionado, en [`hallazgos.md`](hallazgos.md).

El criterio con que juzgamos cada decisión es el mismo del curso: consistencia, patrón de consulta, escalabilidad y costo operativo, aplicados a lo que TiendaYa es de verdad (≈1000 productos, 3 desarrolladores, todo corriendo en laptops con Windows), no a un sistema hipotético.

## Resumen

| # | Decisión | Veredicto |
|---|---|---|
| 1 | PostgreSQL como única fuente de verdad del dinero (pedidos, pagos, inventario) y checkout en un procedimiento atómico | **Se sostiene** |
| 2 | No migrar pagos a NewSQL (ADR-005) | **Se sostiene** |
| 3 | Outbox + clave de idempotencia en vez de 2PC (Entrega 3) | **Se sostiene** |
| 4 | Redis + scripts Lua para la oferta de inventario limitado (ADR-003) | **Se sostiene** |
| 5 | Neo4j para fraude y no implementar la base columnar (ADR-002, ADR-007) | **Se sostiene** |
| 6 | Elasticsearch como proyección detrás de un alias (ADR-004) | **Se sostiene** |
| 7 | pgvector en un contenedor aparte, como proyección (ADR-008) | **Se sostiene**, con matices |
| 8 | Catálogo en MongoDB **duplicado** con la tabla `productos` de PostgreSQL | **Se replantea** |
| 9 | Copias a Neo4j "de mejor esfuerzo", fuera del outbox | **Se replantea** |
| 10 | Seguridad dejada para la última entrega (sin autenticación en la API ni en los motores) | **Se replantea** |
| 11 | Relevo del outbox como hilo dentro de Flask | **Se replantea** |
| 12 | Carrito sin expiración por defecto (ADR-006) | **Se replantea** |

---

## Decisiones que sostendríamos

### 1. PostgreSQL decide si hubo compra

**Qué decidimos.** Usuarios, direcciones, pedidos, líneas, pagos e inventario en PostgreSQL normalizado (3FN). El checkout es `sp_procesar_checkout`: una transacción con `SELECT ... FOR UPDATE` sobre el inventario, que inserta pedido, líneas y pago y descuenta stock, o no hace nada.

**Por qué lo sostenemos.** Es el único lugar del sistema donde un error cuesta dinero, y ahí la garantía ACID no tiene sustituto. Todo lo demás de la arquitectura se apoya en esta decisión: la estrategia de consistencia de la Entrega 3 funciona *porque* hay un único motor que dice "sí hubo compra" y los demás son copias. En la prueba de fallas (40/40, [evidencia](evidencia/prueba_fallas_checkout.txt)) ningún escenario produjo un pedido duplicado ni un cobro sin pedido, ni siquiera con Redis, MongoDB o Elasticsearch fallando después del COMMIT.

### 2. Pagos se quedan en PostgreSQL (no NewSQL)

**Qué decidimos.** En la evaluación opcional de la Entrega 3 (ADR-005) no migrar pagos a un motor NewSQL.

**Por qué lo sostenemos.** El argumento sigue intacto: separar `pagos` del pedido y del inventario rompería la atomicidad que justifica el punto 1, y migrar el núcleo transaccional completo agrega operación de un clúster, reintentos por serialización y latencia por escritura a cambio de capacidades (multirregión, RPO 0 sin failover manual) que TiendaYa no necesita. Las condiciones bajo las que sí migraríamos siguen documentadas en el ADR; ninguna se cumplió durante el proyecto.

### 3. Outbox e idempotencia en lugar de 2PC

**Qué decidimos.** En la Entrega 3: clave de idempotencia en el checkout, compensación de las reservas de oferta antes del COMMIT y, después del COMMIT, eventos en una tabla `eventos_sincronizacion` (outbox) que se aplican en el acto y que un relevo reintenta con espera creciente.

**Por qué lo sostenemos.** Fue la decisión que más rindió. Nació para el checkout y terminó siendo el mecanismo de toda la arquitectura: la reindexación en Elasticsearch al editar un producto (Entrega 3) y el recálculo de embeddings en pgvector (entrega final) se agregaron como **un tipo de evento más**, sin diseñar nada nuevo. La ventana de inconsistencia quedó medida (MongoDB se corrigió solo en 18-20 s tras una falla simulada) en vez de supuesta.

### 4. Redis y Lua para la oferta de inventario limitado

**Qué decidimos.** Cupo, precio y reservas de la oferta en Redis; cada operación (crear, reservar, consumir, compensar, confirmar) es un script Lua atómico; sin bloqueos en la aplicación (ADR-003).

**Por qué lo sostenemos.** La prueba de concurrencia lo demostró desde la Entrega 2 y lo volvió a demostrar con las ACL de la entrega final: 50 solicitudes simultáneas por 10 unidades → 10 vendidas, 40 rechazadas, 0 sobreventa. Hacerlo en PostgreSQL con `FOR UPDATE` habría funcionado, pero concentrando miles de solicitudes de una oferta en la misma fila del inventario que usa el checkout normal; separar el cupo de la oferta del inventario real fue lo correcto.

### 5. Neo4j para fraude; sin base columnar

**Qué decidimos.** Implementar la familia de grafos para la detección de fraude y documentar cuándo se justificaría la columnar para tendencias de venta (ADR-002). Después de la Entrega 3 ampliamos el mismo grafo con vendedores, direcciones y compra verificada, y cuatro patrones nuevos (ADR-007).

**Por qué lo sostenemos.** Que la ampliación entrara **sin cambiar el modelo existente** —solo agregando nodos y relaciones— es la mejor prueba de que el grafo era el modelo correcto: "cuentas distintas que comparten dirección y califican al mismo vendedor" son recorridos de 3-4 saltos que en SQL serían autojoins difíciles de leer y de mantener. Sobre la columnar: con unos cientos de pedidos de prueba, cualquier panel de tendencias se responde con un `GROUP BY` en PostgreSQL en milisegundos; las condiciones de ADR-002 (volumen de eventos que no quepa en el relacional, escrituras masivas append-only) no se dieron. No implementar algo cuando no se justifica también es una decisión que sostenemos.

### 6. Elasticsearch como proyección con alias

**Qué decidimos.** El índice es una proyección de solo lectura de MongoDB, consultada por un alias que apunta a un índice versionado, con un mapping propio (analizador español, sinónimos, autocompletado) y respaldo en el `$text` de Mongo si el motor no responde (ADR-004).

**Por qué lo sostenemos.** Cambiamos el mapping varias veces (el último commit agregó un sinónimo) y reindexar nunca cortó el buscador. Tratarlo como proyección reconstruible nos permitió no preocuparnos por respaldarlo y degradar con gracia cuando falla.

### 7. pgvector en un contenedor aparte

**Qué decidimos.** PostgreSQL 17 + pgvector en Docker, con embeddings como proyección derivada de MongoDB y sincronizados por el outbox (ADR-008).

**Por qué lo sostenemos, y con qué matices.** La forma de integrarlo —proyección, hash del texto para no recalcular, outbox para los fallos— es la misma que ya había funcionado con Elasticsearch, y eso hizo que la entrega final fuera sobre todo reutilización. El matiz: tener **dos PostgreSQL** (5432 local y 5433 en Docker) es una consecuencia de una decisión anterior, no de un mérito técnico: se debe a que el PostgreSQL principal está instalado localmente en Windows, donde compilar pgvector es costoso. Si el PostgreSQL principal hubiera estado en Docker desde la fase inicial (ver punto 10), pondríamos la extensión ahí y nos ahorraríamos un servicio. Con 1000 productos el recorrido exacto es más rápido que el índice HNSW; el índice está para cuando el catálogo crezca, y lo dejamos verificado, no supuesto.

---

## Decisiones que replantearíamos

### 8. El producto vive en dos lugares: MongoDB y la tabla `productos` de PostgreSQL

**Qué decidimos.** En la Entrega 1 migramos el catálogo a MongoDB, pero dejamos `productos` e `inventario` en PostgreSQL porque `sp_procesar_checkout` y las `lineas_pedido` los referencian. El documento de Mongo guarda `id_sql_origen` como llave foránea lógica.

**Qué salió mal.** Dos fuentes de verdad para el mismo dato. El admin edita el precio en Mongo, pero el checkout cobra el de PostgreSQL; el stock hay que copiarlo en las dos direcciones; y una oferta creada contra el precio de Mongo puede fallar al pagar contra el de PostgreSQL (todo esto está en "Limitaciones conocidas" del README). Varios hallazgos (H-015, stock desfasado) nacieron de aquí, y buena parte del outbox existe para mantener copias que no deberían existir.

**Qué haríamos distinto.** Una de dos, decidido en la Entrega 1 y no después:

- **Opción A (la que elegiríamos):** quedarnos con el producto en PostgreSQL y modelar los atributos variables con una columna **`JSONB` + índice GIN**, y el historial de cambios como una tabla de eventos (`producto_eventos`, solo `INSERT`). Cubre los dos problemas de la Entrega 1 (heterogeneidad de atributos y reconstrucción por fecha) sin un segundo motor y con integridad referencial real hacia las líneas de pedido. El enunciado valora igual la justificación de *no* migrar (sección 5.5), y con ≈1000 productos el argumento de escala de MongoDB no aplicaba.
- **Opción B:** si se migra a MongoDB, migrar **de verdad**: que el checkout lea precio y nombre del catálogo de Mongo y que PostgreSQL guarde solo el inventario y una copia inmutable del precio en la línea de pedido (que es lo que en realidad necesita un pedido histórico).

Lo que no volveríamos a hacer es quedarnos a medias.

### 9. Las copias a Neo4j son "de mejor esfuerzo", fuera del outbox

**Qué decidimos.** En la Entrega 2, al crear una reseña se escribe en Mongo y luego, en el mismo request, en Neo4j; si Neo4j falla solo se registra una advertencia. Las direcciones (fraude ampliado) siguieron el mismo patrón. El outbox llegó después, en la Entrega 3, y no volvimos atrás.

**Qué salió mal.** Hay dos formas de sincronizar en el mismo sistema: el checkout, el buscador y pgvector reintentan; Neo4j no. Una reseña creada con Neo4j caído **nunca** llega al grafo salvo que alguien corra `sincronizar_grafo_fraude.py`, y quedó registrada una carrera entre dos ediciones de direcciones del mismo usuario (H-020). Para un sistema de detección de fraude, perder justo los eventos que llegan cuando hay problemas es un mal compromiso.

**Qué haríamos distinto.** Pasar `resenas.py` y `direcciones.py` al outbox con eventos idempotentes (`MERGE`), igual que los demás motores. El costo es bajo porque el mecanismo ya existe; no lo hicimos por orden de entregas, no por una razón técnica.

### 10. La seguridad se dejó para la última entrega

**Qué decidimos.** Seguir el orden del enunciado: control de acceso en la entrega final. Mientras tanto, Redis y Elasticsearch corrían sin autenticación, y la API identifica al usuario con `id_usuario` y `rol_solicitante` que manda el propio navegador, sin verificación del lado del servidor.

**Qué salió mal.** Dos cosas concretas:

1. **Configurar el ACL al final destapó un problema real tarde.** Al deshabilitar el usuario `default` de Redis, los cambios hechos por scripts Lua se perdían al reiniciar el contenedor (el AOF se reproduce con los permisos de `default`; [H-025](hallazgos.md), ADR-009). Lo detectamos porque lo probamos, pero fue en la última semana; si el ACL hubiera estado desde la Entrega 2, junto con los scripts Lua, habría aparecido en la primera prueba de reinicio.
2. **Las ACL de la base no protegen de la API.** Hoy cualquiera puede llamar a un endpoint de administrador mandando `rol_solicitante=administrador`. La ACL de Redis impide que el servicio de carrito haga `FLUSHALL`, pero no impide que un usuario haga, a través de la API legítima, algo que su rol no debería permitir.

**Qué haríamos distinto.** Desde la fase inicial: sesión firmada (JWT o cookie de sesión de Flask) y el rol leído del token, no del cuerpo de la petición; cada motor en Docker con usuario por servicio desde que se incorpora; y un rol de aplicación en PostgreSQL en vez del superusuario `postgres`. La seguridad es más barata cuando crece con el sistema que cuando se agrega encima.

### 11. El relevo del outbox es un hilo dentro de Flask

**Qué decidimos.** En la Entrega 3, el relevo corre como un hilo en el mismo proceso del backend (`iniciar_relevo` en `backend/main.py`).

**Qué salió mal.** Si Flask está detenido, nadie reintenta; con el recargador de Flask en modo desarrollo hubo que cuidar que el hilo arrancara una sola vez; y escalar la API a varios procesos multiplicaría los relevos (lo tolera `FOR UPDATE SKIP LOCKED`, pero no es el diseño que querríamos).

**Qué haríamos distinto.** Un proceso aparte (`python -m app.relevo`) como servicio más del `docker-compose.yml`. La entrega final ya dio el primer paso: el relevo entra a Redis con su propio usuario (`tiendaya_relevo`), así que separarlo en otro proceso ya no exige tocar permisos.

### 12. Carrito sin expiración por defecto

**Qué decidimos.** Después de la Entrega 3 el equipo cambió el valor por defecto de `CARRITO_TTL_SEGUNDOS` a `0` (ADR-006), para que el comprador no pierda su carrito.

**Por qué lo replanteamos.** La razón de producto era válida, pero el valor por defecto quedó en contra del requerimiento de la Entrega 2 ("expiración automática por inactividad") y hay que acordarse de cambiarlo para demostrarlo (H-016). Mejor solución: expirar por defecto el carrito de Redis a los 30 días de inactividad (sigue siendo "persistente" para el usuario y los carritos abandonados no se acumulan en memoria), conservando la expiración corta de las reservas de oferta, que es la que protege el inventario.

---

## Lo que aprendimos como equipo

- **Una proyección que se puede reconstruir es una proyección de la que no hay que tener miedo.** Elasticsearch, Neo4j y pgvector tienen un script idempotente que los reconstruye desde la fuente de verdad. Eso nos dejó cambiar mappings, modelos de grafo y modelos de embeddings sin migraciones delicadas.
- **Medir en vez de suponer.** Varias conclusiones cambiaron al medir: el HNSW no se usa con 1000 vectores, el primer modelo de embeddings parecía malo por un problema de codificación de la terminal y no del modelo, y la ventana de consistencia del outbox es de segundos, no de minutos.
- **Las pruebas automáticas con el servidor real pagaron su costo.** Las de concurrencia, fallas del checkout, buscador, fraude, recomendación y control de acceso se pueden correr en cualquier momento y son la evidencia de cada entrega. Fueron las que detectaron que las ACL no rompían nada y las que encontraron H-025.
- **El orden del enunciado no tiene que ser el orden de construcción.** Seguridad y la decisión sobre el producto (puntos 8 y 10) son transversales; dejarlas para "cuando toque" fue lo que más nos costó.
