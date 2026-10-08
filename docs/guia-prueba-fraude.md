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

## 9. Detección ampliada (2026-10-07)

Las secciones 1 a 8 siguen valiendo para la consulta original de anillos (`GET /api/fraude/alertas`), que no cambió. Esta sección explica cómo probar los **4 patrones nuevos**: `cuenta_rafaga`, `grupo_coordinado`, `sesgo_vendedor_sin_compra` y `cuentas_vinculadas`. Qué detecta cada uno, sus consultas y cómo se calcula el score están en [`deteccion-fraude-ampliada.md`](deteccion-fraude-ampliada.md).

Los pasos de esta sección se ejecutaron por la API el 2026-10-07 con las cuentas y productos que aparecen abajo: dieron los resultados indicados, y la limpieza del 9.5 dejó la base igual que antes.

### 9.1 Antes de empezar

- Además de lo de la sección 2, el grafo necesita los datos nuevos: corre una vez `venv\Scripts\python.exe database\migrations\sincronizar_grafo_fraude.py` (macOS/Linux: `venv/bin/python database/migrations/sincronizar_grafo_fraude.py`). Si ya corriste `sembrar_fraude_ampliado.py`, no hace falta, porque lo llama al final.
- **Usa cuentas sin reseñas.** Si una cuenta ya tiene reseñas, se suman a las de la prueba y el resultado cambia. En esta instalación, las cuentas `@fraude-demo.tiendaya.gt` con `id_usuario` 66 a 80 (de una versión anterior de la semilla) no tienen reseñas, direcciones ni pedidos. Para confirmarlo en tu máquina (mongosh, base `tiendaya_nosql`), debe dar `0`:

  ```js
  db.resenas.countDocuments({ "autor.id_usuario": { $in: [66,67,68,69,70,71,72,73,74,75,76,77,78] } })
  ```

  Y para ver sus IDs y nombres (psql, base `tiendaya_db`):

  ```sql
  SELECT id_usuario, nombre, email FROM usuarios WHERE email LIKE '%@fraude-demo.tiendaya.gt' ORDER BY id_usuario;
  ```

- Las reseñas de estas cuentas son **sin compra verificada** (no tienen pedidos), que es lo que buscan tres de los patrones.
- Usa un texto con la marca `[prueba ampliada]` para poder borrar todo después.
- **Usa cada cuenta en una sola prueba.** Si la misma cuenta participa en dos pruebas, sus reseñas se mezclan y puede aparecer en otro patrón.

Para no repetir el bloque de la sección 4.3, define estas dos funciones en **PowerShell** (cambia los nombres si tus IDs son otros):

```powershell
$nombres = @{66="Oscar Monterroso"; 67="Brenda Sagastume"; 68="Hector Cifuentes"; 69="Mariela Pineda";
             70="Walter Estrada"; 71="Diego Coronado"; 72="Karla Velasquez"; 73="Marvin Galindo";
             74="Silvia Herrera"; 75="Erick Samayoa"; 76="Andrea Lemus"; 77="Byron Quinonez"; 78="Claudia Arevalo"}

function Resena($id, $producto, $estrellas) {
  $body = @{ rol_solicitante = "comprador"; producto_id = $producto; id_usuario = $id
             nombre_autor = $nombres[$id]; calificacion = $estrellas
             texto = "Resena de prueba. [prueba ampliada]" } | ConvertTo-Json
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/resenas" -Method POST `
         -ContentType "application/json; charset=utf-8" -Body $body -UseBasicParsing
  "$id $producto $estrellas -> $($r.StatusCode)"
}

function Direccion($id, $linea1, $postal) {
  $body = @{ direccion_linea1 = $linea1; ciudad = "Guatemala"; departamento_estado = "Guatemala"
             codigo_postal = $postal } | ConvertTo-Json
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/usuarios/$id/direcciones" -Method POST `
         -ContentType "application/json; charset=utf-8" -Body $body -UseBasicParsing
  "direccion de $id -> $($r.StatusCode)"
}
```

En macOS/Linux, la misma reseña con `curl`:

```bash
curl -s -X POST http://127.0.0.1:8000/api/resenas -H "Content-Type: application/json" \
  -d '{"rol_solicitante":"comprador","producto_id":"PROD-0024","id_usuario":66,"nombre_autor":"Oscar Monterroso","calificacion":4,"texto":"Resena de prueba. [prueba ampliada]"}'
```

Cada reseña debe responder `201` y cada dirección también. Los productos de los ejemplos no tenían reseñas el 2026-10-07; si ves `409`, elige otro con la consulta de la sección 4.1. Para el sesgo hacen falta 3 productos **del mismo vendedor**:

```js
db.productos.find({ "vendedor.id_vendedor": 2, activo: true, _id: { $nin: db.resenas.distinct("producto_id") } },
                  { _id: 1, nombre: 1, "vendedor.nombre_comercial": 1 }).limit(3)
```

### 9.2 Provocar cada patrón

| Patrón | Qué hacer | Resultado esperado con los valores por defecto |
|---|---|---|
| `cuenta_rafaga` | Una cuenta publica **5 reseñas** de productos distintos en pocos minutos, con 3 y 4 estrellas (así no se mezcla con los patrones que miran 5 o 1-2 estrellas):<br>`Resena 66 PROD-0024 4; Resena 66 PROD-0034 3; Resena 66 PROD-0022 4; Resena 66 PROD-0035 3; Resena 66 PROD-0122 4` | Aparece la cuenta 66, nivel alto (score 100: 5 reseñas en menos de un minuto, todas sin compra) |
| `grupo_coordinado` | **3 cuentas** dan **1 estrella** a los mismos **2 productos**, dentro de las mismas 6 horas:<br>`foreach ($id in 67,68,69) { Resena $id PROD-0229 1; Resena $id PROD-0339 1 }` | Un grupo negativo de 3 cuentas (67, 68, 69), nivel alto (score 90). Con 5 estrellas en lugar de 1 sale un grupo positivo |
| `sesgo_vendedor_sin_compra` | Una cuenta da **5 estrellas** a **3 productos del mismo vendedor** (aquí, TechStore Oficial):<br>`Resena 70 PROD-0304 5; Resena 70 PROD-0305 5; Resena 70 PROD-0308 5` | Aparece la cuenta 70 con signo positivo y vendedor TechStore Oficial, nivel alto (score 80). Con 1 estrella sale con signo negativo |
| `cuentas_vinculadas` | **2 cuentas** registran la **misma dirección**, escrita con distintas mayúsculas y espacios, y califican **igual** los mismos **2 productos** (cualquier calificación):<br>`Direccion 71 "Avenida Las Americas 9-50 Zona 13" "01013"`<br>`Direccion 72 "avenida las americas 9-50  ZONA 13 " "01013"`<br>`foreach ($id in 71,72) { Resena $id PROD-0038 4; Resena $id PROD-0040 4 }` | Aparecen las cuentas 71 y 72 con ciudad Guatemala, nivel alto (score 70). La clave normalizada une las dos formas de escribir la dirección |

Ninguna de estas cuentas aparece en los tríos de `GET /api/fraude/alertas`: la consulta original no ve estos casos.

### 9.3 Verificar el resultado

**En el panel.** Entra a `http://localhost:5173/admin` con `admin@tiendaya.com` / `Tiendaya123!` y abre **Fraude** (`/admin/fraude`).

1. La pestaña **Resumen** muestra 5 tarjetas (Anillos de reseñas y los 4 patrones nuevos) con su cantidad de alertas, y la tabla de cuentas en riesgo. Tus cuentas deben aparecer con nivel **Alto** y el patrón que provocaste.
2. Pulsa la tarjeta de un patrón, o su pestaña. La URL cambia a `/admin/fraude?patron=<tipo>` (por ejemplo, `?patron=cuenta_rafaga`), y se puede abrir directo.
3. En la alerta, el **motivo** explica en una frase por qué se disparó. **"Ver detalle"** muestra la evidencia (por ejemplo, "Porcentaje sin compra" o "Parejas que coinciden") y los productos con enlace.
4. **"Ajustar sensibilidad"** abre los parámetros del patrón. Cambia un valor y pulsa **"Aplicar"**; **"Restaurar valores"** vuelve a los de por defecto. El panel acepta solo enteros positivos, y en `min_pct_sin_compra` un entero entre 1 y 100. Estos ajustes no cambian el Resumen.
5. La pestaña **Anillos de reseñas (Entrega 2)** (`?patron=anillos_resenas`) sigue mostrando los tríos de la consulta original.

**Con la API** (PowerShell):

```powershell
$admin = "rol_solicitante=administrador"
(Invoke-RestMethod "http://127.0.0.1:8000/api/fraude/alertas/cuenta_rafaga?$admin").alertas |
  ForEach-Object { "$($_.cuentas.id_usuario -join ', ') | $($_.nivel) $($_.score) | $($_.motivo)" }

(Invoke-RestMethod "http://127.0.0.1:8000/api/fraude/resumen?$admin").cuentas_riesgo |
  ForEach-Object { "$($_.id_usuario) $($_.nombre) | $($_.nivel) | $($_.patrones -join ', ')" }
```

Cambia `cuenta_rafaga` por `grupo_coordinado`, `sesgo_vendedor_sin_compra` o `cuentas_vinculadas`. Para otros parámetros, agrégalos a la URL, por ejemplo `...&min_resenas=4`.

**En Neo4j Browser** (`http://localhost:7474`), para ver los datos nuevos que usan los patrones:

```cypher
MATCH (c:Cuenta)-[r:CALIFICO]->(p:Producto)-[:VENDIDO_POR]->(v:Vendedor)
WHERE c.id_usuario IN [66, 67, 68, 69, 70, 71, 72]
RETURN c.id_usuario AS cuenta, p.id_producto AS producto, v.nombre AS vendedor,
       r.calificacion AS estrellas, r.compra_verificada AS con_compra, r.fecha AS fecha
ORDER BY cuenta, fecha
```

```cypher
MATCH (c:Cuenta)-[:ENVIA_A]->(d:Direccion) WHERE c.id_usuario IN [71, 72] RETURN c, d
```

La segunda consulta muestra las dos cuentas apuntando al **mismo** nodo `Direccion`.

### 9.4 Casos negativos

Usa cuentas distintas de las del 9.2 (si no, se suman a las reseñas de arriba).

| Caso | Cómo provocarlo | Con los valores por defecto | Para ver que el umbral es lo que lo deja fuera |
|---|---|---|---|
| Ráfaga corta | Una cuenta publica solo **4** reseñas en pocos minutos:<br>`Resena 73 PROD-0028 3; Resena 73 PROD-0036 4; Resena 73 PROD-0025 3; Resena 73 PROD-0037 4` | No aparece en `cuenta_rafaga` | Con `min_resenas=4` aparece |
| Solo 2 cuentas coordinadas | 2 cuentas dan 1 estrella a otros 2 productos:<br>`foreach ($id in 74,75) { Resena $id PROD-0230 1; Resena $id PROD-0404 1 }` | No aparece en `grupo_coordinado` (pide 3 cuentas) | Con `min_cuentas=2` aparece como grupo de 2 |
| Sesgo con signos mezclados | Una cuenta da 5, 5 y 1 estrellas a 3 productos del mismo vendedor:<br>`Resena 76 PROD-0318 5; Resena 76 PROD-0324 5; Resena 76 PROD-0338 1` | No aparece en `sesgo_vendedor_sin_compra`: solo hay 2 del mismo signo | Con `min_resenas=2` aparece con signo positivo (nivel medio) |
| Misma dirección, distinta opinión | 2 cuentas registran la misma dirección y califican los mismos 2 productos con **distintas** estrellas:<br>`Direccion 77 "Calle Montufar 5-10 Zona 9" "01009"; Direccion 78 "CALLE MONTUFAR 5-10 ZONA 9" "01009"`<br>`Resena 77 PROD-0041 4; Resena 77 PROD-0042 4; Resena 78 PROD-0041 3; Resena 78 PROD-0042 3` | No aparece en `cuentas_vinculadas` | No aparece ni con `min_productos_compartidos=1`: compartir dirección no basta |
| Reseñas fuera de la ventana | Cambia la fecha de las reseñas de una cuenta del grupo, como en la sección 6 (solo para pruebas) | El grupo pierde esa cuenta, o desaparece si queda con menos de 3 | Con una `ventana_segundos` mayor vuelve a aparecer |

### 9.5 Limpiar lo creado

Hay que borrar en tres lugares, en este orden.

**1. Direcciones, por la API** (no directo en PostgreSQL), para que el backend borre también las relaciones `ENVIA_A` y el nodo `Direccion` que quede sin cuentas. Primero lista las direcciones de cada cuenta y luego borra las de la prueba:

```powershell
foreach ($id in 71,72,77,78) {
  Invoke-RestMethod "http://127.0.0.1:8000/api/usuarios/$id/direcciones" |
    ForEach-Object {
      Invoke-RestMethod -Method DELETE "http://127.0.0.1:8000/api/usuarios/$id/direcciones/$($_.id_direccion)"
    }
}
```

Este bucle borra **todas** las direcciones de esas cuentas. Úsalo así solo si son cuentas de prueba sin otras direcciones (como las 66 a 80); si no, borra solo las de la prueba por su `id_direccion`. Cada borrado responde `{"mensaje": "Dirección eliminada"}`.

**2. Reseñas en MongoDB** (mongosh, base `tiendaya_nosql`):

```js
db.resenas.countDocuments({ texto: /\[prueba ampliada/ })   // revisa cuántas son antes de borrar
db.resenas.deleteMany({ texto: /\[prueba ampliada/ })
```

**3. Relaciones `CALIFICO` y nodos `Cuenta` en Neo4j** (Neo4j Browser). Como las cuentas de la prueba no tenían otras reseñas, se puede filtrar por cuenta. Si usaste cuentas con otras reseñas, filtra también por producto, como en la sección 7.

```cypher
MATCH (c:Cuenta)-[r:CALIFICO]->(:Producto)
WHERE c.id_usuario IN [66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78]
DELETE r
```

```cypher
MATCH (c:Cuenta)
WHERE c.id_usuario IN [66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78] AND NOT (c)--()
DELETE c
```

La segunda borra solo los nodos `Cuenta` que quedaron sin relaciones (la sincronización de reseñas y direcciones los crea; el backend no los borra solo). Con la prueba completa de esta sección son 33 reseñas en Mongo, 33 relaciones `CALIFICO` y 13 nodos `Cuenta`.

Los nodos `Producto` que entraron al grafo por primera vez en la prueba quedan, con su `VENDIDO_POR`. No generan alertas sin reseñas, y la próxima reseña de ese producto los reutiliza.

Para comprobar que todo quedó como antes, `GET /api/fraude/resumen?rol_solicitante=administrador` debe devolver el mismo `por_tipo` que antes de la prueba (el 2026-10-07, con la semilla cargada: `cuenta_rafaga` 1, `grupo_coordinado` 4, `sesgo_vendedor_sin_compra` 6, `cuentas_vinculadas` 1).

**No** uses `sembrar_resenas_fraude.py` para limpiar: borra **todas** las reseñas, incluidas las de `sembrar_fraude_ampliado.py` (ver la sección 6.3 de [`deteccion-fraude-ampliada.md`](deteccion-fraude-ampliada.md)).

### 9.6 Problemas comunes de la detección ampliada

| Síntoma | Causa probable |
|---|---|
| El panel muestra "El grafo de fraude no está disponible (Neo4j no responde)" | Neo4j no está corriendo (la API responde 503). Levántalo con `docker compose up -d`. |
| `cuentas_vinculadas` no ve dos cuentas con la misma dirección | Neo4j estaba caído cuando se guardó la dirección, o la dirección difiere en algo más que mayúsculas y espacios (por ejemplo, "Zona 13" contra "Z. 13", u otro código postal). Corre `sincronizar_grafo_fraude.py` y revisa la dirección. |
| `sesgo_vendedor_sin_compra` no aparece aunque la cuenta reseñó 3 productos de una tienda | Las calificaciones no son todas del mismo signo extremo (todas 5, o todas 1-2), la cuenta sí compró alguno de esos productos (un pedido cancelado también cuenta), o el grafo no tiene el vendedor del producto (corre `sincronizar_grafo_fraude.py`). |
| Una cuenta de prueba aparece en un patrón que no esperabas | La cuenta ya tenía reseñas, o se usó en más de una prueba. Usa cuentas sin reseñas (9.1). |
| "Aplicar" está deshabilitado en "Ajustar sensibilidad" | Algún valor no es un entero positivo, o `min_pct_sin_compra` no está entre 1 y 100. |
