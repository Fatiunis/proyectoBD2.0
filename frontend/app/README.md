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

Rutas: `/` sitio público (catálogo, carrito, checkout, login/registro), `/admin`
panel admin (catálogo, categorías, usuarios, ventas, historial).

## Build de producción

```
npm run build
```

Genera el build en `app/dist/`.

## Stack

- Vue 3 + Vite + Vue Router (`/` y `/admin`)
- Tailwind CSS v4 instalado como dependencia de build (`@tailwindcss/vite`),
  tema configurado en `src/style.css` (`@theme`) con el color `accent`
  (`#75823a`) y la fuente Inter.
- Sin Pinia — estado compartido con composables reactivos simples
  (`src/composables/`: `useSesion`, `useToast`, `useCategorias`, `useCarrito`).
