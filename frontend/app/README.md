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

Rutas: `/` sitio público (catálogo paginado, buscador con autocompletado y
facetas, carrito, checkout, login/registro y "Mi cuenta" del comprador:
pedidos, perfil y direcciones), `/producto/:id` página de producto
(especificaciones, reseñas, oferta límite) y `/admin/:tab?` panel admin
(catálogo, categorías, usuarios, ventas, historial, fraude, sincronización).

El buscador (`ResultadosBusqueda.vue`) usa `GET /api/busqueda` (Elasticsearch)
y, si responde 503, repite la búsqueda contra `GET /api/productos?q=`
(MongoDB) mostrando un aviso; cualquier otro error (por ejemplo, `400
BUSQUEDA_NO_VALIDA`) se muestra como error, sin respaldo. El checkout manda una clave de idempotencia por
intento de compra; con `PERMITIR_FALLAS_SIMULADAS=1` en el `.env` del backend,
muestra además un selector para simular fallas (ver
`docs/estrategia-consistencia-checkout.md`).

La pestaña Historial del admin (`components/admin/HistorialProducto.vue`)
carga el selector de productos recorriendo todas las páginas de `GET
/api/productos` (`por_pagina=100`) y pagina el feed de `GET /api/historial`
de a 20 eventos con `Paginacion.vue`: muestra el total ("N eventos") y vuelve
a la página 1 al pulsar "Filtrar" o "Limpiar filtros".

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
  (`src/composables/`: `useSesion`, `useToast`, `useCategorias`, `useCarrito`;
  este último guarda el carrito en el backend, sobre Redis).
- Componentes compartidos entre el sitio público y el admin en
  `src/components/comunes/` (por ahora, `Paginacion.vue`, que usan el
  catálogo público, el del admin, los resultados de búsqueda y el historial).
  `GET /api/productos` devuelve `{items, total, pagina, por_pagina,
  total_paginas}`, no una lista; `GET /api/historial` devuelve `{eventos,
  total, pagina, por_pagina, total_paginas}`.
- `apiFetch` (`src/services/api.js`) no lanza si el servidor no responde:
  devuelve `{ok: false, status: 0, data: {codigo: "SIN_CONEXION"}}`.
