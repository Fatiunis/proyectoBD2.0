# TiendaYa — frontend (Vue 3 + Vite)

Único frontend del proyecto (el sitio HTML/JS vanilla original se retiró del
repositorio tras completarse y verificarse la migración — ver `docs/STACK.md`
en la raíz del repo para el detalle técnico completo).

## Desarrollo

```
npm install
npm run dev
```

Levanta el servidor de desarrollo de Vite en `http://localhost:5173` (o el
siguiente puerto libre). Requiere el backend Flask corriendo en
`http://127.0.0.1:8000` (ver el README raíz para levantarlo).

`vite.config.js` activa `server.watch.usePolling` (cada 300 ms) porque el repo
suele vivir dentro de OneDrive, que no siempre emite eventos de cambio de
archivos: sin esto Vite podía servir módulos viejos o dos copias distintas de un
composable (por ejemplo `useCarrito`), partiendo su estado. Si aun así ves algo
raro tras muchos cambios seguidos, reinicia `npm run dev` y recarga con Ctrl+F5.

En Windows, si Vite falla con `listen EACCES` en el puerto 5173, es porque
Docker/Hyper-V reservó un rango de puertos que lo incluye (Vite solo cambia de
puerto si el 5173 está ocupado, no si está reservado). Revisa los rangos con
`netsh interface ipv4 show excludedportrange protocol=tcp` y levanta Vite en
otro puerto, por ejemplo `npm run dev -- --port 5300`. El backend tiene CORS
abierto, así que funciona igual. Detalle en el README raíz (paso 7).

Rutas: `/` sitio público (catálogo paginado con la franja de ofertas flash
encima de la grilla, buscador con autocompletado y facetas, página de ofertas flash,
carrito, checkout, login/registro y "Mi cuenta" del comprador: pedidos, perfil
y direcciones; las vistas sin URL propia se piden con `/?vista=ofertas`,
`/?vista=carrito`, etc.), `/producto/:id` página de producto
(especificaciones, reseñas, oferta límite con precio de oferta y cuenta
regresiva) y `/admin/:tab?` panel admin (catálogo, categorías, usuarios, "Mis
ventas", ofertas flash del vendedor en `/admin/ofertas`, historial, fraude,
sincronización).

El buscador (`ResultadosBusqueda.vue`) usa `GET /api/busqueda` (Elasticsearch)
y, si responde 503, repite la búsqueda contra `GET /api/productos?q=`
(MongoDB) mostrando un aviso; cualquier otro error (por ejemplo, `400
BUSQUEDA_NO_VALIDA`) se muestra como error, sin respaldo. El checkout manda una clave de idempotencia por
intento de compra; con `PERMITIR_FALLAS_SIMULADAS=1` en el `.env` del backend,
muestra además un selector para simular fallas (ver
`docs/estrategia-consistencia-checkout.md`).

Las ofertas flash (botón "Ofertas", franja del catálogo, página de ofertas,
etiqueta de descuento en las tarjetas y pestaña del vendedor) se explican en
la sección [Ofertas flash](#ofertas-flash), más abajo. `GestionVentas.vue`
("Mis ventas", también para el administrador) manda `rol_solicitante` e
`id_usuario`, que `GET /api/vendedores/<id>/ventas` ahora exige.
`ModalAdmin.vue` se cierra con Escape.

La pestaña Historial del admin (`components/admin/HistorialProducto.vue`)
carga el selector de productos recorriendo todas las páginas de `GET
/api/productos` (`por_pagina=100`) y pagina el feed de `GET /api/historial`
de a 20 eventos con `Paginacion.vue`: muestra el total ("N eventos") y vuelve
a la página 1 al pulsar "Filtrar" o "Limpiar filtros".

## Ofertas flash

Desde el 2026-10-07.

**Una sola consulta compartida.** El botón "Ofertas" de `NavPublica.vue` (con
el número de ofertas activas), la franja `FranjaOfertasFlash.vue`, la página
`OfertasFlash.vue` (`/?vista=ofertas`) y las tarjetas del catálogo comparten
una sola consulta a `GET /api/ofertas` a través de
`composables/useOfertasFlash.js`: cada componente montado pide un `limite`, la
consulta se hace con el mayor y se repite cada 20 s, salvo que la pestaña del
navegador esté oculta. La barra, la franja y la página piden `limite=100`:
como la barra está en todas las vistas públicas, las tarjetas de cualquier
vista (también los resultados de búsqueda) conocen todas las ofertas
(antes la barra pedía `limite=1` y en la búsqueda solo se marcaba una,
H-018). El contador del botón cuenta solo las ofertas disponibles (con cupo y
sin terminar), igual que el "N activas" de la franja, no el `total` del
backend. El
composable exporta además `ofertaDisponible(oferta)` (tiene cupo y no
terminó) y `ofertaActivaDe(producto_id)`, que busca en el estado ya cargado
sin hacer otra petición.

**Franja del catálogo.** `FranjaOfertasFlash.vue` vive dentro de
`CatalogoProductos.vue`, en la columna derecha encima de la grilla, así que el
menú de categorías de la izquierda sigue siempre a la vista. Es compacta y
oscura para que destaque sobre el catálogo blanco: degradado
`from-accent-900 via-accent-800 to-accent-900` (tokens `--color-accent-800` y
`--color-accent-900` del `@theme` de `src/style.css`), texto blanco, acentos
ámbar (rayo, chip "N activas", precio de oferta, chip -X%, "Ver todas →",
foco `outline-amber-300`) y tarjetas `bg-white/10`. Muestra hasta 12 ofertas
con desplazamiento lateral; se contrae a una línea y ese estado se guarda en
`sessionStorage` (`tiendaya_franja_ofertas_contraida`); si no hay ofertas
vigentes no se muestra. "Ver todas" hace que `CatalogoProductos` emita
`ver-ofertas`, y `VistaPublica.vue` abre la página de ofertas.

**Tarjetas y detalle.** `TarjetaProducto.vue` usa `ofertaActivaDe` para
mostrar la etiqueta "⚡ -X%" sobre la imagen y el precio de oferta junto al
normal tachado. En `/producto/:id`, `VistaDetalleProducto.vue` muestra el
bloque de precio de oferta con cuenta regresiva (escucha el evento
`cambio-oferta` de `OfertaLimitada.vue`, sin consulta aparte). Ambos usan el
`descuento_pct` que devuelve `GET /api/ofertas/<producto_id>` y muestran "Sin
límite de tiempo" cuando `segundos_restantes` viene `null`.

**Porcentaje y tiempo.** `utils/descuento.js` (`porcentajeDescuento`) usa el
`descuento_pct` del servidor si viene; si no, lo calcula con el mismo
redondeo del backend (half-up), en centavos enteros, porque con floats
`(1 - 1749/2200) * 100` da 20,4999… y quedaría en 20 en vez de 21. El
resultado queda entre 0 y 99 mientras el precio de oferta sea mayor que 0,
igual que en el backend. Las cuentas regresivas usan `formatoMinSeg` y
`formatoCuentaRegresiva` de `utils/tiempo.js`.

**Pestaña del vendedor.** `components/admin/GestionOfertas.vue` (con
`FormularioOferta.vue` y `TarjetaOferta.vue`), en `/admin/ofertas` y solo
para vendedor, usa `GET /api/vendedores/<id>/ofertas` y se actualiza cada
15 s. Crear y finalizar usan `POST /api/ofertas` y `DELETE
/api/ofertas/<producto_id>`.

### Filtros de las ofertas vs. filtros del catálogo

Son dos mecanismos distintos y no están conectados entre sí.

**Filtros de la página de ofertas** (`OfertasFlash.vue`, `/?vista=ofertas`):
se aplican 100 % en el navegador. La página hace una sola petición,
`GET /api/ofertas?limite=100` (la misma de `useOfertasFlash`), y después
filtra y ordena en memoria. El backend no tiene parámetros de filtro: `GET
/api/ofertas` solo acepta `limite`.
- **Categoría**: los chips se arman con las mismas ofertas
  (`categoria.id_categoria` y `categoria.nombre`, que el backend toma del
  documento del producto en MongoDB), cada uno con su conteo. Solo aparecen
  si hay ofertas de dos o más categorías. Si después de una recarga la
  categoría elegida ya no tiene ofertas, vuelve a "Todas".
- **Orden**: "Terminan pronto" (por el instante de fin, calculado a partir de
  `segundos_restantes`) o "Mayor descuento" (por el `descuento_pct` del
  servidor, con `porcentajeDescuento` de respaldo). Las agotadas o
  terminadas van siempre al final.
- El filtro y el orden elegidos no se guardan en la URL ni en
  `sessionStorage`: se pierden al salir de la vista.

**Filtros del sidebar del catálogo** (`CatalogoProductos.vue` +
`FiltrosCatalogo.vue`): se aplican en el servidor. Al elegir una categoría se
pide `GET /api/categorias/<id>/filtros` (el esquema de atributos de esa
categoría en MongoDB) y luego `GET
/api/productos?categoria_id=…&atributo_<clave>=…&atributo_<clave>_min=…&atributo_<clave>_max=…&pagina=…&por_pagina=24`,
que filtra y pagina en MongoDB. Hay filtros por atributo (de selección y de
rango); las ofertas no los tienen.

**Cómo se relacionan:**
- La franja de ofertas del catálogo **no** se filtra por la categoría ni por
  los atributos del sidebar: siempre muestra todas las ofertas vigentes.
- La etiqueta "⚡ -X%" de `TarjetaProducto.vue` sí aparece en los productos
  que deja pasar el filtro del sidebar, porque se busca por `producto_id` en
  el estado compartido de `useOfertasFlash`.
- Los filtros de la página de ofertas tampoco afectan al catálogo.
- Mejora posible (no implementada): que la franja respete la categoría
  elegida en el sidebar, filtrando en el navegador por
  `categoria.id_categoria`.

## Panel de fraude

Desde el 2026-10-07 (detección de fraude ampliada). La explicación de los
patrones está en `docs/deteccion-fraude-ampliada.md` (raíz del repo).

`/admin/fraude` (solo administrador) es `GestionFraude.vue`, ahora con
pestañas. La pestaña activa va en la URL como `?patron=<tipo>`, así que se
puede enlazar directo y sobrevive a recargar; sin `?patron=` (o con un valor
desconocido) se abre el Resumen. Las pestañas se recorren con las flechas,
Inicio y Fin (`role="tablist"`), y cada una muestra su número de alertas.

| Pestaña | `?patron=` | Componente | API |
|---|---|---|---|
| Resumen | (ninguno) | `ResumenFraude.vue`: alertas por patrón (cada tarjeta abre su pestaña) y tabla de cuentas de mayor riesgo (columnas Cuenta, Nivel y Aparece en; sin puntaje numérico) | `GET /api/fraude/resumen` |
| Anillos de reseñas (Entrega 2) | `anillos_resenas` | `AnillosResenas.vue`: la consulta de anillos de siempre (tríos de cuentas, productos compartidos, detalle expandible) | `GET /api/fraude/alertas` |
| Cuenta en ráfaga, Grupo coordinado, Cuenta sesgada hacia un vendedor, Cuentas vinculadas | `cuenta_rafaga`, `grupo_coordinado`, `sesgo_vendedor_sin_compra`, `cuentas_vinculadas` | `AlertasPatron.vue` (lista y "Ajustar sensibilidad") + `AlertaFraude.vue` (una alerta: nivel, motivo, cuentas, productos y evidencia; el puntaje numérico no se muestra, solo el nivel que sale de él) | `GET /api/fraude/alertas/<tipo>` |

- Los nombres de las 4 pestañas de patrones y sus umbrales por defecto vienen
  de `GET /api/fraude/patrones`; el frontend no los repite.
- "Ajustar sensibilidad" (`AlertasPatron.vue`) permite cambiar los umbrales
  del patrón y vuelve a pedir las alertas con esos parámetros. Valida antes de
  enviar: enteros positivos y, para los porcentajes (`min_pct_sin_compra`),
  entre 1 y 100 (H-024 en `docs/hallazgos.md`).
- `src/utils/fraude.js` reúne lo que comparten los componentes: colores y
  etiquetas de nivel (`alto`, `medio`, `bajo`), la frase corta de cada patrón,
  las etiquetas de los umbrales y de la evidencia, `duracionLegible` y
  `mensajeErrorFraude` (un `503 GRAFO_NO_DISPONIBLE` o la falta de conexión
  se traducen a un mensaje para el administrador; el resto de los errores
  muestran el `error` del backend). También exporta `ANILLOS`
  (`"anillos_resenas"`), el valor de `?patron=` de la pestaña de la Entrega 2.
- El botón "Actualizar" vuelve a pedir el resumen, los anillos y la pestaña
  abierta.

## Build de producción

```
npm run build
```

Genera el build en `frontend/app/dist/` (es decir, `dist/` dentro de esta carpeta).

## Stack

- Vue 3 + Vite + Vue Router (`/`, `/producto/:id` y `/admin/:tab?`)
- Tailwind CSS v4 instalado como dependencia de build (`@tailwindcss/vite`),
  tema configurado en `src/style.css` (`@theme`) con el color `accent`
  (`#75823a`) y la fuente Inter.
- Sin Pinia — estado compartido con composables reactivos simples
  (`src/composables/`: `useSesion`, `useToast`, `useCategorias`, `useCarrito`,
  que guarda el carrito en el backend, sobre Redis, y `useOfertasFlash`).
- Componentes compartidos entre el sitio público y el admin en
  `src/components/comunes/` (por ahora, `Paginacion.vue`, que usan el
  catálogo público, el del admin, los resultados de búsqueda y el historial).
  `GET /api/productos` devuelve `{items, total, pagina, por_pagina,
  total_paginas}`, no una lista; `GET /api/historial` devuelve `{eventos,
  total, pagina, por_pagina, total_paginas}`.
- `apiFetch` (`src/services/api.js`) no lanza si el servidor no responde:
  devuelve `{ok: false, status: 0, data: {codigo: "SIN_CONEXION"}}`.
