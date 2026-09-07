<script setup>
import { ref, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";

const { sesion } = useSesion();
const { toast } = useToast();

const ventas = ref([]);
const resumen = ref({ total_vendido: 0, unidades_vendidas: 0, numero_lineas: 0 });

const ESTILO_ESTADO = {
  pendiente: "bg-amber-100 text-amber-800",
  pagado: "bg-emerald-100 text-emerald-800",
  enviado: "bg-sky-100 text-sky-800",
  entregado: "bg-emerald-100 text-emerald-800",
  cancelado: "bg-red-100 text-red-800",
};

function formatearFecha(iso) {
  return new Date(iso).toLocaleString("es-GT", { dateStyle: "long", timeStyle: "short", timeZone: "America/Guatemala" });
}

async function cargarMisVentas() {
  const { ok, data } = await apiFetch(`/vendedores/${sesion.value.id_usuario}/ventas`);
  if (!ok) {
    toast(data.error || "No se pudieron cargar las ventas.", "error");
    return;
  }
  ventas.value = data.ventas || [];
  resumen.value = data.resumen;
}

onMounted(cargarMisVentas);
</script>

<template>
  <div>
    <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mb-1">Mis ventas</h2>
    <p class="text-sm text-neutral-500 mb-6">Líneas de pedido de productos vendidos por tu cuenta (fuente: PostgreSQL)</p>

    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="bg-white p-5 rounded-2xl border border-neutral-200">
        <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Total vendido</p>
        <p class="text-2xl font-extrabold text-neutral-950">Q{{ resumen.total_vendido.toFixed(2) }}</p>
      </div>
      <div class="bg-white p-5 rounded-2xl border border-neutral-200">
        <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Unidades vendidas</p>
        <p class="text-2xl font-extrabold text-neutral-950">{{ resumen.unidades_vendidas }}</p>
      </div>
      <div class="bg-white p-5 rounded-2xl border border-neutral-200">
        <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Líneas de pedido</p>
        <p class="text-2xl font-extrabold text-neutral-950">{{ resumen.numero_lineas }}</p>
      </div>
    </div>

    <div class="bg-white p-5 rounded-2xl border border-neutral-200">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
              <th class="p-2.5">Pedido</th>
              <th class="p-2.5">Producto</th>
              <th class="p-2.5 text-right">Cantidad</th>
              <th class="p-2.5 text-right">Subtotal</th>
              <th class="p-2.5">Estado</th>
              <th class="p-2.5">Fecha</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="ventas.length === 0">
              <td colspan="6" class="p-6 text-center text-sm text-neutral-400">Aún no tienes ventas registradas.</td>
            </tr>
            <tr v-for="v in ventas" :key="v.id_linea" class="border-b border-neutral-100 hover:bg-neutral-50/80 transition">
              <td class="p-2.5 text-neutral-400 font-mono text-xs">#{{ v.id_pedido }}</td>
              <td class="p-2.5 font-medium text-neutral-950">{{ v.nombre_producto_historico }}</td>
              <td class="p-2.5 text-right text-neutral-700">{{ v.cantidad }}</td>
              <td class="p-2.5 text-right font-semibold text-neutral-950">Q{{ v.subtotal.toFixed(2) }}</td>
              <td class="p-2.5"><span :class="['text-[10px] font-bold uppercase px-2 py-0.5 rounded-full', ESTILO_ESTADO[v.estado] || 'bg-neutral-100 text-neutral-700']">{{ v.estado }}</span></td>
              <td class="p-2.5 text-xs text-neutral-500">{{ formatearFecha(v.fecha_pedido) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
