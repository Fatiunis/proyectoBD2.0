<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { FRASE_PATRON } from "../../utils/fraude";

defineProps({
  alertas: { type: Array, default: () => [] },
  cargando: { type: Boolean, default: false },
  error: { type: String, default: "" },
});
const emit = defineEmits(["reintentar"]);

const router = useRouter();

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
</script>

<template>
  <div>
    <p class="text-sm text-neutral-700 mb-4 max-w-3xl leading-relaxed">{{ FRASE_PATRON.anillos_resenas }}</p>

    <div
      v-if="error"
      role="alert"
      class="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
    >
      <span class="mt-0.5 w-5 h-5 shrink-0 rounded-full bg-red-600 text-white text-xs font-bold flex items-center justify-center" aria-hidden="true">!</span>
      <p class="flex-1">{{ error }}</p>
      <button @click="emit('reintentar')" class="shrink-0 text-xs font-semibold underline underline-offset-2 hover:text-red-600">Reintentar</button>
    </div>

    <p v-else-if="cargando" class="text-sm text-neutral-500" aria-live="polite">Buscando anillos en el grafo...</p>

    <div v-else-if="!alertas.length" class="bg-white p-8 rounded-2xl border border-neutral-200 text-center">
      <p class="text-sm font-semibold text-neutral-800">No se detectaron anillos de reseñas</p>
    </div>

    <div v-else class="bg-white p-5 rounded-2xl border border-neutral-200">
      <p class="text-xs text-neutral-500 mb-3" aria-live="polite">
        {{ alertas.length }} anillo{{ alertas.length === 1 ? "" : "s" }} detectado{{ alertas.length === 1 ? "" : "s" }}
        (consulta original de la Entrega 2, <span class="font-mono">GET /api/fraude/alertas</span>)
      </p>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
              <th class="p-2.5">Cuentas involucradas</th>
              <th class="p-2.5">Productos compartidos</th>
              <th class="p-2.5 text-right">Score de anomalía</th>
              <th class="p-2.5"><span class="sr-only">Detalle</span></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(a, index) in alertas" :key="index">
              <tr class="border-b border-neutral-100 hover:bg-neutral-50/80 transition">
                <td class="p-2.5 font-medium text-neutral-950">{{ nombresCuentas(a) }}</td>
                <td class="p-2.5 text-neutral-600 font-mono text-xs">{{ productosUnicos(a).join(", ") }}</td>
                <td class="p-2.5 text-right font-semibold text-neutral-950">{{ a.score_anomalia }}</td>
                <td class="p-2.5 text-right">
                  <button
                    @click="alternarDetalle(index)"
                    :aria-expanded="filaExpandida === index"
                    class="px-2.5 py-1 bg-neutral-100 hover:bg-neutral-200 text-neutral-700 text-xs font-semibold rounded-full transition"
                  >
                    {{ filaExpandida === index ? "Ocultar" : "Ver detalle" }}
                  </button>
                </td>
              </tr>
              <tr v-if="filaExpandida === index" class="border-b border-neutral-100 bg-neutral-50">
                <td colspan="4" class="p-4">
                  <dl class="grid gap-4 md:grid-cols-3 text-sm">
                    <div>
                      <dt class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Cuentas</dt>
                      <dd>
                        <ul class="space-y-0.5">
                          <li v-for="c in a.cuentas_involucradas" :key="c.id_usuario" class="text-neutral-800">
                            {{ c.nombre }} <span class="text-neutral-400">#{{ c.id_usuario }}</span>
                          </li>
                        </ul>
                      </dd>
                    </div>
                    <div>
                      <dt class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">
                        Productos en común ({{ productosUnicos(a).length }})
                      </dt>
                      <dd class="flex flex-wrap gap-1.5">
                        <a
                          v-for="p in productosUnicos(a)"
                          :key="p"
                          :href="router.resolve(`/producto/${encodeURIComponent(p)}`).href"
                          target="_blank"
                          rel="noopener"
                          class="px-2 py-0.5 rounded-full border border-neutral-200 hover:border-accent-600 font-mono text-xs text-accent-700 transition"
                        >{{ p }}</a>
                      </dd>
                    </div>
                    <div>
                      <dt class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Score de anomalía</dt>
                      <dd class="text-neutral-800">
                        <span class="font-semibold">{{ a.score_anomalia }}</span>
                        <span class="text-neutral-500"> = suma de productos calificados con 5★ por cada par de cuentas del trío, dentro de la misma ventana de tiempo</span>
                      </dd>
                    </div>
                  </dl>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
