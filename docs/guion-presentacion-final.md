# Guion de la presentación final

TiendaYa · Bases de Datos 2 · preparado el 21 de octubre de 2026

La presentación final tiene dos partes que la rúbrica evalúa: mostrar el proyecto completo y **sustentar las decisiones ante preguntas** (4 pts). Dura unos 15-20 minutos más preguntas. Material de apoyo: [diagrama de arquitectura final](arquitectura-final.html), [retrospectiva](retrospectiva.md), [informe de la entrega final](informe-entrega-final.md) y los ADR de [`decisiones/`](decisiones/).

Los presentadores de cada bloque están marcados con ✏️ para que el equipo los reparta.

---

## 1. Qué tener abierto

| Ventana | Dirección | Para qué |
|---|---|---|
| Diagrama final | `docs/arquitectura-final.html` en el navegador | Bloque 3.1 y para volver a él en las preguntas |
| Sitio público | `http://127.0.0.1:5173` (o el puerto que dé Vite) | Recomendaciones y búsqueda por significado |
| Panel admin | `/admin/sincronizacion` con `admin@tiendaya.com` / `Tiendaya123!` | Cobertura de embeddings y outbox |
| Terminal 1 | backend: `python backend/main.py` | Debe mostrar `[relevo] ... activo` |
| Terminal 2 | libre, con el `venv` activado | Pruebas en vivo |
| pgAdmin | servidor `localhost:5433`, base `tiendaya_vectores`, usuario `vectores_lector` | Mostrar la tabla y una consulta `<=>` |

## 2. Preparación (30 min antes)

1. `docker compose up -d` y esperar a que `docker compose ps` muestre `vectores` y `elasticsearch` como `healthy`.
2. Backend y frontend levantados.
3. **Calentar el modelo**: abrir una vez `http://127.0.0.1:8000/api/busqueda/semantica?q=prueba`. La primera búsqueda semántica carga el modelo (~8 s); las siguientes tardan milisegundos.
4. Correr las dos pruebas de la entrega final y dejar la salida en pantalla por si se cae algo:
   ```bash
   python backend/scripts/prueba_control_acceso_redis.py
   python backend/scripts/prueba_recomendacion.py
   ```
5. Abrir PROD-0005 en el sitio para confirmar que aparecen los "Productos relacionados".

## 3. Guion

### 3.1 La arquitectura completa (3 min) — ✏️

- Abrir `arquitectura-final.html`, figura 1. Recorrer los seis componentes con **una frase cada uno**: qué dato es suyo y por qué ese motor (sección "Por qué cada motor" al final del documento).
- Mensaje central: **un solo motor decide si hubo compra (PostgreSQL)**; MongoDB es la fuente de verdad del catálogo; Elasticsearch, Neo4j y pgvector son **proyecciones que se pueden reconstruir**; nada usa 2PC, las copias se reintentan por el outbox.

### 3.2 Recomendación semántica en vivo (4 min) — ✏️

1. En el sitio, abrir **PROD-0005** (HP EliteBook). Bajar a "Productos relacionados": 6 laptops **distintas**.
2. En otra pestaña: `http://127.0.0.1:8000/api/productos/PROD-0005/relacionados?diversificar=0` → sin diversificar son variantes de la misma laptop. Explicar el umbral 0.93 (medido sobre el catálogo, ADR-008).
3. Buscar en el sitio **"regalo para alguien que ama la música"**: Elasticsearch no encuentra nada y aparece "Productos por significado" con audífonos. Ninguna palabra coincide: el modelo compara significados.
4. En pgAdmin (5433), la consulta de vecinos de PROD-0001 del README: mostrar que es SQL normal con `<=>`.
5. Si preguntan por calidad: mostrar en la evidencia los **dos fallos** de R3 ("fragancia elegante para una cena" → cuchillos). Decir que se reportan como tasa de acierto (6/8, contra 3/8 del buscador léxico) y no se maquillaron.

### 3.3 Sincronización del componente vectorial (2 min) — ✏️

1. Panel admin → Sincronización: "Componente vectorial: 1019 de 1019 productos con embedding · al día".
2. Editar la descripción de un producto en el admin y guardarlo; abrir sus relacionados: cambian. Explicar el hash del texto (solo se recalcula lo que cambió) y el evento `embedding_producto` del outbox si pgvector está caído.
3. (Opcional si hay tiempo) `docker compose stop vectores` → la página del producto sigue funcionando, solo desaparece la franja; `docker compose start vectores` → vuelve sola.

### 3.4 Control de acceso en Redis (4 min) — ✏️

1. Mostrar `database/redis/users.acl`: un usuario por servicio, contraseñas como hash, `default` deshabilitado.
2. En la terminal 2, en vivo:
   ```bash
   docker compose exec redis redis-cli PING
   # -> NOAUTH Authentication required.
   docker compose exec redis redis-cli --user tiendaya_api --pass api_tiendaya_2026 FLUSHALL
   # -> NOPERM ... no permissions to run the 'flushall' command
   docker compose exec redis redis-cli --user tiendaya_api --pass api_tiendaya_2026 EVAL "return redis.call('FLUSHALL')" 0
   # -> ACL failure in script: ... (la ACL también aplica dentro de Lua)
   docker compose exec redis redis-cli --user tiendaya_relevo --pass relevo_tiendaya_2026 INCRBY oferta:PROD-0001:stock 100
   # -> NOPERM: el relevo no puede subir el cupo de una oferta
   ```
3. Correr `python backend/scripts/prueba_control_acceso_redis.py` → 37/37.
4. Contar **H-025** (el AOF y `default`): es la mejor historia de la entrega porque muestra por qué se prueba con reinicios reales.

### 3.5 Retrospectiva (4 min) — ✏️

Abrir [`retrospectiva.md`](retrospectiva.md), tabla de resumen. No leerla entera; elegir:

- **Sostenemos**: outbox + idempotencia (nació para el checkout y terminó sirviendo a Elasticsearch y pgvector sin diseñar nada nuevo).
- **Replanteamos**: el producto duplicado entre MongoDB y PostgreSQL. Con ≈1000 productos, `JSONB` + GIN en PostgreSQL habría cubierto la heterogeneidad de atributos sin dos fuentes de verdad. Lo que no volveríamos a hacer es migrar a medias.
- **Replanteamos**: seguridad al final. La ACL protege a Redis de la API, pero la API no verifica el rol del usuario.

### 3.6 Cierre (0,5 min) — ✏️

Una frase: "Cada motor está porque resuelve un patrón de acceso concreto, cada copia tiene una ventana de consistencia medida, y lo que no se justificó (columnar, NewSQL) se documentó en vez de implementarse."

## 4. Plan B

| Si falla… | Hacer… |
|---|---|
| No aparecen los relacionados | `docker compose ps` (¿`vectores` arriba?) y `python database/migrations/generar_embeddings_productos.py`. Mientras tanto, mostrar `docs/evidencia/prueba_recomendacion.txt` |
| La búsqueda semántica tarda mucho la primera vez | Es la carga del modelo (~8 s); por eso se calienta en la preparación |
| El backend dice `NOAUTH` | El `.env` tiene el `REDIS_URL` viejo; copiarlo de `.env.example` y reiniciar |
| Docker no arranca | Presentar con el HTML del diagrama y los archivos de `docs/evidencia/` |

## 5. Preguntas probables y respuesta corta

**¿Por qué pgvector y no el `dense_vector` de Elasticsearch, que ya tenían?**
Porque el componente vectorial queda como pieza identificable, con sus propios roles, y reindexar el buscador no arrastra los vectores. Con 1000 productos ambas funcionan; si necesitáramos búsqueda híbrida en una sola consulta, Elasticsearch sería la opción (ADR-008, "Cuándo se replantearía").

**¿Por qué un contenedor aparte y no la extensión en su PostgreSQL?**
Porque el PostgreSQL de cada uno está instalado en Windows, donde pgvector hay que compilarlo con Visual Studio. Es una razón de costo operativo, y la retrospectiva lo reconoce: si el PostgreSQL principal estuviera en Docker, la pondríamos ahí.

**El índice HNSW no se usa, ¿para qué está?**
Con 1019 filas el recorrido exacto cuesta 0.9 ms y da recall perfecto; el planificador hace bien en preferirlo. El índice está creado y verificado (0.4 ms forzado) para cuando el catálogo crezca; no hay que cambiar código.

**¿Cómo saben que las recomendaciones son buenas?**
Medimos: 90 % de la misma categoría y 100 % de la misma o afín, en 24 categorías; y la búsqueda semántica acierta 6 de 8 frases contra 3 de 8 del buscador léxico. Los fallos están en la evidencia.

**¿Qué pasa si se edita un producto y pgvector está caído?**
El producto se guarda en MongoDB igual (fuente de verdad), se registra `embedding_producto` en el outbox y el relevo lo reintenta. Mientras tanto se recomienda con el texto anterior: ventana de consistencia eventual aceptada.

**¿Por qué Redis para el control de acceso y no Elasticsearch o MongoDB?**
Porque en Redis una operación indebida rompe una garantía de negocio (sobreventa, `FLUSHALL` de carritos), lo usan tres servicios con necesidades distintas, y sus keys ya tenían prefijos por dominio. Elasticsearch es reconstruible desde Mongo, y Mongo corre local en cada máquina sin forma de versionar la configuración (ADR-009).

**¿Por qué `tiendaya_api` puede tocar carritos y ofertas a la vez?**
Porque varios scripts Lua tocan una oferta y un carrito en la misma operación atómica; separarlos en dos usuarios obligaría a partir los scripts y perder la atomicidad que evita la sobreventa.

**¿La ACL los protege de un usuario malicioso del portal?**
No: protege a Redis de los servicios. Un usuario del portal pasa por la API, y la API hoy confía en el `rol_solicitante` que manda el navegador. Es la deuda principal de la retrospectiva; la solución es un token firmado desde la fase inicial.

**Si empezaran de nuevo, ¿usarían MongoDB?**
Probablemente no para este tamaño: `JSONB` en PostgreSQL cubre los atributos variables y el historial puede ser una tabla de eventos, sin duplicar el producto en dos motores. Si se usa MongoDB, hay que migrar completo, no a medias (retrospectiva, punto 8).
