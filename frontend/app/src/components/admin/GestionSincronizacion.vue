<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";

// Eventos de sincronización del checkout (outbox, Entrega 3): lo que quedó
// pendiente en Redis, MongoDB o Elasticsearch después de confirmar un pedido.
// Se refresca solo cada 5 s para ver al relevo trabajar.

const { sesion } = useSesion();
const { toast } = useToast();

const ETIQUETAS_TIPO = {
  confirmar_reserva_oferta: "Cerrar reserva de oferta (Redis)",
  limpiar_carrito: "Limpiar carrito (Redis)",
  stock_mongo: "Copiar stock a MongoDB",
  stock_elasticsearch: "Copiar stock a Elasticsearch",
  indexar_producto: "Reindexar producto (Elasticsearch)",
};
const ESTILO_ESTADO = {
  pendiente: "bg-amber-100 text-amber-800",
  procesado: "bg-accent-50 text-accent-700",
  fallido: "bg-red-100 text-red-700",
};

const resumen = ref({ pendiente: 0, procesado: 0, fallido: 0 });
const eventos = ref([]);
const filtroEstado = ref("");
const cargando = ref(true);
const trabajando = ref(false);
let intervalo = null;

function fecha(iso) {
  return iso ? new Date(iso).toLocaleString("es-GT", { dateStyle: "short", timeStyle: "medium" }) : "—";
}

async function cargar() {
  const params = new URLSearchParams({ rol_solicitante: sesion.value.rol, limite: 100 });
  if (filtroEstado.value) params.set("estado", filtroEstado.value);
  const { ok, data } = await apiFetch(`/sincronizacion/eventos?${params}`);
  cargando.value = false;
  if (!ok) {
    toast(data?.error || "No se pudieron cargar los eventos de sincronización.", "error");
    return;
  }
  resumen.value = data.resumen;
  eventos.value = data.eventos;
}

async function accion(ruta, mensajeExito) {
  trabajando.value = true;
  const { ok, data } = await apiFetch(ruta, {
    method: "POST",
    body: JSON.stringify({ rol_solicitante: sesion.value.rol }),
  });
  trabajando.value = false;
  if (!ok) {
    toast(data?.error || "No se pudo completar la acción.", "error");
    return;
  }
  toast(mensajeExito(data), "success");
  cargar();
}

const procesarAhora = () =>
  accion("/sincronizacion/procesar", (d) => `Procesados: ${d.procesados} · siguen pendientes: ${d.pendientes} · fallidos: ${d.fallidos}`);
const reintentarFallidos = () => accion("/sincronizacion/reintentar-fallidos", (d) => d.mensaje);

onMounted(() => {
  cargar();
  intervalo = setInterval(cargar, 5000);
});
onUnmounted(() => clearInterval(intervalo));
</script>

<template>
  <div>
    <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mb-1">Sincronización del checkout</h2>
    <p class="text-sm text-neutral-500 mb-6 max-w-3xl">
      Trabajo pendiente en Redis, MongoDB y Elasticsearch después de confirmar un pedido en PostgreSQL (outbox).
      Si un motor falla, el evento queda pendiente y se reintenta solo con espera creciente; el pedido ya es válido.
    </p>

    <div class="grid grid-cols-3 gap-4 mb-6 max-w-2xl">
      <button
        v-for="estado in ['pendiente', 'procesado', 'fallido']"
        :key="estado"
        @click="filtroEstado = filtroEstado === estado ? '' : estado; cargar()"
        :class="['bg-white p-5 rounded-2xl border text-left transition', filtroEstado === estado ? 'border-neutral-950' : 'border-neutral-200 hover:border-neutral-400']"
      >
        <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">{{ estado }}s</p>
        <p class="text-2xl font-extrabold text-neutral-950">{{ resumen[estado] }}</p>
      </button>
    </div>

    <div class="flex flex-wrap gap-2 mb-6">
      <button @click="procesarAhora" :disabled="trabajando" class="px-4 py-2 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 text-white font-semibold rounded-full text-sm transition">
        Procesar pendientes ahora
      </button>
      <button @click="reintentarFallidos" :disabled="trabajando || !resumen.fallido" class="px-4 py-2 border border-neutral-300 hover:border-neutral-950 disabled:opacity-40 text-neutral-800 font-semibold rounded-full text-sm transition">
        Volver a encolar fallidos
      </button>
    </div>

    <div class="bg-white p-5 rounded-2xl border border-neutral-200">
      <p v-if="cargando" class="text-sm text-neutral-500">Cargando eventos...</p>
      <p v-else-if="!eventos.length" class="text-sm text-neutral-500">No hay eventos{{ filtroEstado ? ` en estado "${filtroEstado}"` : "" }}.</p>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
              <th class="p-2.5">#</th>
              <th class="p-2.5">Tarea</th>
              <th class="p-2.5">Pedido</th>
              <th class="p-2.5">Estado</th>
              <th class="p-2.5 text-right">Intentos</th>
              <th class="p-2.5">Último error</th>
              <th class="p-2.5">Creado</th>
              <th class="p-2.5">Próximo intento / procesado</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in eventos" :key="e.id_evento" class="border-b border-neutral-50 align-top">
              <td class="p-2.5 text-neutral-400">{{ e.id_evento }}</td>
              <td class="p-2.5 font-medium text-neutral-900">{{ ETIQUETAS_TIPO[e.tipo] || e.tipo }}</td>
              <td class="p-2.5">{{ e.id_pedido ? `#${e.id_pedido}` : "—" }}</td>
              <td class="p-2.5"><span :class="['px-2 py-0.5 rounded-full text-xs font-semibold', ESTILO_ESTADO[e.estado]]">{{ e.estado }}</span></td>
              <td class="p-2.5 text-right">{{ e.intentos }}</td>
              <td class="p-2.5 text-xs text-red-700 max-w-xs break-words">{{ e.ultimo_error || "" }}</td>
              <td class="p-2.5 text-xs text-neutral-500 whitespace-nowrap">{{ fecha(e.creado_en) }}</td>
              <td class="p-2.5 text-xs text-neutral-500 whitespace-nowrap">{{ e.estado === "procesado" ? fecha(e.procesado_en) : fecha(e.proximo_intento) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
