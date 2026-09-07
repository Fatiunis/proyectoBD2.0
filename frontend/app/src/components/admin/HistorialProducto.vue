<script setup>
import { ref, computed, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";

const { sesion } = useSesion();
const { toast } = useToast();

const esVendedor = computed(() => sesion.value?.rol === "vendedor");

const textoBusqueda = ref("");
const fechaDesde = ref("");
const fechaHasta = ref("");
const mapaProductos = ref({});
const eventos = ref([]);
const cargando = ref(true);
const filaExpandida = ref(null);

async function cargarProductos() {
  const path = esVendedor.value ? `/productos?vendedor_id=${sesion.value.id_usuario}` : "/productos";
  const { data } = await apiFetch(path);
  const ordenados = [...(data || [])].sort((a, b) => a.nombre.localeCompare(b.nombre));
  const mapa = {};
  ordenados.forEach((p) => {
    mapa[`${p.nombre} — ${p.sku}`] = p._id;
  });
  mapaProductos.value = mapa;
}

const idResuelto = computed(() => mapaProductos.value[textoBusqueda.value] || null);

const ETIQUETAS_TIPO_EVENTO = {
  CREACION_PRODUCTO: "Creación de producto",
  ACTUALIZACION_PANEL_ADMIN: "Actualización desde panel admin",
};

function etiquetaTipoEvento(tipo) {
  return (
    ETIQUETAS_TIPO_EVENTO[tipo] ||
    tipo
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/(^|\s)\S/g, (letra) => letra.toUpperCase())
  );
}

function formatearFecha(iso) {
  return new Date(iso).toLocaleString("es-GT", { dateStyle: "long", timeStyle: "short", timeZone: "America/Guatemala" });
}

async function cargarHistorial() {
  if (textoBusqueda.value && !idResuelto.value) {
    toast("Selecciona un producto válido de la lista antes de filtrar.", "error");
    return;
  }

  const params = new URLSearchParams();
  if (idResuelto.value) params.set("producto_id", idResuelto.value);
  if (fechaDesde.value) params.set("fecha_desde", new Date(fechaDesde.value).toISOString());
  if (fechaHasta.value) params.set("fecha_hasta", new Date(fechaHasta.value).toISOString());
  if (esVendedor.value) params.set("vendedor_id", sesion.value.id_usuario);

  cargando.value = true;
  const { ok, data } = await apiFetch(`/historial?${params.toString()}`);
  cargando.value = false;

  if (!ok) {
    toast(data.error || data.detail || "No se pudo cargar el historial.", "error");
    return;
  }

  eventos.value = data.eventos || [];
}

function limpiarFiltros() {
  textoBusqueda.value = "";
  fechaDesde.value = "";
  fechaHasta.value = "";
  filaExpandida.value = null;
  cargarHistorial();
}

function alternarDetalle(index) {
  filaExpandida.value = filaExpandida.value === index ? null : index;
}

onMounted(async () => {
  await cargarProductos();
  await cargarHistorial();
});
</script>

<template>
  <div>
    <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mb-1">Historial temporal</h2>
    <p class="text-sm text-neutral-500 mb-6">Últimos cambios registrados sobre el catálogo (event sourcing)</p>

    <div class="bg-white p-4 rounded-2xl border border-neutral-200 mb-6 flex flex-wrap items-end gap-4">
      <div class="flex-1 min-w-[16rem]">
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Producto</label>
        <input
          type="text"
          v-model="textoBusqueda"
          list="lista-productos-historial"
          autocomplete="off"
          placeholder="Todos los productos"
          class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent"
        >
        <datalist id="lista-productos-historial">
          <option v-for="etiqueta in Object.keys(mapaProductos)" :key="etiqueta" :value="etiqueta"></option>
        </datalist>
      </div>
      <div class="min-w-[12rem]">
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Desde</label>
        <input type="datetime-local" v-model="fechaDesde" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>
      <div class="min-w-[12rem]">
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Hasta</label>
        <input type="datetime-local" v-model="fechaHasta" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>
      <div class="flex gap-2 shrink-0">
        <button @click="cargarHistorial" class="px-4 py-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition">Filtrar</button>
        <button @click="limpiarFiltros" class="px-4 py-2 text-neutral-500 hover:text-neutral-800 font-semibold text-sm transition">Limpiar filtros</button>
      </div>
    </div>

    <div class="bg-white p-5 rounded-2xl border border-neutral-200">
      <div class="overflow-x-auto lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto scrollbar-fina">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-white z-10">
            <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
              <th class="p-2.5">Fecha</th>
              <th class="p-2.5">Producto</th>
              <th class="p-2.5">Tipo de evento</th>
              <th class="p-2.5 text-right">Precio</th>
              <th class="p-2.5">Estado</th>
              <th class="p-2.5">Responsable</th>
              <th class="p-2.5"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!cargando && eventos.length === 0">
              <td colspan="7" class="p-6 text-center text-sm text-neutral-400">No hay cambios registrados para estos filtros.</td>
            </tr>
            <template v-for="(e, index) in eventos" :key="`${e.producto_id}-${e.fecha_evento}-${index}`">
              <tr class="border-b border-neutral-100 hover:bg-neutral-50/80 transition">
                <td class="p-2.5 text-xs text-neutral-500">{{ formatearFecha(e.fecha_evento) }}</td>
                <td class="p-2.5">
                  <div class="font-medium text-neutral-950">{{ e.nombre }}</div>
                  <div class="text-neutral-400 font-mono text-[11px]">{{ e.sku || e.producto_id }}</div>
                </td>
                <td class="p-2.5"><span class="text-[10px] font-bold uppercase px-2 py-0.5 bg-accent-50 text-accent-700 rounded-full">{{ etiquetaTipoEvento(e.tipo_evento) }}</span></td>
                <td class="p-2.5 text-right font-semibold text-neutral-950">Q{{ Number(e.precio_base).toFixed(2) }}</td>
                <td class="p-2.5"><span :class="['text-[10px] font-bold uppercase px-2 py-0.5 rounded-full', e.activo ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800']">{{ e.activo ? "Activo" : "Inactivo" }}</span></td>
                <td class="p-2.5 text-neutral-500 text-xs">{{ e.responsable }}</td>
                <td class="p-2.5 text-right">
                  <button @click="alternarDetalle(index)" class="px-2.5 py-1 bg-neutral-100 hover:bg-neutral-200 text-neutral-700 text-xs font-semibold rounded-full transition">
                    {{ filaExpandida === index ? "Ocultar" : "Ver detalle" }}
                  </button>
                </td>
              </tr>
              <tr v-if="filaExpandida === index" class="border-b border-neutral-100 bg-neutral-50">
                <td colspan="7" class="p-3.5">
                  <pre class="text-xs bg-neutral-950 text-neutral-300 p-3 rounded-lg overflow-x-auto">{{ JSON.stringify(e, null, 2) }}</pre>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
