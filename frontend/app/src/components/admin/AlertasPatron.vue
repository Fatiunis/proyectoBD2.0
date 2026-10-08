<script setup>
import { ref, reactive, computed, watch, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import AlertaFraude from "./AlertaFraude.vue";
import { etiquetaParametro, duracionLegible, mensajeErrorFraude } from "../../utils/fraude";

const props = defineProps({
  patron: { type: Object, required: true },
  recarga: { type: Number, default: 0 },
});

const { sesion } = useSesion();

const valores = reactive(Object.fromEntries(Object.entries(props.patron.parametros || {}).map(([k, v]) => [k, String(v)])));
const alertas = ref([]);
const total = ref(0);
const cargando = ref(true);
const error = ref("");
const ajustesAbiertos = ref(false);

const ENTERO_POSITIVO = /^[1-9]\d*$/;
const esPorcentaje = (clave) => /(^|_)pct(_|$)/.test(clave);
function valorValido(clave) {
  const v = String(valores[clave]).trim();
  if (!ENTERO_POSITIVO.test(v)) return false;
  return !esPorcentaje(clave) || Number(v) <= 100;
}
const invalidos = computed(() => Object.keys(valores).filter((k) => !valorValido(k)));
const aplicados = ref({ ...valores });
const ajustada = computed(() =>
  Object.entries(props.patron.parametros || {}).some(([k, v]) => String(aplicados.value[k]).trim() !== String(v))
);

async function cargar() {
  if (invalidos.value.length) return;
  cargando.value = true;
  error.value = "";
  aplicados.value = { ...valores };
  const params = new URLSearchParams({ rol_solicitante: sesion.value.rol });
  Object.entries(valores).forEach(([k, v]) => params.set(k, String(v).trim()));
  const { ok, status, data } = await apiFetch(`/fraude/alertas/${encodeURIComponent(props.patron.tipo)}?${params}`);
  cargando.value = false;
  if (!ok) {
    error.value = mensajeErrorFraude(status, data, "No se pudieron cargar las alertas de este patrón.");
    return;
  }
  alertas.value = data.alertas || [];
  total.value = data.total ?? alertas.value.length;
}

function restaurar() {
  Object.entries(props.patron.parametros || {}).forEach(([k, v]) => (valores[k] = String(v)));
  cargar();
}

watch(() => props.recarga, cargar);
onMounted(cargar);
</script>

<template>
  <div>
    <p v-if="patron.descripcion" class="text-sm text-neutral-700 mb-4 max-w-3xl leading-relaxed">{{ patron.descripcion }}</p>

    <div v-if="Object.keys(valores).length" class="mb-5">
      <button
        type="button"
        @click="ajustesAbiertos = !ajustesAbiertos"
        :aria-expanded="ajustesAbiertos"
        :aria-controls="`ajustes-${patron.tipo}`"
        class="inline-flex items-center gap-1.5 text-sm font-semibold text-neutral-600 hover:text-neutral-950 transition"
      >
        <svg :class="['w-3.5 h-3.5 transition-transform', ajustesAbiertos ? 'rotate-90' : '']" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fill-rule="evenodd" d="M7.2 14.8a.75.75 0 0 1 0-1.06L10.94 10 7.2 6.26a.75.75 0 1 1 1.06-1.06l4.27 4.27a.75.75 0 0 1 0 1.06L8.26 14.8a.75.75 0 0 1-1.06 0Z" clip-rule="evenodd" />
        </svg>
        Ajustar sensibilidad
        <span v-if="ajustada" class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[11px] font-bold">ajustada</span>
      </button>

      <form
        v-if="ajustesAbiertos"
        :id="`ajustes-${patron.tipo}`"
        @submit.prevent="cargar"
        class="mt-3 bg-white p-4 rounded-2xl border border-neutral-200 flex flex-wrap items-end gap-4"
        :aria-label="`Sensibilidad de ${patron.nombre}`"
      >
        <div v-for="(_, clave) in valores" :key="clave" class="flex flex-col">
          <label :for="`param-${patron.tipo}-${clave}`" class="text-xs font-semibold text-neutral-600 mb-1">
            {{ etiquetaParametro(clave) }}
          </label>
          <input
            :id="`param-${patron.tipo}-${clave}`"
            v-model="valores[clave]"
            type="number"
            min="1"
            :max="esPorcentaje(clave) ? 100 : undefined"
            step="1"
            inputmode="numeric"
            :aria-invalid="invalidos.includes(clave)"
            :aria-describedby="`ayuda-${patron.tipo}-${clave}`"
            :class="[
              'w-40 px-3 py-2 rounded-xl border text-sm focus:outline-none focus:ring-2 focus:ring-accent-600/40',
              invalidos.includes(clave) ? 'border-red-400' : 'border-neutral-200',
            ]"
          />
          <span :id="`ayuda-${patron.tipo}-${clave}`" class="text-[11px] text-neutral-400 mt-1">
            <template v-if="invalidos.includes(clave)"><span class="text-red-600">{{ esPorcentaje(clave) ? "Debe ser un entero entre 1 y 100" : "Debe ser un entero positivo" }}</span></template>
            <template v-else>
              <template v-if="esPorcentaje(clave)">Entre 1 y 100 · </template>Por defecto {{ patron.parametros[clave] }}<template v-if="clave.endsWith('_segundos') && duracionLegible(valores[clave])"> · {{ duracionLegible(valores[clave]) }}</template>
            </template>
          </span>
        </div>
        <div class="flex gap-2 pb-5">
          <button
            type="submit"
            :disabled="cargando || invalidos.length > 0"
            class="px-4 py-2 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 text-white font-semibold rounded-full text-sm transition"
          >Aplicar</button>
          <button
            v-if="ajustada"
            type="button"
            @click="restaurar"
            :disabled="cargando"
            class="px-4 py-2 border border-neutral-200 hover:border-neutral-400 text-neutral-700 font-semibold rounded-full text-sm transition disabled:opacity-50"
          >Restaurar valores</button>
        </div>
      </form>
    </div>

    <div
      v-if="error"
      role="alert"
      class="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
    >
      <span class="mt-0.5 w-5 h-5 shrink-0 rounded-full bg-red-600 text-white text-xs font-bold flex items-center justify-center" aria-hidden="true">!</span>
      <p class="flex-1">{{ error }}</p>
      <button @click="cargar" class="shrink-0 text-xs font-semibold underline underline-offset-2 hover:text-red-600">Reintentar</button>
    </div>

    <p v-else-if="cargando" class="text-sm text-neutral-500" aria-live="polite">Buscando el patrón en el grafo...</p>

    <div v-else-if="!alertas.length" class="bg-white p-8 rounded-2xl border border-neutral-200 text-center">
      <p class="text-sm font-semibold text-neutral-800">No se detectó este patrón</p>
      <p v-if="ajustada" class="text-xs text-neutral-500 mt-1">
        Con la sensibilidad ajustada.
        <button type="button" @click="restaurar" class="font-semibold text-accent-700 underline underline-offset-2">Volver a los valores por defecto</button>
      </p>
    </div>

    <div v-else>
      <p class="text-xs text-neutral-500 mb-3" aria-live="polite">
        {{ total }} alerta{{ total === 1 ? "" : "s" }}<template v-if="total > alertas.length">, se muestran las {{ alertas.length }} de mayor riesgo</template>
      </p>
      <div class="space-y-2.5">
        <AlertaFraude v-for="(a, i) in alertas" :key="i" :alerta="a" />
      </div>
    </div>
  </div>
</template>
