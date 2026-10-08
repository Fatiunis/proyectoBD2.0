# Registro de hallazgos

Este archivo registra los errores, pendientes y discrepancias que aparecen al probar TiendaYa (scripts de `backend/scripts/prueba_*.py`, pruebas manuales de la API y del frontend, y revisiones de la documentación). Sirve para que nadie del equipo reporte dos veces lo mismo y para que el catedrático vea qué se encontró, qué se corrigió y qué se decidió aceptar.

**Quién lo mantiene:** el responsable de la documentación, a partir de lo que reportan quienes prueban. Cualquiera del equipo puede agregar una entrada respetando el formato.

**Formato:** una entrada por hallazgo, la más reciente arriba, numerada `H-NNN` (el número no se reutiliza). Campos: estado, severidad (`bloqueante`, `menor`, `documentación`), área (`backend`, `frontend`, `database`, `documentación` o `repositorio`, para archivos de configuración de la raíz como `.gitignore`), síntoma, cómo reproducirlo, causa y corrección.

**Cómo se cierra una entrada:** no se borra. Se cambia el estado a `corregido en <commit o archivo>` (o `descartado (motivo)`) y se completa "Corrección" con lo que se cambió. Si el hallazgo revela una limitación que se decidió aceptar, se agrega también a "Limitaciones conocidas" del [`README.md`](../README.md).

Los números de línea de las causas de H-001 a H-009 se refieren al código del commit `785789d` (2026-10-06). Los de H-010 a H-015, y los de las correcciones, se refieren al árbol de trabajo del 2026-10-06 (correcciones todavía sin commit). Los de H-016 en adelante, al árbol de trabajo del 2026-10-07 (sobre el commit `06994dd`, con cambios sin commit). Los de H-019 en adelante (detección de fraude ampliada), al árbol de trabajo del 2026-10-07 sobre el commit `4aabb9c`, con cambios sin commit.

## Verificación del fraude ampliado (2026-10-07)

Verificación de la detección de fraude ampliada ([`deteccion-fraude-ampliada.md`](deteccion-fraude-ampliada.md)) sobre el árbol de trabajo del 2026-10-07 (sin commit), con la semilla `database/migrations/sembrar_fraude_ampliado.py` cargada:

- **Agente de backend**: `python backend/scripts/prueba_fraude_ampliado.py` 59/59 PASS (bloques F1 a F8: positivos, controles, lo que agregan los patrones nuevos frente a la consulta de la Entrega 2, `GET /api/fraude/alertas` intacto, errores, `/resumen`, y sincronización de reseñas y direcciones con Neo4j). Salida real de una corrida del 2026-10-07 en [`evidencia/prueba_fraude_ampliado.txt`](evidencia/prueba_fraude_ampliado.txt).
- **Agente de base de datos**: el ruido legítimo de `sembrar_resenas_fraude.py` no genera ninguna alerta de los 4 patrones con los umbrales por defecto (0 alertas). (Que cada escenario de control de la semilla nueva quede por debajo de su umbral lo comprueba el bloque F2 de la prueba automática.)
- **Agente de pruebas, prueba manual parcial**: una dirección escrita con distintas mayúsculas y espacios en cuentas diferentes llega al mismo nodo `(:Direccion)` (misma clave normalizada), y `cuentas_vinculadas` detecta esas cuentas. Esa pasada se interrumpió antes de terminar. Sus datos se limpiaron; quedaron los nodos `Producto` PROD-0113 y PROD-0168 y el `Vendedor` 51 sin relaciones, que también se borraron (no afectaban ninguna alerta).
- **Estado del grafo consultado por el agente de documentación** (Neo4j, 2026-10-07): las 151 reseñas de MongoDB tienen su `CALIFICO`, todas con `compra_verificada`; hay 28 nodos `Vendedor`, 63 `VENDIDO_POR` (uno por producto) y 14 nodos `Direccion` con 17 `ENVIA_A`. Las tres variantes de "13 Calle 4-56 Zona 10" de la semilla quedan en un solo nodo, con clave `13 calle 4-56 zona 10|guatemala|01010` (cuentas 81, 82 y 83). Constraints: `cuenta_id`, `producto_id`, `vendedor_id` y `direccion_clave`.
- **Verificación final del agente de pruebas (2026-10-07)**:
  - `python backend/scripts/prueba_fraude_ampliado.py`: 59/59 PASS.
  - API de los 4 patrones: `/patrones` los lista en orden; cada alerta tiene la forma esperada; `404` para tipos que no existen (`anillo_resenas`, `rafaga_producto`); `400` con un parámetro inválido; `403` sin rol de administrador.
  - `GET /api/fraude/resumen`: `por_tipo` = `cuenta_rafaga` 1, `grupo_coordinado` 4, `sesgo_vendedor_sin_compra` 6, `cuentas_vinculadas` 1; 12 alertas y 23 cuentas de riesgo.
  - `GET /api/fraude/alertas` (Entrega 2): `total` 5 (los 4 tríos del anillo de la semilla, más el de la prueba manual de H-021). El diff de `backend/app/blueprints/fraude.py` no borra ninguna línea.
  - Prueba propia: 5 reseñas sin compra de la cuenta demo 69, en productos distintos, hacen aparecer la cuenta en `cuenta_rafaga` con puntaje 100 y nivel alto, y en `/resumen`. Después se limpió todo: reseñas, `CALIFICO` y los nodos `Cuenta`, `Producto` y `Vendedor` que se crearon.
  - La semilla original (`sembrar_resenas_fraude.py`) y `database/neo4j/01_constraints.cypher` no cambiaron.
  - `npm run build` (en `frontend/app/`): OK (80 módulos). Las 6 pestañas del panel `/admin/fraude` se revisaron leyendo el código contra las respuestas de la API, sin navegador.
  - Regresión: `python backend/scripts/prueba_buscador.py` 18/18 PASS; `GET /api/resenas/PROD-0001` responde `200`.
  - Hallazgo nuevo: H-024 (corregido el mismo día).

## Verificación del 2026-10-07 (ofertas flash, ventas y carrito)

Corrida del agente de pruebas sobre el árbol de trabajo del 2026-10-07 (sin commit), con H-017 corregido:

- `descuento_pct` coincide en `POST /api/ofertas`, `GET /api/ofertas/<producto_id>`, el listado público `GET /api/ofertas` y el listado del vendedor `GET /api/vendedores/<id>/ofertas` (PROD-0002, Q2200 → Q1749: 21 en los cuatro).
- Tope de 99: una oferta de Q0.01 devuelve `descuento_pct` 99. `precio_oferta` 0 o negativo responde `400`, así que un 100 % no es alcanzable, tampoco en el frontend.
- `python backend/scripts/prueba_concurrencia_oferta.py`: PASS (10 reservas aceptadas y 40 rechazadas, sin sobreventa).
- `python backend/scripts/prueba_buscador.py`: 18/18 PASS (sin `--caida-real`).
- `npm run build` (en `frontend/app/`): OK.
- Distribución de la franja de ofertas en pantallas `lg` (columna derecha, encima de la grilla): verificada leyendo el código, sin navegador.
- Redis quedó limpio salvo las 3 ofertas de prueba (PROD-0007, PROD-0012 y PROD-0013).
- Hallazgo nuevo: H-018 (corregido el mismo día).

## Re-verificación del 2026-10-06 (después de las correcciones)

Con las correcciones de H-001 a H-004, H-007, H-008, H-010 y H-011 aplicadas en el árbol de trabajo:

- `python backend/scripts/prueba_buscador.py --caida-real`: 21/21 PASS.
- `python backend/scripts/prueba_fallas_checkout.py --caida-real`: 45/45 PASS. E4 (MongoDB cae tras el COMMIT) convergió en 16 s y E5 (caída real de Elasticsearch) 15 s después de levantarlo. Creó los pedidos 39 y 41 a 44 de `maria.torres@email.com`. El 40 no existe porque lo consumió el rollback de E2: es el hueco normal de la secuencia que explica la sección 8 de la [estrategia de consistencia](estrategia-consistencia-checkout.md). La [evidencia guardada](evidencia/prueba_fallas_checkout.txt) sigue siendo la de la corrida del 5 de octubre y no se reemplazó.
- Outbox: 36 eventos procesados, 0 pendientes y 0 fallidos.
- Consistencia entre motores: 1015 productos en MongoDB y en el alias `productos` de Elasticsearch. Hay dos productos con el stock desfasado de antes del outbox (H-015).
- `GET /api/busqueda?q=mouse&pagina=500` responde `200` con `items` vacíos, `total` 40 y `total_paginas` 2; `precio_min=nan` responde `400`.
- **Nota de entorno (corregido, solo en la base local):** el índice `idx_activo_precio` de MongoDB no existía en la base local, porque después de la migración no se había corrido el comando del [paso 4 del README](../README.md#4-migrar-el-catálogo-a-mongodb). Se creó y ya aparece en `productos`. No es un error de código: la migración `database/migrations/migracion_postgres_a_mongo.py` no crea ese índice, y su `drop()` lo borra cada vez que se corre completa. El catálogo funciona sin él, pero MongoDB tiene que recorrer y ordenar toda la colección en cada página de "Todas las categorías".
- **Verificación final del 2026-10-06** (con H-012, H-014 y H-015 cerrados): `python backend/scripts/prueba_buscador.py` 18/18 PASS (sin `--caida-real`); las fallas simuladas quedaron deshabilitadas (`GET /api/checkout/fallas-simuladas` responde `habilitadas: false`); stock con 0 desfases entre PostgreSQL, MongoDB y Elasticsearch en los 1015 productos.

## Verificación del 2026-10-06 (antes de las correcciones)

- `python backend/scripts/prueba_buscador.py --caida-real`: 21/21 PASS.
- `python backend/scripts/prueba_fallas_checkout.py --caida-real`: 45/45 PASS. E4 (MongoDB cae tras el COMMIT) convergió en 12 s y E5 (caída real de Elasticsearch) 31 s después de levantarlo. Creó los pedidos 33 a 38 del comprador `maria.torres@email.com`. La [evidencia guardada](evidencia/prueba_fallas_checkout.txt) es de una corrida anterior (20 s y 25 s) y no se reemplazó.
- Verificación general de la API: 158 casos, 155 OK. Los 3 restantes son hallazgos menores (H-002, H-003 y H-004). Hubo además 1 falso positivo: `DELETE /api/carrito/<id_usuario>/items/<id_producto>` con un producto que no está en el carrito responde `200` a propósito, porque la operación es idempotente (`backend/app/blueprints/carrito.py:202-216`).
- Consistencia entre motores: 1015 productos en PostgreSQL, en MongoDB y en el alias `productos` de Elasticsearch. Outbox: 18 eventos procesados, 0 pendientes y 0 fallidos.
- `npm run build` (en `frontend/app/`): OK.

## H-024 — "Ajustar sensibilidad" acepta un porcentaje mayor que 100 (2026-10-07)
- **Estado:** corregido en el árbol de trabajo (`frontend/app/src/components/admin/AlertasPatron.vue`; 2026-10-07, sin commit)
- **Severidad:** menor
- **Área:** frontend
- **Síntoma:** en la pestaña "Cuenta en ráfaga" del panel `/admin/fraude`, el campo `min_pct_sin_compra` de "Ajustar sensibilidad" deja escribir un valor mayor que 100. El backend responde `400` ("min_pct_sin_compra debe ser un entero entre 1 y 100") y el panel muestra un error. El campo debería limitarse a 1-100 antes de enviar.
- **Cómo reproducirlo:** entrar como `admin@tiendaya.com` a `/admin/fraude?patron=cuenta_rafaga`, escribir `150` en "Mínimo % de reseñas sin compra" y aplicar. Por la API: `curl "http://127.0.0.1:8000/api/fraude/alertas/cuenta_rafaga?rol_solicitante=administrador&min_pct_sin_compra=150"` responde `400`.
- **Causa:** el formulario de `AlertasPatron.vue` solo validaba que el valor fuera un entero positivo. El tope de 100 está solo en el backend (`_MAXIMOS_PARAMETRO` en `backend/app/blueprints/fraude.py`).
- **Corrección:** `AlertasPatron.vue:23-28`: `esPorcentaje` reconoce como porcentaje todo parámetro que tenga `pct` como palabra en el nombre (por ejemplo `min_pct_sin_compra`), y `valorValido` exige para esos un entero entre 1 y 100 (el resto, un entero positivo). El campo tiene `max="100"` (línea 96) y, si el valor no es válido, muestra "Debe ser un entero entre 1 y 100" (línea 107); si es válido, la ayuda dice "Entre 1 y 100 · Por defecto 80" (línea 109). Verificado con `npm run build`; falta la prueba visual en el navegador.

## H-023 — Comentarios de los scripts del fraude ampliado con nombres de patrones viejos (2026-10-07)
- **Estado:** corregido en el árbol de trabajo (2026-10-07)
- **Severidad:** documentación
- **Área:** database
- **Síntoma:** el docstring de `database/migrations/sincronizar_grafo_fraude.py` dice que el grafo ampliado lo usan los patrones "promotor_sin_compra, ataque_competencia, rafaga_producto y cuentas_vinculadas". Los patrones que existen son `cuenta_rafaga`, `grupo_coordinado`, `sesgo_vendedor_sin_compra` y `cuentas_vinculadas`; los otros tres se eliminaron durante el desarrollo (la prueba verifica que respondan `404`). Además, `database/neo4j/02_fraude_ampliado.cypher` y ese mismo docstring dicen "(Entrega 3)", aunque el cambio es posterior a la Entrega 3.
- **Cómo reproducirlo:** leer las primeras líneas de `database/migrations/sincronizar_grafo_fraude.py` (párrafo "Propósito") y la línea 1 de `database/neo4j/02_fraude_ampliado.cypher`.
- **Causa:** comentarios escritos con una versión intermedia del diseño.
- **Corrección:** el docstring de `sincronizar_grafo_fraude.py` (líneas 6-7) nombra ahora los patrones vigentes (`cuenta_rafaga`, `grupo_coordinado`, `sesgo_vendedor_sin_compra` y `cuentas_vinculadas`), y la línea 2 de ese archivo y la línea 1 de `02_fraude_ampliado.cypher` dicen "(después de la Entrega 3, 2026-10-07)". No cambia el comportamiento. **Verificado:** `grep -rn "promotor_sin_compra\|ataque_competencia\|rafaga_producto" database/` no encuentra nada y el script compila (`py_compile`).

## H-022 — 15 compradores `@fraude-demo` sin uso en bases que corrieron una versión intermedia de la semilla (2026-10-07)
- **Estado:** descartado (inofensivo: son compradores sin reseñas, direcciones ni pedidos; no se borran usuarios)
- **Severidad:** menor
- **Área:** database
- **Síntoma:** en una base donde se corrió una versión intermedia de `database/migrations/sembrar_fraude_ampliado.py`, que sembraba 4 escenarios más, quedan 15 compradores `@fraude-demo.tiendaya.gt` que ninguna corrida actual usa. En la base local son los ids 66 a 80 (de `oscar.monterroso@fraude-demo.tiendaya.gt` a `ingrid.mazariegos@fraude-demo.tiendaya.gt`). Las 24 cuentas que sí usa la semilla son las de `CUENTAS_POR_ESCENARIO`.
- **Cómo reproducirlo:** `venv/Scripts/python -c "import psycopg2, os; from dotenv import load_dotenv; load_dotenv(); c=psycopg2.connect(host=os.getenv('PG_HOST'), port=os.getenv('PG_PORT'), dbname=os.getenv('PG_DBNAME'), user=os.getenv('PG_USER'), password=os.getenv('PG_PASSWORD')); cur=c.cursor(); cur.execute(\"SELECT count(*) FROM usuarios WHERE email LIKE '%@fraude-demo.tiendaya.gt'\"); print(cur.fetchone())"` da 39 en esa base (24 en una base que solo corrió la versión final). Comprobado el 2026-10-07: los ids 66 a 80 no tienen direcciones ni pedidos en PostgreSQL ni reseñas en MongoDB.
- **Causa:** la semilla crea los usuarios con `ON CONFLICT (email) DO NOTHING` y, a propósito, nunca borra usuarios (solo limpia sus reseñas, direcciones marcadas y relaciones). Está explicado en el docstring del script.
- **Corrección:** ninguna. Como no tienen reseñas, no aparecen en ninguna alerta. Si se quieren quitar, se pueden borrar a mano de `usuarios` (no tienen filas que los referencien).

## H-021 — Las reseñas "[prueba fraude]" del 2026-09-23 siguen en la base y aparecen como fraude (2026-10-07)
- **Estado:** descartado (no es un falso positivo: son reseñas de una prueba manual de fraude que siguen en la base)
- **Severidad:** documentación
- **Área:** database
- **Síntoma:** las cuentas 16 (Paola Morales), 18 (Daniela Ortiz), 20 (Gabriela Ramos) y 21 (Andres Vasquez) aparecen en `grupo_coordinado`, y 16, 18 y 21 forman un trío en `GET /api/fraude/alertas` (por eso esa consulta da 5 alertas y no las 4 del informe de la Entrega 2). Parecen falsos positivos, pero no lo son: son las 11 reseñas de 5 estrellas sobre PROD-0107, PROD-0108 y PROD-0109 de la prueba manual del 2026-09-23 ([guía de prueba de fraude](guia-prueba-fraude.md), sección 3), escritas a segundos de distancia, con el texto `[prueba fraude]` (o `[prueba fraude - control]` en la cuenta 20).
- **Cómo reproducirlo:** en `mongosh`, `db.resenas.find({ texto: /\[prueba fraude/ }).count()` da 11; `curl "http://127.0.0.1:8000/api/fraude/resumen?rol_solicitante=administrador"` incluye las cuentas 16, 18, 20 y 21.
- **Causa:** la prueba manual no se limpió después. La cuenta 20 era el control de esa prueba (comparte solo 2 productos y por eso no forma trío en la consulta de la Entrega 2), pero sí cumple el umbral de `grupo_coordinado` (3 cuentas, 2 productos en común, 6 horas): el patrón nuevo es más sensible a propósito.
- **Corrección:** ninguna en el código. Para quitarlas, seguir la sección 7 de la [guía de prueba de fraude](guia-prueba-fraude.md) (borra las reseñas en MongoDB y sus relaciones en Neo4j). Si se dejan, al leer el panel hay que tener en cuenta que son datos de prueba.

## H-020 — Carrera posible al sincronizar direcciones con Neo4j (2026-10-07)
- **Estado:** descartado (limitación aceptada: sincronización en mejor esfuerzo, sin 2PC; agregada a "Limitaciones conocidas" del [`README.md`](../README.md))
- **Severidad:** menor
- **Área:** backend
- **Síntoma:** si dos cambios de direcciones del mismo usuario (crear, editar o borrar) se confirman casi a la vez en PostgreSQL, las relaciones `ENVIA_A` de Neo4j pueden quedar con el estado anterior. Deberían reflejar siempre las direcciones actuales de PostgreSQL.
- **Cómo reproducirlo:** no se reprodujo; se deduce del código. Haría falta enviar dos `PUT /api/usuarios/<id_usuario>/direcciones/<id_direccion>` del mismo usuario casi al mismo tiempo, de forma que la sincronización que leyó primero escriba en Neo4j después que la otra.
- **Causa:** `sincronizar_direcciones_cuenta` (`backend/app/grafo_fraude.py`) lee las direcciones actuales de PostgreSQL después del commit y deja `ENVIA_A` iguales a esa lectura. No hay bloqueo entre la lectura y la escritura en Neo4j. Está documentado en el docstring de la función.
- **Corrección:** ninguna. Se acepta porque un usuario casi nunca edita dos direcciones a la vez, el efecto es solo sobre el detector `cuentas_vinculadas` (no sobre las direcciones ni el checkout) y se corrige solo con la próxima edición de direcciones de ese usuario o al correr `python database/migrations/sincronizar_grafo_fraude.py`, que es idempotente.

## H-019 — El backend se cae al recargar en Windows con `OSError: [WinError 10038]` (2026-10-07)
- **Estado:** abierto
- **Severidad:** menor
- **Área:** backend
- **Síntoma:** con el backend en modo debug (`DEBUG = True` en `backend/main.py`), al guardar un archivo `.py` del backend, el recargador de Flask (Werkzeug) no reinicia el servidor: el proceso termina con `OSError: [WinError 10038]` en `select.select` y la API deja de responder. Debería recargarse y seguir atendiendo. Se observó varias veces en Windows durante el desarrollo de la detección de fraude ampliada.
- **Cómo reproducirlo:** en Windows, `python backend/main.py`, editar y guardar cualquier archivo de `backend/app/` y luego `curl http://127.0.0.1:8000/api/fraude/patrones?rol_solicitante=administrador` (no responde). No se reprodujo en macOS/Linux.
- **Causa:** no confirmada. El error sale del bucle del servidor de Werkzeug (`select.select` sobre el socket del servidor) al reiniciarse el proceso en Windows. No es un error del código de TiendaYa.
- **Corrección:** por ahora, relanzar `python backend/main.py` a mano. Si se vuelve molesto, se puede proponer al agente de backend arrancar sin recargador (`use_reloader=False`) en Windows, a cambio de reiniciar a mano después de cada cambio.

## H-018 — En los resultados de búsqueda, la etiqueta de oferta solo marca una oferta (2026-10-07)
- **Estado:** corregido en el árbol de trabajo (`frontend/app/src/components/publico/NavPublica.vue`; 2026-10-07, sin commit)
- **Severidad:** menor
- **Área:** frontend
- **Síntoma:** en los resultados de búsqueda, la etiqueta "⚡ -X%" de `TarjetaProducto.vue` aparece solo en un producto en oferta, aunque haya varias ofertas vigentes. Debería aparecer en todos los productos con oferta vigente, como en el catálogo.
- **Cómo reproducirlo:** con las ofertas vigentes de PROD-0007, PROD-0012 y PROD-0013, abrir `/?q=monitor`: PROD-0012 y PROD-0013 salen sin etiqueta. `curl "http://127.0.0.1:8000/api/ofertas?limite=1"` trae solo PROD-0007, con `total` 3.
- **Causa:** `useOfertasFlash.js` hace la consulta con el mayor `limite` de los componentes montados. En los resultados de búsqueda no se monta la franja (`limite: 100`), y el único suscriptor es el botón "Ofertas" de `frontend/app/src/components/publico/NavPublica.vue:21`, con `limite: 1`. `ofertaActivaDe` solo encuentra las ofertas cargadas.
- **Corrección:** `NavPublica.vue:24` se suscribe con `useOfertasFlash({ limite: 100 })` (comentario en las líneas 21-23). Como la barra está montada en todas las vistas públicas, el estado compartido tiene siempre todas las ofertas y `ofertaActivaDe` las encuentra también en los resultados de búsqueda; sigue siendo una sola petición cada 20 s. Además, el contador del botón "Ofertas" (`NavPublica.vue:25`) cuenta solo las ofertas disponibles (`ofertaDisponible`: con cupo y sin terminar), igual que el "N activas" de la franja, en vez del `total` del backend, que incluye las agotadas. De paso, el botón "Ver →" de la franja contraída tiene `aria-label` "Ver todas las ofertas flash" (`FranjaOfertasFlash.vue:162`). Verificado con `npm run build` y `GET /api/ofertas?limite=100` (3 ofertas); falta la prueba visual en el navegador.

## H-017 — `descuento_pct` puede valer 100 aunque la oferta cobre algo (2026-10-07)
- **Estado:** corregido en el árbol de trabajo (`backend/app/blueprints/ofertas.py`, `_descuento_pct`; 2026-10-07, sin commit)
- **Severidad:** menor
- **Área:** backend
- **Síntoma:** con un precio de oferta muy bajo frente al precio normal, `POST /api/ofertas` y `GET /api/ofertas` devuelven `"descuento_pct": 100`, aunque el producto no es gratis. La interfaz muestra 99 %, porque `frontend/app/src/utils/descuento.js:15` limita el porcentaje a 99 mientras el precio de oferta sea mayor que 0. Un cliente de la API que use el valor tal cual mostraría "-100 %".
- **Cómo reproducirlo:** crear una oferta sobre PROD-0001 (precio normal Q12 500) con `"precio_oferta": 1` (`POST /api/ofertas` con `rol_solicitante: "administrador"`) y ver `descuento_pct` en la respuesta y en `GET /api/ofertas`. Se reprodujo así el 2026-10-07; la oferta se finalizó después.
- **Causa:** `backend/app/blueprints/ofertas.py:136` redondea el porcentaje al entero más cercano (99,992 → 100) sin el tope que aplica el frontend.
- **Corrección:** `_descuento_pct` (`backend/app/blueprints/ofertas.py:126-140`) redondea con `ROUND_HALF_UP` y acota el resultado con piso 0 y tope 99: `min(99, max(0, ...))`. Como el backend ya rechaza `precio_oferta` menor o igual que 0, una oferta siempre cobra algo y el tope de 99 aplica en todos los casos. El piso 0 cubre el caso de un `precio_base` editado en Mongo por debajo del precio de oferta. Lo usan `POST /api/ofertas`, `GET /api/ofertas`, `GET /api/ofertas/<producto_id>` y `GET /api/vendedores/<id>/ofertas`. `frontend/app/src/utils/descuento.js` usa el `descuento_pct` del servidor cuando viene y aplica el mismo tope. Verificado el 2026-10-07 llamando a la función con el venv: Q1 sobre Q12 500 → 99; Q13 000 sobre Q12 500 → 0; Q1749 sobre Q2200 → 21; sin `precio_base` → `None`.

## H-016 — Con el valor por defecto nuevo, el carrito no expira, y el enunciado pide expiración por inactividad (2026-10-07)
- **Estado:** decidido: se mantiene (2026-10-07, ver [ADR-006](decisiones/ADR-006-carrito-sin-expiracion-por-defecto.md))
- **Severidad:** bloqueante (para la nota de la Entrega 2, no para el funcionamiento)
- **Área:** backend
- **Síntoma:** desde el 2026-10-07, si `CARRITO_TTL_SEGUNDOS` no está definida o vale `0`, el carrito no expira: cada operación le quita el TTL (`PERSIST`). El enunciado (`docs/Proyecto_TiendaYa_BasesDeDatos2.pdf`, Entrega 2) pide "carrito de compra persistente por sesión, con expiración automática por inactividad" y "un tiempo de expiración configurado explícitamente y su efecto documentado sobre el flujo de checkout"; la rúbrica le asigna 1.5 puntos a "Implementación del carrito sobre el almacén clave-valor, con expiración justificada". La expiración sigue siendo configurable (con un valor mayor que 0 funciona como en la Entrega 2), pero quien instale el proyecto desde cero con el `.env.example` actual tendrá un carrito sin expiración, y la evidencia del [informe de la Entrega 2](informe-entrega-2.md) (TTL de 1799 s) no se reproduce con ese valor.
- **Cómo reproducirlo:** con `CARRITO_TTL_SEGUNDOS=0` en el `.env` (el del `.env.example`), agregar un producto al carrito y correr `docker compose exec redis redis-cli TTL carrito:<id_usuario>`: responde `-1` (sin expiración). Verificado el 2026-10-07 con un carrito de prueba al que se le puso TTL 120: después de `GET /api/carrito/<id>` quedó en `-1`.
- **Causa:** `backend/app/config.py:25` (valor por defecto `"0"`), `.env.example` (`CARRITO_TTL_SEGUNDOS=0`) y `renovar_ttl_carrito()` en `backend/app/blueprints/carrito.py:47-57`.
- **Corrección:** sin cambio de código. Se plantearon dos opciones: volver a un valor por defecto mayor que 0 (por ejemplo `1800`), o mantener `0` y justificarlo en un ADR nuevo. El equipo decidió el 2026-10-07 **mantener `0` por defecto** y lo registró en [ADR-006](decisiones/ADR-006-carrito-sin-expiracion-por-defecto.md), que reemplaza ese punto de la Decisión 1 de [ADR-003](decisiones/ADR-003-redis-carrito-y-oferta.md) (ADR-003 lleva una nota que remite a ADR-006). La expiración por inactividad sigue configurándose explícitamente con `CARRITO_TTL_SEGUNDOS` (un valor mayor que 0 hace `EXPIRE` en cada operación, como en la Entrega 2), las reservas de oferta siguen venciendo con `RESERVA_OFERTA_TTL_SEGUNDOS`, y para demostrar la expiración se pone un valor mayor que 0 en el `.env`. La limitación (carritos abandonados que no se borran solos con el valor por defecto) quedó en "Limitaciones conocidas" del README. El README, `docs/STACK.md`, `docs/arquitectura.md` y el informe de la Entrega 2 remiten a ADR-006.

## H-015 — Stock de PROD-0004 y PROD-0014 desfasado entre PostgreSQL y MongoDB/Elasticsearch (2026-10-06)
- **Estado:** corregido en la base local (2026-10-06), con un ajuste de datos, sin cambio de código
- **Severidad:** menor
- **Área:** database
- **Síntoma:** PROD-0004 tiene 30 unidades en MongoDB y en Elasticsearch, pero 29 en el `inventario` de PostgreSQL, que es la fuente de verdad; PROD-0014 tiene 58 contra 57. El catálogo y el buscador muestran una unidad de más. El checkout no vende de más, porque valida contra PostgreSQL. Los tres motores deberían coincidir.
- **Cómo reproducirlo:** comparar `SELECT id_producto, stock_disponible FROM inventario WHERE id_producto IN (4, 14);` con el campo `stock_disponible` de los documentos con `id_sql_origen` 4 y 14 en la colección `productos` de MongoDB, y con el buscador o el catálogo. El buscador no encuentra por id interno: hay que buscar por SKU, `GET /api/busqueda?q=TSH-VINTAGE-WHT` (PROD-0004) y `GET /api/busqueda?q=TSH-CREW-BLU` (PROD-0014), o pedir el producto directo con `GET /api/productos/PROD-0004`.
- **Causa:** el desfase es anterior al outbox. La última actualización de esas filas de `inventario` es del 22 y 23 de septiembre de 2026 (compras de la Entrega 2), cuando la copia del stock a MongoDB era de mejor esfuerzo y sin reintentos. No hay eventos pendientes en `eventos_sincronizacion` para esos productos, así que el relevo no lo va a corregir solo. Se corregiría en la próxima compra de cada producto, porque el evento `stock_mongo` fija el valor absoluto de PostgreSQL.
- **Corrección:** se comparó el stock de los 1015 productos entre los tres motores. Solo difería en PROD-0004 (MongoDB/Elasticsearch 30 → 29) y PROD-0014 (58 → 57); a esos dos se les copió `stock_disponible` desde PostgreSQL con una actualización parcial del campo en MongoDB y en Elasticsearch. **Verificado:** la comparación final da 0 desfases, y el tester la volvió a correr con el mismo resultado.

## H-014 — Cambiar de página en el Historial usa filtros que no se aplicaron (2026-10-06)
- **Estado:** corregido en el árbol de trabajo (2026-10-06), pendiente de commit (`frontend/app/src/components/admin/HistorialProducto.vue`)
- **Severidad:** menor
- **Área:** frontend
- **Síntoma:** en la pestaña Historial del admin, "Anterior"/"Siguiente" vuelve a consultar con lo que está escrito en los filtros en ese momento, no con los últimos que se aplicaron con "Filtrar". Si el texto del producto no corresponde a ninguno de la lista, aparece el aviso "Selecciona un producto válido de la lista antes de filtrar", pero el número de página avanza igual: se ve "Página 3 de 51" con la tabla de la página 2 sin cambios. Debería paginar con los filtros aplicados, o al menos no cambiar de página si la carga no se hizo.
- **Cómo reproducirlo:** iniciar sesión en `/admin` con `admin@tiendaya.com`, abrir Historial, pulsar "Siguiente", escribir "xyz" en el filtro de producto sin pulsar "Filtrar" y volver a pulsar "Siguiente".
- **Causa:** `frontend/app/src/components/admin/HistorialProducto.vue:116-121`: `onCambiarPagina` asigna `pagina.value = nueva` antes de llamar a `cargarHistorial()`, y esta (`:76-87`) lee los filtros en vivo (`textoBusqueda`, `fechaDesde`, `fechaHasta`) y sale con el aviso sin consultar si el texto no resuelve a un producto.
- **Corrección:** `HistorialProducto.vue` guarda `filtrosAplicados` al pulsar "Filtrar" o "Limpiar filtros", y "Anterior"/"Siguiente" paginan solo con esos filtros, no con lo que esté escrito en los campos. `cargarHistorial(numPagina, filtros)` actualiza la página, los filtros aplicados y los eventos solo si la respuesta fue correcta; si falla, la tabla y el número de página quedan como estaban. **Verificado** por lectura del código y con llamadas a la API; la prueba visual en el navegador queda pendiente del usuario.
- **Observación (menor, no es un error):** los botones de paginación y de filtros no se desactivan mientras carga. Con la red lenta, si se pulsan varias veces seguidas, la tabla muestra la última respuesta en llegar, que no siempre es la del último clic.

## H-013 — `Paginacion.vue` ignora el `total_paginas` del buscador (2026-10-06)
- **Estado:** abierto (pendiente de decisión del equipo; latente)
- **Severidad:** menor
- **Área:** frontend
- **Síntoma:** desde la corrección de H-002, `GET /api/busqueda` limita `total_paginas` a las páginas alcanzables dentro de la ventana de 10 000 resultados de Elasticsearch, pero la página de resultados calcula sus propias páginas con el `total` completo. Con más de 10 000 resultados ofrecería páginas que responden vacías. Hoy no pasa, porque el catálogo tiene 1015 productos.
- **Cómo reproducirlo:** no se puede reproducir con los datos actuales. Se ve en el código: con `total` = 12 000 y 24 por página, `Paginacion.vue` muestra 500 páginas, y el backend solo devuelve resultados hasta la 417.
- **Causa:** `frontend/app/src/components/publico/ResultadosBusqueda.vue:205` pasa `total` a `Paginacion.vue`, que calcula `Math.ceil(total / porPagina)` (`frontend/app/src/components/comunes/Paginacion.vue:12`) y no recibe el `total_paginas` del backend.
- **Corrección (propuesta):** agregar a `Paginacion.vue` una prop opcional `totalPaginas` que, si viene, reemplace el cálculo, y pasarle `total_paginas` desde `ResultadosBusqueda.vue`. El catálogo y el historial no cambian.

## H-012 — Un número de página enorme responde 500 en el historial y el catálogo (2026-10-06)
- **Estado:** corregido en el árbol de trabajo (2026-10-06), pendiente de commit (`backend/app/blueprints/historial.py`, `backend/app/blueprints/catalogo.py`)
- **Severidad:** menor
- **Área:** backend
- **Síntoma:** `GET /api/historial?pagina=10000000000000000000` y `GET /api/productos?pagina=10000000000000000000` responden `500` con `OverflowError: MongoDB can only handle up to 8-byte ints`. Deberían responder como cualquier página posterior a la última (`200` con la lista vacía y el `total` real) o con un `400`. En el catálogo el error es anterior a las correcciones de este día. No es alcanzable desde la interfaz.
- **Cómo reproducirlo:** `curl "http://127.0.0.1:8000/api/historial?pagina=10000000000000000000"` (y lo mismo con `/api/productos`).
- **Causa:** el salto `(pagina - 1) * por_pagina` no cabe en un entero de 8 bytes de MongoDB: `backend/app/blueprints/historial.py:96` (`$skip`) y `backend/app/blueprints/catalogo.py:221` (`cursor.skip`). Ninguno de los dos pone tope a `pagina`.
- **Corrección:** `historial.py` topa el `$skip` con `SALTO_MAXIMO = 2**63 - 1` (`historial.py:11` y `:100`), el mayor entero que acepta MongoDB y que sigue quedando más allá de cualquier total real. `catalogo.py` no consulta la página si el salto es mayor o igual que el `total` (`catalogo.py:223-224`) y devuelve `items` vacíos con el `total` real. `GET /api/busqueda` ya era seguro por la ventana de 10 000 resultados (H-002). **Verificado por el tester:** 238/238 casos (`pagina` 10^19, 10^30, 2^63, 2^64 y 999, con y sin filtros) responden `200` con la lista vacía y el `total` real, y los recorridos completos de ambas rutas siguen sin duplicados.

## H-011 — El feed del Historial solo mostraba los 50 eventos más recientes (2026-10-06)
- **Estado:** corregido en el árbol de trabajo (2026-10-06), pendiente de commit (`backend/app/blueprints/historial.py`, `frontend/app/src/components/admin/HistorialProducto.vue`)
- **Severidad:** menor (mejora pedida por el usuario)
- **Área:** backend, frontend
- **Síntoma:** `GET /api/historial` devolvía solo los 50 eventos más recientes (como máximo 200 con `limit`), sin el total ni forma de ver los anteriores. La base tiene 1016 eventos, así que la pestaña Historial del admin escondía casi todos. Debería poder recorrerlos todos.
- **Cómo reproducirlo (antes de la corrección):** `curl "http://127.0.0.1:8000/api/historial"` devolvía `{"eventos": [...]}` con 50 eventos y ningún total.
- **Causa:** `backend/app/blueprints/historial.py` (commit `785789d`) aplicaba `{"$limit": limit}` con `LIMIT_DEFAULT = 50` y `LIMIT_MAXIMO = 200`, y el componente no tenía paginación.
- **Corrección:** `GET /api/historial` ahora está paginado: acepta `pagina` y `por_pagina` (20 por defecto, máximo 100; `limit` se acepta como alias de `por_pagina`; valores no numéricos responden `400`) y devuelve `{eventos, total, pagina, por_pagina, total_paginas}`. Ordena por `fecha_evento` descendente con desempate por `_id`, y cuenta y pagina en una sola consulta con `$facet`; sin filtro de vendedor, el `$lookup` al producto se hace solo sobre la página. En el frontend, `HistorialProducto.vue` usa `components/comunes/Paginacion.vue`, muestra "N eventos" y vuelve a la página 1 al pulsar "Filtrar" o "Limpiar filtros". **Verificado:** los 1016 eventos recorridos sin duplicados con 20, 37 y 100 por página, y con filtros combinados. Queda abierto H-014.

## H-010 — La paginación de `GET /api/productos` repetía y saltaba productos (2026-10-06)
- **Estado:** corregido en el árbol de trabajo (2026-10-06), pendiente de commit (`backend/app/blueprints/catalogo.py`)
- **Severidad:** menor
- **Área:** backend
- **Síntoma:** al recorrer las 43 páginas de 24 productos de `GET /api/productos`, llegaban 1015 ítems, pero solo 1001 distintos: algunos productos aparecían en dos páginas y 14 no aparecían nunca. Cada producto debería aparecer exactamente una vez.
- **Cómo reproducirlo (antes de la corrección):** pedir `GET /api/productos?pagina=N` para N de 1 a 43 y contar los `_id` distintos.
- **Causa:** `backend/app/blueprints/catalogo.py` (commit `785789d`) ordenaba solo por `precio_base` (o solo por `textScore` con `q`). Con precios empatados, MongoDB no garantiza el mismo orden entre consultas, y `skip`/`limit` cortaba en lugares distintos.
- **Corrección:** se agregó `_id` como desempate: `precio_base` + `_id` sin `q`, y `textScore` + `_id` con `q` (`catalogo.py:199-207`). **Verificado:** total = recibidos = distintos con 24 y con 100 por página, con y sin filtros.

## H-009 — Discrepancias entre la documentación y el código (2026-10-06)
- **Estado:** corregido en `README.md`, `docs/arquitectura.md`, `docs/estrategia-consistencia-checkout.md`, `docs/decisiones/ADR-004-motor-de-busqueda.md`, `docs/informe-entrega-3.md`, `docs/STACK.md` y `frontend/app/README.md` (cambio de documentación del 2026-10-06).
- **Severidad:** documentación
- **Área:** documentación
- **Síntoma:** varios documentos decían cosas que el código no hace o con cifras desactualizadas:
  - El README describía `prueba_fallas_checkout.py` como "5 fallas simuladas"; en realidad son camino feliz + 4 fallas simuladas (E0-E4) + caída real de Elasticsearch (E5).
  - "Novedades de la Entrega 3" no nombraba las variables opcionales `ES_ALIAS_PRODUCTOS`, `OUTBOX_INTERVALO_SEGUNDOS` y `OUTBOX_MAX_INTENTOS`, ni ofrecía alternativa sin `psql` para la migración; el paso 3 no tenía atajo en Python para `CREATE DATABASE`.
  - Las credenciales de prueba no decían que el vendedor tampoco ve la pestaña Sincronización (`frontend/app/src/components/admin/SidebarAdmin.vue:50`).
  - El README no aclaraba que el backend usa la base Mongo `tiendaya_nosql` fija (`backend/app/extensions.py:22`) y que `MONGO_DB_NAME` solo la leen dos scripts de migración.
  - El diagrama de `docs/arquitectura.md` dibujaba el respaldo del buscador como `busqueda.py` → MongoDB; en realidad `busqueda.py` responde 503 y es el frontend (`ResultadosBusqueda.vue:78`) el que llama a `GET /api/productos?q=` (`catalogo.py`, `$text`). Tampoco mostraba que `checkout.py` procesa los eventos del outbox en el acto tras el COMMIT (`checkout.py:415`), no solo el relevo.
  - Las ventanas de consistencia decían "de 8 a 25 s" (`arquitectura.md`) y "8 a 20 s" (`estrategia-consistencia-checkout.md`); la evidencia registra 20 s (E4) y 25 s (E5).
  - ADR-004 y el informe de la Entrega 3 hablaban de 1019 productos (son 1015) y de 126 claves de atributos (124 medidas el 2026-10-06).
  - `docs/STACK.md` omitía el buscador y "Mi cuenta" en `VistaPublica.vue`, ventas y sincronización en `VistaAdmin.vue`, el `usePolling` de `vite.config.js` y las rutas `GET`/`DELETE /api/ofertas/<producto_id>` (`ofertas.py:198,329`).
  - `frontend/app/README.md` decía que el build queda en `app/dist/`; el README raíz dice `frontend/app/dist/`.
- **Cómo reproducirlo:** comparar cada afirmación con el archivo de código citado.
- **Causa:** documentación escrita antes de los últimos cambios de la Entrega 3 o con cifras de una medición anterior.
- **Corrección:** se corrigió cada punto en el documento correspondiente. En ADR-004 (ya aceptado) solo se corrigieron las cifras, con una nota que indica la fecha de la corrección; la decisión no cambia. Además se agregó este registro al README (Estado del proyecto y Estructura del repositorio) y se anotó H-001 en "Limitaciones conocidas".

## H-008 — `.gitignore` no ignora respaldos del `.env` (2026-10-06)
- **Estado:** corregido en el árbol de trabajo (2026-10-06), pendiente de commit (`.gitignore`)
- **Severidad:** menor
- **Área:** repositorio
- **Síntoma:** `.gitignore` solo ignora `.env`. Un respaldo como `.env.bak` (hay uno sin seguimiento en el repo local) aparece como archivo nuevo y se podría subir por error con las contraseñas. Debería quedar ignorado.
- **Cómo reproducirlo:** `cp .env .env.bak` y luego `git status`: `.env.bak` aparece como archivo sin seguimiento.
- **Causa:** `.gitignore` tiene la regla `.env`, que no cubre `.env.*`.
- **Corrección:** se agregaron a `.gitignore` las reglas `.env.*` y `!.env.example`, con un comentario. **Verificado:** `git check-ignore -v .env.bak` responde con la regla `.env.*`, y `.env.example` sigue sin ignorarse (versionado).

## H-007 — `docs/hola.html` es un archivo vacío (2026-10-06)
- **Estado:** corregido en el árbol de trabajo (2026-10-06), pendiente de commit (`docs/hola.html` borrado)
- **Severidad:** menor
- **Área:** repositorio
- **Síntoma:** `docs/hola.html` pesa 0 bytes y ningún documento ni código lo referencia. No aporta nada a la entrega y puede confundir al catedrático.
- **Cómo reproducirlo:** `wc -c docs/hola.html` (0) y `git log --oneline -- docs/hola.html` (commit `38580f9`, "Create hola.html").
- **Causa:** se agregó desde la interfaz de GitHub sin contenido.
- **Corrección:** se borró el archivo (borrado ya preparado en el índice de git). **Verificado:** `docs/hola.html` ya no existe y ningún documento del repositorio lo menciona, salvo este registro.

## H-006 — `docs/guia-funcionalidades.docx` desactualizada (2026-10-06)
- **Estado:** abierto (pendiente de regenerar)
- **Severidad:** documentación
- **Área:** documentación
- **Síntoma:** la guía en Word refleja la Entrega 2. Afirma cosas que ya no son ciertas:
  - "4 bases de datos" / "cuatro motores" (secciones 2 y 6): son cinco, con Elasticsearch.
  - "No hay sincronización automática" entre bases: el checkout usa un outbox con relevo y reintentos.
  - "Editar un producto desde el panel admin solo actualiza Mongo": también actualiza el stock en el `inventario` de PostgreSQL y reindexa en Elasticsearch (`backend/app/blueprints/catalogo.py:474-497`).
  - Sección 4.6, sobre el fallo al borrar el carrito tras la compra: hoy es el evento `limpiar_carrito` del outbox, que se reintenta, y un checkout con otra clave sobre el carrito viejo responde `409 CARRITO_VACIO`.
  - Sección 5, "catálogo y stock no se sincronizan automáticamente": falso para el stock (outbox).
  - "Redis es obligatorio para arrancar el backend": falso; los scripts Lua se cargan la primera vez que se usan (`backend/app/ofertas_redis.py:57-63`).
  - Sección 4.3 describe `GET /api/productos` como una lista; desde la Entrega 2 devuelve `{items, total, pagina, por_pagina, total_paginas}`.

  Y no menciona: el buscador con Elasticsearch (`busqueda.py`, `busqueda_es.py`, `ResultadosBusqueda.vue`, autocompletado en `NavPublica.vue`, facetas, "¿Quisiste decir…?" y respaldo a MongoDB), la clave de idempotencia y el botón "Reintentar compra", el outbox con su relevo y el panel Sincronización, las fallas simuladas y los scripts de prueba, la paginación, "Mi cuenta" completo (perfil y direcciones, máximo 3, `409`), las filas de Búsqueda y Sincronización en la tabla de la sección 3, ni los enlaces a `docs/estrategia-consistencia-checkout.md`, ADR-004, ADR-005, `docs/informe-entrega-3.md` y `docs/evidencia/`.

  Actualización del 2026-10-07: tampoco cubre los cambios posteriores a la Entrega 3: el listado público de ofertas (`GET /api/ofertas`, botón "Ofertas" de la barra, página de ofertas flash y franja encima del catálogo; `ofertas.py`, `ofertas_redis.py`, `OfertasFlash.vue`, `FranjaOfertasFlash.vue`, `TarjetaOfertaPublica.vue`, `useOfertasFlash.js`), el precio de oferta con cuenta regresiva en la página del producto (`VistaDetalleProducto.vue`), la pestaña "Ofertas flash" del vendedor (`GET /api/vendedores/<id>/ofertas`, `GestionOfertas.vue`, `FormularioOferta.vue`, `TarjetaOferta.vue`), "Mis ventas" para el administrador con `rol_solicitante` e `id_usuario` obligatorios, y el carrito sin expiración por defecto (`CARRITO_TTL_SEGUNDOS=0`, ver H-016 y ADR-006). Si la guía describe el carrito como "expira a los 30 minutos", eso ya no es el valor por defecto. Tampoco cubre la franja de ofertas dentro de `CatalogoProductos.vue` (encima de la grilla, contraíble), la etiqueta "⚡ -X%" en `TarjetaProducto.vue`, los filtros de la página de ofertas (en el navegador, distintos de los del sidebar del catálogo) ni `descuento_pct` en `GET /api/ofertas/<producto_id>`.
- **Cómo reproducirlo:** abrir `docs/guia-funcionalidades.docx` y compararlo con el README y el código citado.
- **Causa:** la guía se generó con el estado de la Entrega 2 (commit `07e8bde`) y no se actualizó con la Entrega 3.
- **Corrección (propuesta):** regenerar la guía con los puntos de arriba. Es un archivo binario: no se edita a mano desde el repositorio; lo decide y coordina el orquestador.

## H-005 — Los resultados del buscador no muestran atributos (2026-10-06)
- **Estado:** abierto (decidir si es el comportamiento deseado)
- **Severidad:** menor
- **Área:** frontend
- **Síntoma:** en la página de resultados de búsqueda, las tarjetas de producto no muestran los chips de atributos (marca, capacidad, etc.) que sí aparecen en el catálogo. No da error.
- **Cómo reproducirlo:** buscar "laptop" en la barra del sitio público y comparar las tarjetas con las de la categoría Laptops del catálogo.
- **Causa:** `GET /api/busqueda` no devuelve `atributos` en cada resultado (`backend/app/busqueda_es.py`, armado de `items`), y `TarjetaProducto.vue` usa `props.producto.atributos || {}`, así que no muestra nada.
- **Corrección (propuesta):** decidir si se quiere mostrar atributos en los resultados. Si sí, devolverlos desde `busqueda_es.py` (el índice ya los guarda, en el campo `flattened`); si no, cerrar la entrada como descartada.

## H-004 — Reintento de checkout con `id_comprador` como texto responde 409 (2026-10-06)
- **Estado:** corregido en el árbol de trabajo (2026-10-06), pendiente de commit (`backend/app/blueprints/checkout.py`)
- **Severidad:** menor
- **Área:** backend
- **Síntoma:** al repetir `POST /api/checkout` con la misma clave de idempotencia del propio comprador, pero mandando `id_comprador` como string (`"12"`), responde `409 CLAVE_IDEMPOTENCIA_AJENA`. Debería responder `200` con `"repetido": true` y el mismo pedido. El frontend manda un número, así que no afecta a la interfaz.
- **Cómo reproducirlo:** hacer un checkout con `{"id_comprador": 12, ..., "clave_idempotencia": "prueba-h004-0001"}` y repetirlo con `"id_comprador": "12"` y la misma clave.
- **Causa:** `backend/app/blueprints/checkout.py:185` y `:330` comparan el `id_comprador` entero guardado en la BD con el valor crudo del JSON.
- **Corrección:** un helper nuevo, `_id_entero` (`checkout.py:145-156`), normaliza `id_comprador` a entero al inicio de `procesar_checkout` (`checkout.py:182-186`), antes de compararlo con la clave de idempotencia, de armar la clave del carrito y de llamar al procedimiento. Acepta un entero positivo o un string con dígitos (`"12"`); cualquier otro valor (`"abc"`, `0`, negativos, `true`, decimales) responde `400` con "id_comprador debe ser un número entero positivo". **Verificado:** `POST /api/checkout` con `"id_comprador": "abc"` responde `400` con ese mensaje, sin tocar el carrito ni la base, y `prueba_fallas_checkout.py --caida-real` sigue en 45/45. El reintento con `"12"` y la misma clave no se volvió a ejecutar a mano en esta verificación: queda cubierto por la lectura del código, porque las comparaciones con la clave guardada (`checkout.py:204` y `:349` en el árbol de trabajo) ahora reciben el entero normalizado.

## H-003 — `precio_min=nan` o `precio_max=inf` en el buscador responden 503 (2026-10-06)
- **Estado:** corregido en el árbol de trabajo (2026-10-06), pendiente de commit (`backend/app/blueprints/busqueda.py`)
- **Severidad:** menor
- **Área:** backend
- **Síntoma:** `GET /api/busqueda?q=mouse&precio_min=nan` (o `precio_max=inf`) pasa la validación y Elasticsearch lo rechaza; el backend responde `503 BUSCADOR_NO_DISPONIBLE`, como si el motor estuviera caído. Debería responder `400` con un mensaje de parámetro inválido.
- **Cómo reproducirlo:** `curl "http://127.0.0.1:8000/api/busqueda?q=mouse&precio_min=nan"`
- **Causa:** `backend/app/blueprints/busqueda.py:48-58`: `_decimal` acepta cualquier `float()`, incluidos `nan` e `inf`, porque no comprueba `math.isfinite`.
- **Corrección:** `_decimal` rechaza los valores no finitos con `math.isfinite` (`busqueda.py:76-77`), y la ruta responde `400` con "'precio_min' debe ser un número finito". **Verificado:** el comando de arriba responde `400`.

## H-002 — Páginas muy altas del buscador responden 503 (2026-10-06)
- **Estado:** corregido en el árbol de trabajo (2026-10-06), pendiente de commit (`backend/app/busqueda_es.py`, `backend/app/blueprints/busqueda.py`)
- **Severidad:** menor
- **Área:** backend
- **Síntoma:** `GET /api/busqueda?q=mouse&pagina=500` responde `503 BUSCADOR_NO_DISPONIBLE`. Elasticsearch rechaza la consulta porque `from + size` supera su `max_result_window` (10 000), y el backend trata ese rechazo como una caída. El frontend caería entonces al respaldo de MongoDB y mostraría "búsqueda simplificada" aunque el motor esté funcionando. Debería devolver una página vacía o un `400`.
- **Cómo reproducirlo:** `curl "http://127.0.0.1:8000/api/busqueda?q=mouse&pagina=500"`
- **Causa:** `backend/app/blueprints/busqueda.py:95` no pone tope a `pagina`; `backend/app/busqueda_es.py:236` calcula `from = (pagina - 1) * por_pagina`; y `busqueda.py:104` atrapa `ApiError` (incluido un `400` de Elasticsearch) junto con los errores de conexión y responde 503.
- **Corrección:** dos cambios.
  - `busqueda_es.py` define `MAX_VENTANA_RESULTADOS = 10000`. Si la página pedida empieza fuera de esa ventana, hace la misma consulta con `size` 0 y responde `200` con `items` vacíos, pero con el `total`, las facetas y la sugerencia reales; la última página alcanzable se recorta para no pasarse. `total_paginas` cuenta solo las páginas que caben en la ventana.
  - `busqueda.py` distingue un rechazo de la consulta de una caída: si Elasticsearch responde `400`, la API responde `400 BUSQUEDA_NO_VALIDA` (y el frontend no cae al respaldo); el `503 BUSCADOR_NO_DISPONIBLE` queda solo para errores de conexión, timeout, índice o alias inexistente (`404`), `401`/`403`, `429` y `5xx`. Vale para `GET /api/busqueda` y para `GET /api/busqueda/autocompletar`.

  **Verificado:** el comando de arriba responde `200` con `items` vacíos, `total` 40 y `total_paginas` 2; `prueba_buscador.py --caida-real` sigue en 21/21 (con Elasticsearch detenido de verdad responde `503`). Queda abierto H-013, del lado del frontend.

## H-001 — La pestaña Historial del admin no carga (2026-10-06)
- **Estado:** corregido en el árbol de trabajo (2026-10-06), pendiente de commit (`frontend/app/src/components/admin/HistorialProducto.vue`)
- **Severidad:** bloqueante
- **Área:** frontend
- **Síntoma:** al abrir `/admin/historial`, el selector de productos no carga y la consola muestra "data is not iterable". Debería listar todos los productos (o los del vendedor) para elegir uno y ver su historial. Ya estaba anotado en [`STACK.md`](STACK.md) (bitácora de la Entrega 2, catálogo paginado).
- **Cómo reproducirlo:** iniciar sesión en `/admin` con `admin@tiendaya.com` y abrir la pestaña Historial; o `curl "http://127.0.0.1:8000/api/productos"` y ver que la respuesta es un objeto, no una lista.
- **Causa:** `frontend/app/src/components/admin/HistorialProducto.vue:22-23` hace `[...(data || [])]` sobre la respuesta de `GET /api/productos`, que desde la Entrega 2 devuelve `{items, total, pagina, por_pagina, total_paginas}`. Aunque leyera `data.items`, solo recibiría la primera página (24 productos).
- **Corrección:** `cargarProductos` (`HistorialProducto.vue:29-53`) pide la primera página de `GET /api/productos` con `por_pagina=100` (filtrada por `vendedor_id` si quien entra es un vendedor) y el resto de las páginas en paralelo, según `total_paginas`, y junta los `items`. Si alguna página falla, avisa que la lista quedó incompleta. Para que el recorrido no repita ni salte productos hizo falta además corregir el orden del catálogo (H-010). Se quitó la viñeta correspondiente de "Limitaciones conocidas" del README. **Verificado contra la API**, con el mismo recorrido que hace el componente: `GET /api/productos?por_pagina=100`, páginas 1 a 11, devuelve 1015 productos, todos distintos.
