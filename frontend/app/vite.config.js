import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    port: 5173,
    // El repo vive en OneDrive, que no siempre emite eventos del sistema de archivos:
    // sin polling Vite sirve módulos viejos o duplica instancias (p.ej. useCarrito.js).
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
})
