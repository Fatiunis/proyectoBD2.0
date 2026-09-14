<script setup>
import { ref, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";

const { sesion } = useSesion();
const { toast } = useToast();

const alertas = ref([]);
const cargando = ref(true);
const filaExpandida = ref(null);

function nombresCuentas(alerta) {
  return alerta.cuentas_involucradas.map((c) => c.nombre).join(", ");
}

function productosUnicos(alerta) {
  return [...new Set(alerta.productos_compartidos)];
}

function alternarDetalle(index) {
  filaExpandida.value = filaExpandida.value === index ? null : index;
}

async function cargarAlertas() {
  cargando.value = true;
  const { ok, data } = await apiFetch(`/fraude/alertas?rol_solicitante=${sesion.value.rol}`);
  cargando.value = false;

  if (!ok) {
    toast(data?.error || "No se pudieron cargar las alertas de fraude.", "error");
    return;
  }
  alertas.value = data.alertas || [];
}

onMounted(cargarAlertas);
</script>

<template>
  <div>
    <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mb-1">Alertas de fraude</h2>
    <p class="text-sm text-neutral-500 mb-6">Anillos de cuentas con calificaciones cruzadas coordinadas (fuente: Neo4j)</p>

    <div class="bg-white p-5 rounded-2xl border border-neutral-200 mb-6 max-w-xs">
      <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Total de alertas</p>
      <p class="text-2xl font-extrabold text-neutral-950">{{ alertas.length }}</p>
    </div>

    <div class="bg-white p-5 rounded-2xl border border-neutral-200">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
              <th class="p-2.5">Cuentas involucradas</th>
              <th class="p-2.5">Productos compartidos</th>
              <th class="p-2.5 text-right">Score de anomalía</th>
              <th class="p-2.5"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!cargando && alertas.length === 0">
              <td colspan="4" class="p-6 text-center text-sm text-neutral-400">No se detectaron alertas de fraude con estos parámetros.</td>
            </tr>
            <template v-for="(a, index) in alertas" :key="index">
              <tr class="border-b border-neutral-100 hover:bg-neutral-50/80 transition">
                <td class="p-2.5 font-medium text-neutral-950">{{ nombresCuentas(a) }}</td>
                <td class="p-2.5 text-neutral-600 font-mono text-xs">{{ productosUnicos(a).join(", ") }}</td>
                <td class="p-2.5 text-right font-semibold text-neutral-950">{{ a.score_anomalia }}</td>
                <td class="p-2.5 text-right">
                  <button @click="alternarDetalle(index)" class="px-2.5 py-1 bg-neutral-100 hover:bg-neutral-200 text-neutral-700 text-xs font-semibold rounded-full transition">
                    {{ filaExpandida === index ? "Ocultar" : "Ver detalle" }}
                  </button>
                </td>
              </tr>
              <tr v-if="filaExpandida === index" class="border-b border-neutral-100 bg-neutral-50">
                <td colspan="4" class="p-3.5">
                  <pre class="text-xs bg-neutral-950 text-neutral-300 p-3 rounded-lg overflow-x-auto">{{ JSON.stringify(a, null, 2) }}</pre>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
