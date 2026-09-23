# TiendaYa — Informe de la Entrega 2

**Curso:** Bases de Datos 2 — Universidad del Istmo
**Catedrático:** Ing. Javier Álvarez
**Integrantes:** Diego Rueda, Marcos Pineda, Fátima Ramazzini
**Repositorio:** github.com/Fatiunis/proyectoBD2.0
**Tema de la entrega:** concurrencia, señales de comportamiento y relaciones entre entidades (clave-valor, columnares y grafos)

> **Borrador.** Las secciones marcadas con ✏️ las completa el equipo. La evidencia técnica corresponde a pruebas ejecutadas contra el sistema real (PostgreSQL 18, MongoDB 8, Redis 7 y Neo4j 5) el 22 de septiembre de 2026.

---

## 1. Distribución de responsabilidades ✏️

| Integrante | Responsabilidades en esta entrega |
|---|---|
| Diego Rueda | ✏️ |
| Marcos Pineda | ✏️ |
| Fátima Ramazzini | ✏️ |

---

## 2. Resumen de la entrega

| Requerimiento del enunciado | Componente | Dónde está |
|---|---|---|
| Carrito persistente con expiración por inactividad | Redis | `backend/app/blueprints/carrito.py`, `backend/app/blueprints/checkout.py` |
| Oferta de inventario limitado, con ventana de tiempo y sin sobreventa bajo concurrencia | Redis + script Lua | `backend/app/blueprints/ofertas.py`, `backend/app/lua/reservar_oferta.lua` |
| Evaluación comparativa grafos vs. columnar | Documento de decisión | `docs/decisiones/ADR-002-grafos-vs-columnar.md` |
| Familia seleccionada: detección de fraude en reseñas | Neo4j | `backend/app/blueprints/resenas.py`, `backend/app/blueprints/fraude.py` |
| Justificación de incorporar el almacén clave-valor | Documento de decisión | `docs/decisiones/ADR-003-redis-carrito-y-oferta.md` |
| Diagrama de arquitectura actualizado | Mermaid | `docs/arquitectura.md` |
| Instrucciones para levantar el sistema completo | README | `README.md` (Docker Compose para Redis y Neo4j) |

---

## 3. Carrito de compra sobre Redis

### Implementación

- Cada usuario tiene un hash `carrito:{id_usuario}`: el campo es el id del producto y el valor, el ítem serializado (cantidad, precio de referencia, `id_sql_origen`, etc.).
- **Expiración configurada explícitamente**: `CARRITO_TTL_SEGUNDOS=1800` (30 minutos) en `.env`. El TTL se renueva con `EXPIRE` en cada lectura o escritura, así que el carrito vence tras 30 minutos **sin actividad**, no 30 minutos después de crearlo.
- Por qué 30 minutos: es lo bastante largo para una sesión de compra normal (comparar productos, volver al carrito) y lo bastante corto para que los carritos abandonados no se acumulen en memoria. Al ser configurable, se puede ajustar sin tocar código.
- El carrito exige sesión iniciada y se muestra desde el servidor: al abrir la vista del carrito, el frontend lo vuelve a leer de Redis.

### Relación con el checkout

El checkout toma los productos **del carrito guardado en Redis**, no de lo que envía el navegador, y se los pasa a `sp_procesar_checkout`, que valida precio y stock en PostgreSQL dentro de una transacción. Si el carrito ya expiró, el checkout responde `409` con el código `CARRITO_VACIO` y el mensaje "Tu carrito expiró o está vacío. Vuelve a agregar los productos."; el frontend muestra ese mensaje y vacía la vista. Cuando el pago se confirma, el backend borra el carrito.

La **referencia de pago la genera el backend** (formato `TY-AAAAMMDDHHMMSS-XXXXXX`, hora de Guatemala más 6 caracteres aleatorios) y se guarda en `pagos.referencia_transaccion`; el comprador ya no la escribe. Al confirmar la compra, el frontend muestra un resumen con el número de pedido, la referencia y un botón "Dejar reseña" por cada producto comprado, que abre el formulario de reseñas de ese producto.

### Evidencia

| Prueba | Resultado |
|---|---|
| TTL de un carrito recién escrito (`redis-cli TTL carrito:12`) | 1799 s |
| Compra real con la compradora de prueba María Torres (1 × PROD-0014), enviando además una lista de productos falsa desde el cliente | `201`, **pedido 11** creado en `pedidos`, `lineas_pedido` y `pagos` con 1 unidad de PROD-0014 por Q145.00; stock de ese producto en PostgreSQL de 58 a 57; la lista falsa se ignoró (el otro producto no cambió de stock); el carrito quedó borrado en Redis |
| Carrito expirado a la fuerza (`EXPIRE carrito:12 1`) y checkout 2 s después | `409 CARRITO_VACIO`; no se creó pedido ni cambió el stock |
| Compra desde la interfaz (comprador Carlos Méndez, 1 × PROD-0008) | **Pedido 15** con referencia generada automáticamente (`TY-20260922222736-96B82B`); el carrito y su contador quedaron vacíos y se mostró el resumen con "Dejar reseña", que llevó al formulario del producto |

La decisión de usar Redis y sus alternativas (dejar el carrito en el navegador o en tablas de PostgreSQL) están en **ADR-003**.

---

## 4. Oferta de inventario limitado sobre Redis

### Implementación

- Cada oferta usa dos claves:
  - `oferta:{producto_id}:stock`, el contador que se descuenta;
  - `oferta:{producto_id}:limite`, el límite original, para mostrar "quedan X de Y".
- **Ventana de tiempo**: al crear la oferta se indica `duracion_minutos` (de 1 a 10 080, es decir, hasta 7 días), y ambas claves se crean con ese TTL. La oferta **vence sola**: al expirar, las claves desaparecen y cualquier reserva responde `404`. La página del producto muestra una cuenta regresiva y la hora de fin en hora de Guatemala.
- **Reserva atómica sin bloqueos de aplicación**: `reservar_oferta.lua` lee el contador, comprueba que alcanza y lo descuenta en una sola ejecución del servidor Redis (`EVALSHA`). Redis no intercala otros comandos durante un script, así que no existe la carrera entre "leer" y "descontar". No se usan locks en Python ni `WATCH`/`MULTI`.
- **Control de quién gestiona la oferta**: solo el vendedor dueño del producto o un administrador pueden crear o cerrar una oferta.

### Evidencia de concurrencia

Script: `backend/scripts/prueba_concurrencia_oferta.py`. Lanza 50 solicitudes simultáneas (20 hilos) de "reservar 1 unidad" contra una oferta con límite de 10 unidades sobre un producto real.

```
Oferta creada: {'cantidad_limite': 10, 'duracion_minutos': 5, 'segundos_restantes': 300, ...}
Resultados: 10 éxitos (201), 40 rechazos.  Desglose: {409: 40}
Stock restante real: 0
RESULTADO: PASS -- no hubo sobreventa bajo concurrencia.
```

### Evidencia de la ventana de tiempo y del control de dueño

| Prueba | Resultado |
|---|---|
| Crear oferta de 2 minutos | `201`, `segundos_restantes: 120`, `fecha_fin` con offset `-06:00`; TTL en Redis de 120 s (`:stock`) y 119 s (`:limite`) |
| Reservar dentro de la ventana | `201`; el TTL sigue corriendo (una reserva no reinicia la ventana) |
| Oferta vencida (TTL acortado a 2 s y reserva 3 s después) | `404 "No hay oferta activa para este producto"`; las claves ya no existen |
| Duración ausente, 0 o mayor a 10 080 | `400` |
| Vendedor que no es dueño del producto intenta crear o cerrar la oferta | `403` |
| Oferta duplicada sobre el mismo producto | `409` |

La justificación de Redis frente a hacerlo en PostgreSQL (`SELECT ... FOR UPDATE` o `UPDATE` condicional) está en **ADR-003**.

---

## 5. Evaluación comparativa: grafos vs. columnar

El análisis completo está en **ADR-002**. En resumen:

- **Detección de fraude en reseñas**: es un problema de **relaciones** entre cuentas y productos, con consultas de varios saltos ("cuentas que califican los mismos productos que otras cuentas que a su vez..."). En SQL cada salto adicional es otro auto-JOIN; en Cypher es un patrón declarativo. **Se eligió una base de grafos (Neo4j).**
- **Panel de tendencias de venta**: con el volumen real de `pedidos` y `lineas_pedido` de TiendaYa, PostgreSQL agrega por intervalos de tiempo sin esfuerzo (`GROUP BY` y funciones de ventana sobre índices por fecha). **No se implementó una base columnar.** ADR-002 documenta las condiciones concretas bajo las que sí se justificaría: un volumen de escrituras de eventos de venta que supere lo que absorbe un único PostgreSQL, ingestión distribuida desde varias fuentes o regiones, o patrones de consulta fijos modelables como tablas desnormalizadas por partición.

---

## 6. Implementación de la familia seleccionada: Neo4j

### Modelo

```
(:Cuenta {id_usuario, nombre, rol}) -[:CALIFICO {calificacion, fecha, id_resena}]-> (:Producto {id_producto, nombre, sku})
```

- Las reseñas se guardan en MongoDB (colección `resenas`, referenciada, tal como se decidió en la Entrega 1) y cada reseña nueva se replica en el grafo como una relación `CALIFICO`.
- La relación guarda `id_resena`, así que cada arista del grafo se puede rastrear hasta la reseña original.
- Hay restricciones de unicidad para `Cuenta.id_usuario` y `Producto.id_producto` (`database/neo4j/01_constraints.cypher`).

### Consulta de varios saltos

`GET /api/fraude/alertas` (`backend/app/blueprints/fraude.py`) busca **tríos de cuentas** en los que **cada par** cumple a la vez tres señales:

1. comparte al menos 3 productos calificados;
2. ambas cuentas les dieron 5 estrellas;
3. las dos calificaciones ocurrieron dentro de una ventana corta (6 horas por defecto).

Cada par se recorre con el patrón de dos saltos `Cuenta → Producto ← Cuenta`, y el trío completo encadena tres de esos patrones. Combinar las tres señales es lo que evita falsos positivos: en los datos de prueba se comprobó que algunas cuentas sin relación entre sí coinciden por azar en 3 o más productos, pero no además en calificación perfecta y en la misma ventana de tiempo.

### Evidencia

Datos sembrados con `database/migrations/sembrar_resenas_fraude.py`: 66 reseñas en total, que incluyen reseñas legítimas dispersas en 30 días, un **anillo de fraude** de 4 cuentas que se califican los mismos 4 productos de un vendedor en menos de 2 horas, y un **par de control** de 2 cuentas que solo comparten 2 productos.

| Resultado | Detalle |
|---|---|
| Grafo sincronizado | 12 nodos `Cuenta`, 15 nodos `Producto` y 66 relaciones `CALIFICO`, igual que las 66 reseñas de MongoDB |
| Alertas detectadas | **4**: las 4 combinaciones posibles de 3 cuentas dentro del anillo (Carlos Méndez, Sofía López, María Torres y José Ramírez), cada una con puntaje de anomalía 12 |
| Par de control | No aparece en ninguna alerta |
| Falsos positivos entre las reseñas legítimas | Ninguno |

El panel está en `/admin/fraude` y solo lo ve un administrador.

---

## 7. Arquitectura actualizada

El diagrama está en `docs/arquitectura.md`. Incluye los cuatro componentes de persistencia y cómo se relacionan:

- **PostgreSQL**: usuarios, pedidos, pagos, inventario y checkout transaccional.
- **MongoDB**: catálogo, historial de cambios y reseñas.
- **Redis**: carrito y oferta.
- **Neo4j**: grafo de reseñas para fraude.

Para cada integración se indica su ventana de consistencia; ninguna usa commit en dos fases (2PC) entre motores.

---

## 8. Limitaciones conocidas

- **Sin autenticación en el servidor**: el rol y el `id_usuario` los envía el cliente en cada solicitud y el backend los acepta sin verificarlos. Por ejemplo, alguien que se declare "administrador" en la solicitud puede gestionar ofertas o consultar alertas de fraude. La autenticación y autorización explícitas son un requerimiento de la entrega final.
- **La oferta es un cupo aparte**: no descuenta el inventario de PostgreSQL, y una reserva todavía no genera un pedido ni aplica un precio de oferta.
- **Sincronización de reseñas hacia Neo4j sin 2PC**: si Neo4j no está disponible al crear una reseña, esta queda guardada en MongoDB y solo se registra una advertencia; el grafo queda desactualizado hasta volver a sincronizarlo.
- **Catálogo y stock en dos lugares**: el checkout descuenta stock en PostgreSQL, pero el catálogo de MongoDB muestra su propio valor; no se sincronizan automáticamente. En la prueba del pedido 11, PostgreSQL quedó en 57 unidades y MongoDB siguió mostrando 58.
- **Redis es obligatorio para arrancar**: el backend carga el script Lua al iniciar, así que no arranca si Redis no está disponible.

---

## 9. Cómo reproducir la evidencia

Con el sistema levantado según el `README.md`:

```bash
# Concurrencia de la oferta (usa PROD-0001; no debe haber otra oferta activa en ese producto)
python backend/scripts/prueba_concurrencia_oferta.py

# Datos de fraude y consulta de alertas
python database/migrations/sembrar_resenas_fraude.py
curl "http://127.0.0.1:8000/api/fraude/alertas?rol_solicitante=administrador"

# TTL de un carrito o de una oferta
docker compose exec redis redis-cli TTL carrito:<id_usuario>
docker compose exec redis redis-cli TTL oferta:<producto_id>:stock
```
