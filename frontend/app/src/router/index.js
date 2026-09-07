import { createRouter, createWebHistory } from 'vue-router'
import VistaPublica from '../views/VistaPublica.vue'
import VistaAdmin from '../views/VistaAdmin.vue'
import VistaDetalleProducto from '../views/VistaDetalleProducto.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'catalogo', component: VistaPublica },
    { path: '/producto/:id', name: 'producto', component: VistaDetalleProducto, props: true },
    { path: '/admin', name: 'admin', component: VistaAdmin },
  ],
})

export default router
