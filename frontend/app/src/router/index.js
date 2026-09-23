import { createRouter, createWebHistory } from 'vue-router'
import VistaPublica from '../views/VistaPublica.vue'
import VistaAdmin from '../views/VistaAdmin.vue'
import VistaDetalleProducto from '../views/VistaDetalleProducto.vue'

// El destino del hash (p.ej. #escribir-resena) solo existe cuando la vista terminó
// de cargar su contenido asíncrono (el producto), así que se espera a que aparezca.
function esperarElemento(id, limiteMs = 5000) {
  return new Promise((resolve) => {
    const inicio = Date.now()
    const intentar = () => {
      const el = document.getElementById(id)
      if (el || Date.now() - inicio >= limiteMs) resolve(el)
      else setTimeout(intentar, 50)
    }
    intentar()
  })
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'catalogo', component: VistaPublica },
    { path: '/producto/:id', name: 'producto', component: VistaDetalleProducto, props: true },
    { path: '/admin/:tab?', name: 'admin', component: VistaAdmin, props: true },
  ],
  async scrollBehavior(to, from, savedPosition) {
    if (to.hash) {
      const el = await esperarElemento(decodeURIComponent(to.hash.slice(1)))
      if (el) return { el, behavior: 'smooth' }
    }
    return savedPosition || { top: 0 }
  },
})

export default router
