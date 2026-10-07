<script setup>
import { ref, computed, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useCarrito } from "../../composables/useCarrito";
import { useOfertasFlash, ofertaDisponible } from "../../composables/useOfertasFlash";

const props = defineProps({
  vistaActual: { type: String, required: true },
  // Búsqueda vigente en la vista: si cambia desde afuera (por ejemplo, al
  // elegir "¿quisiste decir...?"), el texto de la barra la acompaña.
  busquedaActual: { type: String, default: "" },
});

const emit = defineEmits(["cambiar-vista", "buscar"]);

const router = useRouter();
const { sesion, limpiarSesion } = useSesion();
const { cantidadTotal } = useCarrito();
// Se pide la lista completa (no solo el total): con la nav montada en todas las
// vistas públicas, así ofertaActivaDe() de las tarjetas conoce todas las ofertas
// (H-018), y el contador cuenta solo las disponibles, igual que la franja.
const { ofertas } = useOfertasFlash({ limite: 100 });
const totalOfertas = computed(() => ofertas.value.filter((o) => ofertaDisponible(o)).length);

// Autocompletado (Entrega 3): mientras se escribe se piden sugerencias a
// GET /api/busqueda/autocompletar (Elasticsearch, edge n-grams + fuzziness).
// Enter sin una sugerencia elegida lanza la búsqueda completa (con facetas).
const busqueda = ref(props.busquedaActual);
watch(() => props.busquedaActual, (nueva) => (busqueda.value = nueva));
const sugerencias = ref([]);
const abierto = ref(false);
const resaltada = ref(-1);
let debounceSugerencias = null;
let consultaVigente = 0;

function onBuscarInput() {
  clearTimeout(debounceSugerencias);
  const texto = busqueda.value.trim();
  if (!texto) {
    sugerencias.value = [];
    abierto.value = false;
    emit("buscar", "");
    return;
  }
  debounceSugerencias = setTimeout(() => pedirSugerencias(texto), 150);
}

async function pedirSugerencias(texto) {
  if (texto.length < 2) {
    sugerencias.value = [];
    return;
  }
  const consulta = ++consultaVigente;
  const { ok, data } = await apiFetch(`/busqueda/autocompletar?q=${encodeURIComponent(texto)}`);
  if (consulta !== consultaVigente) return; // llegó tarde: ya se escribió otra cosa
  sugerencias.value = ok && Array.isArray(data) ? data : [];
  resaltada.value = -1;
  abierto.value = true;
}

function buscarTodo() {
  clearTimeout(debounceSugerencias);
  consultaVigente++;
  abierto.value = false;
  emit("buscar", busqueda.value.trim());
}

function irAProducto(s) {
  abierto.value = false;
  router.push(`/producto/${s._id}`);
}

function onTecla(e) {
  if (e.key === "ArrowDown" && sugerencias.value.length) {
    e.preventDefault();
    abierto.value = true;
    resaltada.value = (resaltada.value + 1) % sugerencias.value.length;
  } else if (e.key === "ArrowUp" && sugerencias.value.length) {
    e.preventDefault();
    resaltada.value = resaltada.value <= 0 ? sugerencias.value.length - 1 : resaltada.value - 1;
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (abierto.value && resaltada.value >= 0) irAProducto(sugerencias.value[resaltada.value]);
    else buscarTodo();
  } else if (e.key === "Escape") {
    abierto.value = false;
  }
}

function cerrarConRetraso() {
  // Deja que un clic sobre una sugerencia llegue antes de cerrar la lista.
  setTimeout(() => (abierto.value = false), 150);
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
        @keydown="onTecla"
        @focus="sugerencias.length && (abierto = true)"
        @blur="cerrarConRetraso"
        placeholder="Buscar productos..."
        role="combobox"
        aria-autocomplete="list"
        :aria-expanded="abierto"
        class="w-full bg-neutral-900 hover:bg-neutral-800 focus:bg-neutral-800 border border-neutral-800 focus:border-neutral-600 rounded-full pl-10 pr-4 py-2 text-sm text-white placeholder:text-neutral-500 outline-none transition"
      >

      <div
        v-if="abierto && busqueda.trim().length >= 2"
        class="absolute left-0 right-0 top-full mt-2 bg-white rounded-2xl shadow-xl border border-neutral-200 overflow-hidden z-50 w-[26rem] max-w-[90vw]"
        role="listbox"
      >
        <button
          v-for="(s, i) in sugerencias"
          :key="s._id"
          type="button"
          role="option"
          :aria-selected="i === resaltada"
          @mousedown.prevent="irAProducto(s)"
          @mouseenter="resaltada = i"
          :class="['w-full text-left px-4 py-2.5 flex items-center gap-3 transition', i === resaltada ? 'bg-neutral-100' : 'hover:bg-neutral-50']"
        >
          <img v-if="s.imagen_url" :src="s.imagen_url" alt="" class="w-9 h-9 rounded-lg object-cover shrink-0 bg-neutral-100">
          <div v-else class="w-9 h-9 rounded-lg bg-neutral-100 shrink-0"></div>
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium text-neutral-950 truncate">{{ s.nombre }}</p>
            <p class="text-[11px] text-neutral-400">{{ s.categoria }}</p>
          </div>
          <span class="text-sm font-semibold text-accent-700 shrink-0">Q{{ Number(s.precio_base).toFixed(2) }}</span>
        </button>
        <p v-if="!sugerencias.length" class="px-4 py-3 text-sm text-neutral-500">Sin sugerencias. Presiona Enter para buscar.</p>
        <button
          type="button"
          @mousedown.prevent="buscarTodo"
          class="w-full text-left px-4 py-2.5 text-xs font-semibold text-accent border-t border-neutral-100 hover:bg-neutral-50"
        >Ver todos los resultados de "{{ busqueda.trim() }}" →</button>
      </div>
    </div>

    <div class="flex items-center gap-1 shrink-0">
      <button @click="emit('cambiar-vista', 'catalogo')" class="px-4 py-2 text-neutral-300 hover:text-white text-sm font-medium tracking-tight transition">Catálogo</button>

      <button
        @click="emit('cambiar-vista', 'ofertas')"
        :aria-current="vistaActual === 'ofertas' ? 'page' : undefined"
        :aria-label="totalOfertas > 0 ? `Ofertas flash, ${totalOfertas} activas` : 'Ofertas flash'"
        :class="['relative flex items-center gap-1.5 px-4 py-2 text-sm font-semibold tracking-tight transition', vistaActual === 'ofertas' ? 'text-white' : 'text-neutral-300 hover:text-white']"
      >
        <svg viewBox="0 0 24 24" fill="currentColor" class="w-4 h-4 text-amber-400" aria-hidden="true"><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12L13 2Z"/></svg>
        Ofertas
        <span v-if="totalOfertas > 0" class="absolute -top-0.5 right-0 min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-amber-400 text-amber-950 text-[10px] font-bold flex items-center justify-center" aria-hidden="true">{{ totalOfertas }}</span>
      </button>

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
        <button
          v-if="sesion.rol === 'comprador'"
          @click="emit('cambiar-vista', 'perfil')"
          class="px-4 py-1.5 border border-neutral-700 hover:border-neutral-500 text-white rounded-full text-xs font-medium transition"
        >Mi cuenta</button>
        <button @click="cerrarSesion" title="Cerrar sesión" class="w-8 h-8 flex items-center justify-center text-neutral-500 hover:text-white transition">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>
        </button>
      </div>
    </div>
  </nav>
</template>
