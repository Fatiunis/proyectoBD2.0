<script setup>
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { useSesion } from "../../composables/useSesion";
import { useCarrito } from "../../composables/useCarrito";

defineProps({
  vistaActual: { type: String, required: true },
});

const emit = defineEmits(["cambiar-vista", "buscar"]);

const { sesion, limpiarSesion } = useSesion();
const { cantidadTotal } = useCarrito();

const busqueda = ref("");
let debounceBusqueda = null;

function onBuscarInput() {
  clearTimeout(debounceBusqueda);
  debounceBusqueda = setTimeout(() => emit("buscar", busqueda.value.trim()), 350);
}

function cerrarSesion() {
  limpiarSesion();
  emit("cambiar-vista", "catalogo");
}
</script>

<template>
  <nav class="sticky top-0 z-40 bg-neutral-950 px-8 py-4 flex justify-between items-center gap-6">
    <div class="flex items-baseline gap-2 shrink-0">
      <h1 class="text-xl font-extrabold tracking-tight leading-none text-white">TiendaYa<span class="text-accent">.</span></h1>
      <p class="hidden sm:block text-[10px] text-neutral-500 uppercase tracking-[0.15em] font-medium">Bases de Datos 2</p>
    </div>

    <div class="hidden md:block relative flex-1 max-w-xs">
      <svg class="w-4 h-4 text-neutral-500 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
      <input
        type="search"
        v-model="busqueda"
        @input="onBuscarInput"
        placeholder="Buscar productos..."
        class="w-full bg-neutral-900 hover:bg-neutral-800 focus:bg-neutral-800 border border-neutral-800 focus:border-neutral-600 rounded-full pl-10 pr-4 py-2 text-sm text-white placeholder:text-neutral-500 outline-none transition"
      >
    </div>

    <div class="flex items-center gap-1 shrink-0">
      <button @click="emit('cambiar-vista', 'catalogo')" class="px-4 py-2 text-neutral-300 hover:text-white text-sm font-medium tracking-tight transition">Catálogo</button>

      <button @click="emit('cambiar-vista', 'carrito')" class="relative px-4 py-2 text-neutral-300 hover:text-white text-sm font-medium tracking-tight transition">
        Carrito
        <span v-if="cantidadTotal > 0" class="absolute -top-0.5 right-0 min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-accent text-white text-[10px] font-bold flex items-center justify-center">{{ cantidadTotal }}</span>
      </button>

      <div v-if="!sesion" class="flex items-center gap-1 ml-3 pl-4 border-l border-neutral-800">
        <button @click="emit('cambiar-vista', 'login')" class="px-4 py-2 text-neutral-300 hover:text-white text-sm font-medium tracking-tight transition">Iniciar sesión</button>
        <button @click="emit('cambiar-vista', 'registro')" class="px-5 py-2 bg-white hover:bg-neutral-200 text-neutral-950 rounded-full text-sm font-semibold tracking-tight transition">Registrarse</button>
      </div>

      <div v-else class="flex items-center gap-3 ml-3 pl-4 border-l border-neutral-800">
        <div class="w-8 h-8 rounded-full bg-white text-neutral-950 flex items-center justify-center text-xs font-bold shrink-0">{{ sesion.nombre.trim().charAt(0).toUpperCase() }}</div>
        <div class="leading-tight mr-1">
          <div class="text-sm font-medium text-white">{{ sesion.nombre }}</div>
          <div class="text-[10px] text-neutral-500 uppercase tracking-wide font-semibold">{{ sesion.rol }}</div>
        </div>
        <RouterLink
          v-if="['administrador', 'vendedor'].includes(sesion.rol)"
          to="/admin"
          class="px-4 py-1.5 border border-neutral-700 hover:border-neutral-500 text-white rounded-full text-xs font-medium transition"
        >Panel Admin →</RouterLink>
        <button @click="cerrarSesion" title="Cerrar sesión" class="w-8 h-8 flex items-center justify-center text-neutral-500 hover:text-white transition">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>
        </button>
      </div>
    </div>
  </nav>
</template>
