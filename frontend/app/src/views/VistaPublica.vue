<script setup>
import { ref } from "vue";
import NavPublica from "../components/publico/NavPublica.vue";
import CatalogoProductos from "../components/publico/CatalogoProductos.vue";
import DetalleProducto from "../components/publico/DetalleProducto.vue";
import Carrito from "../components/publico/Carrito.vue";
import FormularioLogin from "../components/publico/FormularioLogin.vue";
import FormularioRegistro from "../components/publico/FormularioRegistro.vue";

const vistaActual = ref("catalogo");
const busqueda = ref("");
const productoDetalleId = ref(null);

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
      <CatalogoProductos v-else :busqueda="busqueda" @ver-detalle="productoDetalleId = $event" />
    </main>

    <DetalleProducto :producto-id="productoDetalleId" @cerrar="productoDetalleId = null" />

    <footer class="border-t border-neutral-200 bg-white text-neutral-400 text-xs py-6 text-center tracking-wide">
      TiendaYa · Portal E-Commerce con arquitectura políglota (PostgreSQL + MongoDB)
    </footer>
  </div>
</template>
