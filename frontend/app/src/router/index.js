import { createRouter, createWebHistory } from 'vue-router'
import VistaPublica from '../views/VistaPublica.vue'
import VistaAdmin from '../views/VistaAdmin.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'catalogo', component: VistaPublica },
    { path: '/admin', name: 'admin', component: VistaAdmin },
  ],
})

export default router
