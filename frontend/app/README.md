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

Rutas: `/` sitio público (catálogo, carrito, checkout, login/registro),
`/producto/:id` página de producto (especificaciones, reseñas, oferta límite) y
`/admin/:tab?` panel admin (catálogo, categorías, usuarios, ventas, historial,
fraude).

## Build de producción

```
npm run build
```

Genera el build en `app/dist/`.

## Stack

- Vue 3 + Vite + Vue Router (`/`, `/producto/:id` y `/admin/:tab?`)
- Tailwind CSS v4 instalado como dependencia de build (`@tailwindcss/vite`),
  tema configurado en `src/style.css` (`@theme`) con el color `accent`
  (`#75823a`) y la fuente Inter.
- Sin Pinia — estado compartido con composables reactivos simples
  (`src/composables/`: `useSesion`, `useToast`, `useCategorias`, `useCarrito`;
  este último guarda el carrito en el backend, sobre Redis).
