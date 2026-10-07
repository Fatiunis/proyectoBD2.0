<script setup>
import { ref, computed, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";

const { sesion } = useSesion();

const ventas = ref([]);
const resumen = ref({ total_vendido: 0, unidades_vendidas: 0, numero_lineas: 0 });
const cargando = ref(true);
const error = ref("");
const filtroEstado = ref("todos");

const ESTILO_ESTADO = {
  pendiente: "bg-amber-100 text-amber-800",
  pagado: "bg-emerald-100 text-emerald-800",
  enviado: "bg-sky-100 text-sky-800",
  entregado: "bg-emerald-100 text-emerald-800",
  cancelado: "bg-red-100 text-red-800",
};

const esAdmin = computed(() => sesion.value?.rol === "administrador");

const numeroPedidos = computed(() => new Set(ventas.value.map((v) => v.id_pedido)).size);

const estados = computed(() => {
  const conteo = {};
  ventas.value.forEach((v) => (conteo[v.estado] = (conteo[v.estado] || 0) + 1));
  return Object.entries(conteo).sort(([a], [b]) => a.localeCompare(b));
});

const ventasFiltradas = computed(() =>
  filtroEstado.value === "todos" ? ventas.value : ventas.value.filter((v) => v.estado === filtroEstado.value)
);
const subtotalFiltrado = computed(() => ventasFiltradas.value.reduce((s, v) => s + Number(v.subtotal || 0), 0));

function q(n) {
  return `Q${Number(n || 0).toLocaleString("es-GT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatearFecha(iso) {
  return new Date(iso).toLocaleString("es-GT", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Guatemala" });
}

async function cargarMisVentas() {
  cargando.value = true;
  error.value = "";
  const { id_usuario, rol } = sesion.value;
  const { ok, data } = await apiFetch(
    `/vendedores/${id_usuario}/ventas?rol_solicitante=${encodeURIComponent(rol)}&id_usuario=${id_usuario}`
  );
  cargando.value = false;
  if (!ok) {
    error.value = data?.error || "No se pudieron cargar las ventas.";
    return;
  }
  ventas.value = data.ventas || [];
  resumen.value = data.resumen || resumen.value;
  if (filtroEstado.value !== "todos" && !ventas.value.some((v) => v.estado === filtroEstado.value)) filtroEstado.value = "todos";
}

function claseChip(activo) {
  return [
    "px-3 py-1 rounded-full text-xs font-semibold border transition",
    activo ? "bg-neutral-950 border-neutral-950 text-white" : "border-neutral-200 text-neutral-600 hover:border-neutral-400",
  ];
}

onMounted(cargarMisVentas);
</script>

<template>
  <div>
    <div class="flex flex-wrap justify-between items-start gap-4 mb-6">
      <div>
        <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mb-1">Mis ventas</h2>
        <p class="text-sm text-neutral-500">Líneas de pedido de tus propios productos (fuente: PostgreSQL)</p>
      </div>
      <button
        @click="cargarMisVentas"
        :disabled="cargando"
        class="px-4 py-2 border border-neutral-200 hover:border-neutral-400 text-neutral-700 font-semibold rounded-full text-sm transition disabled:opacity-50"
      >{{ cargando ? "Actualizando..." : "Actualizar" }}</button>
    </div>

    <div
      v-if="error"
      role="alert"
      class="mb-6 flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
    >
      <span class="mt-0.5 w-5 h-5 shrink-0 rounded-full bg-red-600 text-white text-xs font-bold flex items-center justify-center" aria-hidden="true">!</span>
      <p class="flex-1">{{ error }}</p>
      <button @click="cargarMisVentas" class="shrink-0 text-xs font-semibold underline underline-offset-2 hover:text-red-600">Reintentar</button>
    </div>

    <template v-else>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div class="bg-white p-5 rounded-2xl border border-neutral-200">
          <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Total vendido</p>
          <p class="text-2xl font-extrabold text-accent-700">{{ cargando ? "—" : q(resumen.total_vendido) }}</p>
        </div>
        <div class="bg-white p-5 rounded-2xl border border-neutral-200">
          <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Unidades vendidas</p>
          <p class="text-2xl font-extrabold text-neutral-950">{{ cargando ? "—" : resumen.unidades_vendidas }}</p>
        </div>
        <div class="bg-white p-5 rounded-2xl border border-neutral-200">
          <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Pedidos</p>
          <p class="text-2xl font-extrabold text-neutral-950">{{ cargando ? "—" : numeroPedidos }}</p>
          <p v-if="!cargando" class="text-xs text-neutral-400 mt-0.5">{{ resumen.numero_lineas }} líneas de pedido</p>
        </div>
      </div>

      <div v-if="cargando" class="bg-white p-5 rounded-2xl border border-neutral-200 space-y-3 animate-pulse" aria-busy="true">
        <div v-for="n in 5" :key="n" class="h-8 bg-neutral-100 rounded-lg"></div>
      </div>

      <div
        v-else-if="ventas.length === 0"
        class="bg-white rounded-2xl border border-dashed border-neutral-300 px-6 py-14 flex flex-col items-center text-center"
      >
        <div class="w-16 h-16 rounded-2xl bg-accent-50 text-accent flex items-center justify-center mb-4">
          <svg class="w-8 h-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" /><path d="M3 6h18" /><path d="M16 10a4 4 0 0 1-8 0" />
          </svg>
        </div>
        <h3 class="text-lg font-bold text-neutral-950 tracking-tight">Aún no tienes ventas de productos propios</h3>
        <p class="text-sm text-neutral-500 max-w-md mt-1">
          {{ esAdmin
            ? "Los productos que crees desde Catálogo aparecerán aquí cuando se vendan."
            : "Cuando un comprador confirme un pedido de tus productos, aparecerá aquí." }}
        </p>
      </div>

      <div v-else class="bg-white p-5 rounded-2xl border border-neutral-200">
        <div class="flex flex-wrap items-center gap-2 mb-4" role="group" aria-label="Filtrar por estado">
          <span class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mr-1">Estado</span>
          <button type="button" @click="filtroEstado = 'todos'" :aria-pressed="filtroEstado === 'todos'" :class="claseChip(filtroEstado === 'todos')">
            Todos · {{ ventas.length }}
          </button>
          <button
            v-for="[estado, n] in estados"
            :key="estado"
            type="button"
            @click="filtroEstado = estado"
            :aria-pressed="filtroEstado === estado"
            :class="[claseChip(filtroEstado === estado), 'capitalize']"
          >{{ estado }} · {{ n }}</button>
        </div>

        <div class="overflow-x-auto lg:max-h-[calc(100vh-22rem)] lg:overflow-y-auto scrollbar-fina">
          <table class="w-full text-sm">
            <thead class="sticky top-0 bg-white z-10">
              <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
                <th class="p-2.5">Pedido</th>
                <th class="p-2.5">Producto</th>
                <th class="p-2.5 text-right">Cant.</th>
                <th class="p-2.5 text-right">Precio unit.</th>
                <th class="p-2.5 text-right">Subtotal</th>
                <th class="p-2.5">Estado</th>
                <th class="p-2.5">Fecha</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in ventasFiltradas" :key="v.id_linea" class="border-b border-neutral-100 hover:bg-neutral-50/80 transition">
                <td class="p-2.5 text-neutral-400 font-mono text-xs whitespace-nowrap">#{{ v.id_pedido }}</td>
                <td class="p-2.5 min-w-48">
                  <p class="font-medium text-neutral-950">{{ v.nombre_producto_historico }}</p>
                  <p class="text-[11px] text-neutral-400 font-mono">ID {{ v.id_producto }}</p>
                </td>
                <td class="p-2.5 text-right text-neutral-700 tabular-nums">{{ v.cantidad }}</td>
                <td class="p-2.5 text-right text-neutral-500 tabular-nums whitespace-nowrap">{{ q(v.precio_unitario_historico) }}</td>
                <td class="p-2.5 text-right font-semibold text-neutral-950 tabular-nums whitespace-nowrap">{{ q(v.subtotal) }}</td>
                <td class="p-2.5"><span :class="['text-[10px] font-bold uppercase px-2 py-0.5 rounded-full whitespace-nowrap', ESTILO_ESTADO[v.estado] || 'bg-neutral-100 text-neutral-700']">{{ v.estado }}</span></td>
                <td class="p-2.5 text-xs text-neutral-500 whitespace-nowrap">{{ formatearFecha(v.fecha_pedido) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="flex justify-end gap-2 pt-3 mt-1 border-t border-neutral-100 text-sm">
          <span class="text-neutral-400">{{ filtroEstado === "todos" ? "Total de las líneas" : `Total ${filtroEstado}` }}</span>
          <span class="font-bold text-neutral-950 tabular-nums">{{ q(subtotalFiltrado) }}</span>
        </div>
      </div>
    </template>
  </div>
</template>
