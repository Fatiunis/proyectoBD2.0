<script setup>
import { RouterLink } from "vue-router";
import { useSesion } from "../../composables/useSesion";

defineProps({
  tabActual: { type: String, required: true },
  esVendedor: { type: Boolean, required: true },
});
const emit = defineEmits(["cambiar-tab"]);

const { sesion, limpiarSesion } = useSesion();

function claseBoton(tab, tabActual) {
  return [
    "w-full text-left px-3 py-2.5 rounded-lg text-sm font-semibold transition flex items-center gap-2.5",
    tab === tabActual ? "bg-accent text-white" : "text-neutral-300 hover:bg-neutral-900 hover:text-white",
  ];
}
</script>

<template>
  <aside class="fixed inset-y-0 left-0 w-60 bg-neutral-950 text-neutral-300 flex flex-col">
    <div class="flex items-center gap-2.5 px-5 py-5 border-b border-neutral-800">
      <div class="w-8 h-8 rounded-lg bg-accent text-white flex items-center justify-center font-extrabold text-sm">TY</div>
      <div>
        <h1 class="text-sm font-extrabold text-white leading-none">TiendaYa</h1>
        <p class="text-[10px] text-neutral-500 uppercase tracking-wider font-medium mt-0.5">Panel admin</p>
      </div>
    </div>

    <nav class="flex-1 px-3 py-4 space-y-1">
      <button @click="emit('cambiar-tab', 'catalogo')" :class="claseBoton('catalogo', tabActual)">
        <span class="w-1.5 h-1.5 rounded-full bg-current opacity-60"></span> {{ esVendedor ? "Mi catálogo" : "Catálogo" }}
      </button>
      <button v-if="esVendedor" @click="emit('cambiar-tab', 'ventas')" :class="claseBoton('ventas', tabActual)">
        <span class="w-1.5 h-1.5 rounded-full bg-current opacity-60"></span> Mis ventas
      </button>
      <button v-if="!esVendedor" @click="emit('cambiar-tab', 'categorias')" :class="claseBoton('categorias', tabActual)">
        <span class="w-1.5 h-1.5 rounded-full bg-current opacity-60"></span> Categorías
      </button>
      <button v-if="!esVendedor" @click="emit('cambiar-tab', 'usuarios')" :class="claseBoton('usuarios', tabActual)">
        <span class="w-1.5 h-1.5 rounded-full bg-current opacity-60"></span> Usuarios
      </button>
      <button @click="emit('cambiar-tab', 'historial')" :class="claseBoton('historial', tabActual)">
        <span class="w-1.5 h-1.5 rounded-full bg-current opacity-60"></span> Historial
      </button>
    </nav>

    <div class="px-4 py-4 border-t border-neutral-800">
      <div class="text-xs font-semibold text-neutral-200 mb-3 truncate">{{ sesion.nombre }} · {{ sesion.rol }}</div>
      <div class="flex gap-2">
        <RouterLink to="/" class="flex-1 text-center px-2 py-1.5 border border-neutral-700 hover:border-neutral-500 text-neutral-300 hover:text-white rounded-full text-xs font-semibold transition">Sitio público</RouterLink>
        <button @click="limpiarSesion" class="flex-1 px-2 py-1.5 bg-red-600/90 hover:bg-red-600 text-white rounded-full text-xs font-semibold transition">Salir</button>
      </div>
    </div>
  </aside>
</template>
