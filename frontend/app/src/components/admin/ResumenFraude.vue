<script setup>
import { ref, computed } from "vue";
import { ESTILO_NIVEL, ETIQUETA_NIVEL, FRASE_PATRON, ANILLOS } from "../../utils/fraude";

const props = defineProps({
  patrones: { type: Array, default: () => [] },
  resumen: { type: Object, default: null },
  cargando: { type: Boolean, default: false },
  error: { type: String, default: "" },
  anillos: { type: Object, default: () => ({ total: 0, cargando: false, error: "" }) },
});
const emit = defineEmits(["seleccionar", "reintentar"]);

const CUENTAS_VISIBLES = 10;
const verTodas = ref(false);

const nombrePorTipo = computed(() => Object.fromEntries(props.patrones.map((p) => [p.tipo, p.nombre])));

const tarjetas = computed(() => [
  {
    tipo: ANILLOS,
    nombre: "Anillos de reseñas",
    frase: FRASE_PATRON[ANILLOS],
    total: props.anillos.total,
    cargando: props.anillos.cargando,
    sinDato: Boolean(props.anillos.error),
  },
  ...props.patrones.map((p) => ({
    tipo: p.tipo,
    nombre: p.nombre,
    frase: FRASE_PATRON[p.tipo] || p.descripcion,
    total: props.resumen?.por_tipo?.[p.tipo] ?? 0,
    cargando: props.cargando,
    sinDato: false,
  })),
]);

const cuentas = computed(() => props.resumen?.cuentas_riesgo || []);
const cuentasVisibles = computed(() => (verTodas.value ? cuentas.value : cuentas.value.slice(0, CUENTAS_VISIBLES)));
</script>

<template>
  <div>
    <div
      v-if="error"
      role="alert"
      class="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
    >
      <span class="mt-0.5 w-5 h-5 shrink-0 rounded-full bg-red-600 text-white text-xs font-bold flex items-center justify-center" aria-hidden="true">!</span>
      <p class="flex-1">{{ error }}</p>
      <button @click="emit('reintentar')" class="shrink-0 text-xs font-semibold underline underline-offset-2 hover:text-red-600">Reintentar</button>
    </div>

    <template v-else>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 mb-6">
        <button
          v-for="t in tarjetas"
          :key="t.tipo"
          type="button"
          @click="emit('seleccionar', t.tipo)"
          :aria-label="`${t.nombre}: ${t.cargando ? 'cargando' : t.sinDato ? 'sin datos' : t.total} alertas. Abrir la pestaña`"
          class="group bg-white p-4 rounded-2xl border border-neutral-200 hover:border-neutral-400 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-600/50"
        >
          <p class="text-sm font-bold text-neutral-950 mb-1">{{ t.nombre }}</p>
          <p :class="['text-3xl font-extrabold leading-none mb-2', !t.cargando && !t.sinDato && t.total > 0 ? 'text-red-700' : 'text-neutral-300']">
            {{ t.cargando || t.sinDato ? "—" : t.total }}
          </p>
          <p v-if="t.sinDato" class="text-xs font-semibold text-red-700 mb-1">No se pudo cargar</p>
          <p class="text-xs text-neutral-500 leading-snug">{{ t.frase }}</p>
        </button>
      </div>

      <section class="bg-white p-5 rounded-2xl border border-neutral-200" aria-labelledby="titulo-cuentas-riesgo">
        <h3 id="titulo-cuentas-riesgo" class="text-sm font-bold text-neutral-950 mb-3">Cuentas de mayor riesgo</h3>
        <p v-if="cargando" class="text-sm text-neutral-500" aria-live="polite">Buscando cuentas sospechosas...</p>
        <p v-else-if="!cuentas.length" class="text-sm text-neutral-500">Ninguna cuenta aparece en las alertas.</p>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
                <th class="p-2.5">Cuenta</th>
                <th class="p-2.5">Nivel</th>
                <th class="p-2.5">Aparece en</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in cuentasVisibles" :key="c.id_usuario" class="border-b border-neutral-50 align-middle">
                <td class="p-2.5 font-medium text-neutral-950 whitespace-nowrap">
                  {{ c.nombre }} <span class="text-neutral-400 font-normal">#{{ c.id_usuario }}</span>
                </td>
                <td class="p-2.5">
                  <span :class="['px-2 py-0.5 rounded-full text-xs font-bold border', ESTILO_NIVEL[c.nivel] || ESTILO_NIVEL.bajo]">
                    {{ ETIQUETA_NIVEL[c.nivel] || c.nivel }}
                  </span>
                </td>
                <td class="p-2.5">
                  <div class="flex flex-wrap gap-1">
                    <button
                      v-for="tipo in c.patrones"
                      :key="tipo"
                      type="button"
                      @click="emit('seleccionar', tipo)"
                      class="px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-700 text-xs font-semibold hover:bg-neutral-950 hover:text-white transition"
                    >{{ nombrePorTipo[tipo] || tipo }}</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <button
            v-if="cuentas.length > CUENTAS_VISIBLES"
            type="button"
            @click="verTodas = !verTodas"
            class="mt-3 text-xs font-semibold text-accent-700 underline underline-offset-2"
          >{{ verTodas ? `Ver solo las primeras ${CUENTAS_VISIBLES}` : `Ver las ${cuentas.length} cuentas` }}</button>
        </div>
      </section>
    </template>
  </div>
</template>
