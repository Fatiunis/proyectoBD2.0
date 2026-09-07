<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import NavPublica from "../components/publico/NavPublica.vue";
import CatalogoProductos from "../components/publico/CatalogoProductos.vue";
import Carrito from "../components/publico/Carrito.vue";
import FormularioLogin from "../components/publico/FormularioLogin.vue";
import FormularioRegistro from "../components/publico/FormularioRegistro.vue";

const route = useRoute();
const router = useRouter();

// Otras vistas (ej. VistaDetalleProducto) navegan de vuelta a "/" con estos
// query params para pedir un tab distinto de "catalogo" o disparar una
// búsqueda, ya que carrito/login/registro no tienen su propia URL.
const vistaActual = ref(typeof route.query.vista === "string" ? route.query.vista : "catalogo");
const busqueda = ref(typeof route.query.q === "string" ? route.query.q : "");
if (Object.keys(route.query).length > 0) router.replace({ path: "/" });

function cambiarVista(vista) {
  vistaActual.value = vista;
}

function onBuscar(texto) {
  busqueda.value = texto;
  vistaActual.value = "catalogo";
}
</script>

<template>
  <div class="bg-white text-neutral-950 min-h-screen flex flex-col">
    <NavPublica :vista-actual="vistaActual" @cambiar-vista="cambiarVista" @buscar="onBuscar" />

    <main class="max-w-[1600px] mx-auto px-6 lg:px-10 py-6 flex-grow w-full">
      <FormularioLogin v-if="vistaActual === 'login'" @exito="cambiarVista('catalogo')" @ir-a-registro="cambiarVista('registro')" />
      <FormularioRegistro v-else-if="vistaActual === 'registro'" @exito="cambiarVista('login')" />
      <Carrito v-else-if="vistaActual === 'carrito'" @completado="cambiarVista('catalogo')" />
      <CatalogoProductos v-else :busqueda="busqueda" />
    </main>

    <footer class="border-t border-neutral-200 bg-white text-neutral-400 text-xs py-6 text-center tracking-wide">
      TiendaYa · Portal E-Commerce con arquitectura políglota (PostgreSQL + MongoDB)
    </footer>
  </div>
</template>
