# TiendaYa — frontend (Vue 3 + Vite)

Scaffold inicial de la migración del frontend descrita en `docs/STACK.md`. Todavía
no tiene lógica de negocio migrada (catálogo, carrito, login, admin) — eso se hace
en fases posteriores.

## Desarrollo

```
npm install
npm run dev
```

Levanta el servidor de desarrollo de Vite en `http://localhost:5173`.

## Build de producción

```
npm run build
```

Genera el build en `app/dist/`.

## Stack

- Vue 3 + Vite
- Vue Router (rutas `/` y `/admin` con componentes placeholder en `src/views/`)
- Tailwind CSS instalado como dependencia de build (`@tailwindcss/vite`), tema
  configurado en `src/style.css` (`@theme`) con el color `accent` (#75823a) y
  la fuente Inter, igual que el sitio vanilla.

## Convivencia con el sitio vanilla

Este proyecto vive en `frontend/app/` para no chocar con los archivos vanilla que
siguen siendo el sitio en producción: `frontend/index.html`, `frontend/admin.html`
y `frontend/js/`. Ver la sección "Frontend" del README raíz o `docs/STACK.md` para
más detalle sobre cuál está activo.
