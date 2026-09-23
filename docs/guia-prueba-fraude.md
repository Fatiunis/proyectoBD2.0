# Guía: probar la detección de fraude en reseñas

Esta guía explica cómo provocar a propósito una alerta de fraude, verla en el panel admin, entender por qué se disparó y limpiar los datos de prueba después.

## 1. Qué detecta el sistema

`GET /api/fraude/alertas` (`backend/app/blueprints/fraude.py`) busca en Neo4j **tríos de cuentas** `(:Cuenta)-[:CALIFICO]->(:Producto)` en los que **cada uno de los 3 pares** cumple las tres señales a la vez:

| Señal | Regla | Valor por defecto |
|---|---|---|
| Productos compartidos | Las dos cuentas calificaron los mismos productos | al menos **3** productos (`min_productos_compartidos`) |
| Calificación perfecta | Ambas calificaciones son de **5 estrellas** | fijo |
| Ventana de tiempo corta | Las dos reseñas de cada producto se publicaron con poca diferencia | a lo sumo **6 horas** (`ventana_segundos = 21600`) |

Si falla una sola señal en un solo par, el trío no aparece. Por eso dos cuentas que coinciden por azar no generan alertas: además tendrían que coincidir en 5★ y en la misma ventana de pocas horas.

**Cómo leer una alerta:**
- `cuentas_involucradas`: las 3 cuentas del trío.
- `productos_compartidos`: la unión de los productos de los 3 pares. Un producto aparece repetido si lo comparten varios pares; el panel muestra los productos sin repetir.
- `score_anomalia`: la suma de los productos compartidos por cada par. Si 3 cuentas comparten los mismos 3 productos, el score es 3 + 3 + 3 = **9**.
- Un anillo de 4 cuentas genera 4 alertas, una por cada trío posible (C(4,3) = 4). No es un error.

**De dónde salen los datos del grafo:** cada reseña publicada con `POST /api/resenas` se guarda en MongoDB (`tiendaya_nosql.resenas`) y se copia a Neo4j como relación `CALIFICO`, con `calificacion` y `fecha`. Si Neo4j está caído, la reseña se guarda igual en Mongo pero no llega al grafo, y entonces no puede generar alertas.

## 2. Requisitos previos

- Backend en `http://127.0.0.1:8000`, con PostgreSQL, MongoDB, Redis y **Neo4j** corriendo. Neo4j y Redis corren con `docker compose up -d`.
- Frontend en `http://localhost:5173`.
- Compradores de `datos_semilla_usuarios.sql`. La contraseña de todos es `Tiendaya123!`.
- Para ver el panel de fraude: `admin@tiendaya.com` / `Tiendaya123!`. Una cuenta **vendedor** no ve la pestaña Fraude.

## 3. Prueba que ya se hizo (2026-09-23)

Ya hay una alerta de prueba creada con el flujo real (`POST /api/resenas`):

| Cuenta | id_usuario | PROD-0107 (iPhone 15 256GB Grafito) | PROD-0108 (iPhone 13 256GB Blanco) | PROD-0109 (iPhone 13 256GB Plata) |
|---|---|---|---|---|
| Paola Morales | 16 | 5★ | 5★ | 5★ |
| Daniela Ortiz | 18 | 5★ | 5★ | 5★ |
| Andres Vasquez | 21 | 5★ | 5★ | 5★ |
| Gabriela Ramos (**control**) | 20 | 5★ | 5★ | — |

**Resultado:**
- Aparece la alerta **Andres Vasquez, Paola Morales, Daniela Ortiz**, con productos `PROD-0107, PROD-0108, PROD-0109` y **score 9**.
- Gabriela Ramos **no** aparece: comparte solo 2 productos con cada cuenta del anillo y el mínimo es 3. Muestra que el umbral funciona.
- Las otras 4 alertas son el anillo que siembra `database/migrations/sembrar_resenas_fraude.py`: Carlos Mendez, Sofia Lopez, Maria Torres y Jose Ramirez, en 4 tríos con score 12.

Todas las reseñas de esta prueba tienen el texto `[prueba fraude]`, así que son fáciles de encontrar y borrar (ver la sección 7).

## 4. Hacer una prueba nueva por tu cuenta

### 4.1 Elegir cuentas y productos

- **3 compradores** que vayan a formar el anillo.
- **Opcional, 1 comprador de control**, que califique solo 2 de los productos.
- **3 productos** que esas cuentas **no hayan reseñado nunca**. Una cuenta solo puede reseñar cada producto una vez: el índice único `producto_id + autor.id_usuario` devuelve 409 "Ya reseñaste este producto".

Para ver qué productos ya tienen reseñas (en mongosh, base `tiendaya_nosql`):

```js
db.resenas.distinct("producto_id")
```

Y para elegir productos sin reseñas de una categoría:

```js
db.productos.find(
  { _id: { $nin: db.resenas.distinct("producto_id") }, "categoria.nombre": "Tablets" },
  { _id: 1, nombre: 1 }
).limit(3)
```

### 4.2 Opción A: desde la página (lo más parecido al uso real)

1. Entra a `http://localhost:5173` con el primer comprador del anillo.
2. Abre cada uno de los 3 productos (`/producto/PROD-XXXX`) y deja una reseña de **5 estrellas** con cualquier texto. Conviene incluir `[prueba fraude]` para poder limpiarla después.
3. Cierra sesión y repite con el segundo y el tercer comprador, **todo dentro de las mismas 6 horas**.
4. Opcional: entra con el comprador de control y califica solo 2 de los 3 productos.

### 4.3 Opción B: con la API (más rápido)

En **PowerShell**, cambiando los IDs, nombres y productos:

```powershell
$anillo    = @(@{id=14; nombre="Ana Gutierrez"}, @{id=15; nombre="Luis Fernandez"}, @{id=17; nombre="Roberto Castillo"})
$productos = @("PROD-0200", "PROD-0201", "PROD-0202")

foreach ($c in $anillo) {
  foreach ($p in $productos) {
    $body = @{
      rol_solicitante = "comprador"
      producto_id     = $p
      id_usuario      = $c.id
      nombre_autor    = $c.nombre
      calificacion    = 5
      texto           = "Excelente, 100% recomendado. [prueba fraude]"
    } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/resenas" -Method POST `
           -ContentType "application/json; charset=utf-8" -Body $body -UseBasicParsing
    "$($c.nombre) $p -> $($r.StatusCode)"
  }
}
```

Cada línea debe mostrar `201`. Si ves `409`, esa cuenta ya había reseñado ese producto: elige otro.

## 5. Verificar el resultado

### 5.1 En el panel admin

1. Entra a `http://localhost:5173/admin` con `admin@tiendaya.com` / `Tiendaya123!`.
2. Abre la pestaña **Fraude** (`/admin/fraude`).
3. Busca la fila con tus 3 cuentas. Deberías ver los 3 productos y un **score de 9**.
4. Pulsa **"Ver detalle"** para ver el JSON completo de la alerta. Ahí se ve **por qué** se disparó: las 3 cuentas, la lista `productos_compartidos` (cada producto aparece una vez por cada par que lo comparte) y el `score_anomalia`.
5. Comprueba que la cuenta de control **no** aparece en ninguna fila.

### 5.2 Con la API

```powershell
(Invoke-RestMethod "http://127.0.0.1:8000/api/fraude/alertas?rol_solicitante=administrador").alertas |
  ForEach-Object { "$($_.cuentas_involucradas.nombre -join ', ')  | score $($_.score_anomalia)" }
```

El panel siempre usa los parámetros por defecto. Para probar otros, pásalos en la URL:

```
http://127.0.0.1:8000/api/fraude/alertas?rol_solicitante=administrador&min_productos_compartidos=2&ventana_segundos=3600
```

Con `min_productos_compartidos=2`, la cuenta de control **sí** entra a un trío. Es una buena forma de ver que el umbral es lo que la dejaba fuera.

### 5.3 En Neo4j Browser (el "por qué" en detalle)

Abre `http://localhost:7474` y ejecuta, cambiando los `id_usuario`:

```cypher
MATCH (c:Cuenta)-[r:CALIFICO]->(p:Producto)
WHERE c.id_usuario IN [16, 18, 21, 20]
RETURN c.nombre AS cuenta, p.id_producto AS producto, r.calificacion AS estrellas, r.fecha AS fecha
ORDER BY producto, fecha
```

En la tabla se ven las tres señales: los mismos productos, 5 estrellas y fechas separadas por minutos. En la vista de grafo (quita el `RETURN` de columnas y usa `RETURN c, r, p`) el anillo se ve como tres cuentas que apuntan a los mismos productos.

## 6. Casos negativos para comprobar que no hay falsos positivos

| Caso | Cómo provocarlo | Resultado esperado |
|---|---|---|
| Solo 2 productos compartidos | La cuenta de control califica 2 de los 3 productos | No aparece |
| Una calificación de 4★ | Una cuenta del anillo pone 4★ en uno de los productos (con otro producto nuevo, porque no se puede reseñar dos veces) | Ese par baja a 2 productos compartidos y el trío desaparece |
| Reseñas separadas por más de 6 horas | Publica las reseñas de una cuenta al día siguiente, o consulta con `ventana_segundos=60` si las publicaste con más de un minuto de diferencia | El trío desaparece |
| Solo 2 cuentas | Solo 2 compradores califican los mismos productos | No hay trío, así que no hay alerta |

La API no permite elegir la fecha de una reseña (usa la hora actual). Para simular reseñas antiguas sin esperar, cambia la fecha en Neo4j. Esto es solo para pruebas:

```cypher
MATCH (c:Cuenta {id_usuario: 21})-[r:CALIFICO]->(p:Producto {id_producto: "PROD-0109"})
SET r.fecha = "2026-09-01T10:00:00-06:00"
```

## 7. Limpiar los datos de prueba

Las reseñas viven en **dos** lugares, así que hay que borrarlas de ambos.

**MongoDB** (mongosh, base `tiendaya_nosql`):

```js
db.resenas.find({ texto: /\[prueba fraude/ }).count()   // revisa cuántas son antes de borrar
db.resenas.deleteMany({ texto: /\[prueba fraude/ })
```

**Neo4j** (Neo4j Browser). Cambia las cuentas y los productos por los de tu prueba:

```cypher
MATCH (c:Cuenta)-[r:CALIFICO]->(p:Producto)
WHERE c.id_usuario IN [16, 18, 21, 20]
  AND p.id_producto IN ["PROD-0107", "PROD-0108", "PROD-0109"]
DELETE r
```

Para la prueba del 2026-09-23 esos son exactamente los valores de arriba: 11 reseñas en total, 9 del anillo y 2 de control.

**No** borres con un filtro amplio, como todas las relaciones de una cuenta, porque se perderían las reseñas sembradas por `sembrar_resenas_fraude.py`. Si el grafo queda desordenado, puedes volver a correr ese script: reconstruye `resenas` y el grafo de reseñas desde cero, pero es destructivo con **todas** las reseñas.

## 8. Problemas comunes

| Síntoma | Causa probable |
|---|---|
| Las reseñas se crean (201), pero no aparece la alerta | Neo4j no estaba corriendo al publicarlas. Mira la consola del backend: aparece `[resenas] ADVERTENCIA: no se pudo sincronizar...`. Hay que borrarlas y volver a publicarlas con Neo4j arriba. |
| No aparece la pestaña Fraude | La sesión es de un vendedor. Entra con `admin@tiendaya.com`. |
| 409 "Ya reseñaste este producto" | Esa cuenta ya había reseñado ese producto. Elige otro producto. |
| 403 "Solo un comprador puede publicar reseñas" | Falta `rol_solicitante: "comprador"` en el cuerpo, o la sesión de la página no es de comprador. |
| La alerta aparece varias veces con cuentas distintas | Hay 4 o más cuentas conectadas entre sí: cada trío posible es una alerta. |
