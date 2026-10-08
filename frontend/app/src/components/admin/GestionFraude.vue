<script setup>
import { ref, computed, nextTick, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import ResumenFraude from "./ResumenFraude.vue";
import AlertasPatron from "./AlertasPatron.vue";
import AnillosResenas from "./AnillosResenas.vue";
import { mensajeErrorFraude, ANILLOS } from "../../utils/fraude";

const RESUMEN = "resumen";

const { sesion } = useSesion();
const route = useRoute();
const router = useRouter();

const patrones = ref([]);
const cargandoPatrones = ref(true);
const errorPatrones = ref("");
const resumen = ref(null);
const cargandoResumen = ref(true);
const errorResumen = ref("");
const anillos = ref([]);
const totalAnillos = ref(0);
const cargandoAnillos = ref(true);
const errorAnillos = ref("");
const recarga = ref(0);
const listaPestanas = ref(null);

const pestanas = computed(() => [
  { tipo: RESUMEN, nombre: "Resumen" },
  { tipo: ANILLOS, nombre: "Anillos de reseñas (Entrega 2)" },
  ...patrones.value,
]);
const tipoActivo = computed(() => {
  const pedido = route.query.patron;
  return pestanas.value.some((p) => p.tipo === pedido) ? pedido : RESUMEN;
});
const patronActivo = computed(() => patrones.value.find((p) => p.tipo === tipoActivo.value));
const estadoAnillos = computed(() => ({ total: totalAnillos.value, cargando: cargandoAnillos.value, error: errorAnillos.value }));

function contador(tipo) {
  if (tipo === RESUMEN) return null;
  if (tipo === ANILLOS) return cargandoAnillos.value || errorAnillos.value ? null : totalAnillos.value;
  if (cargandoResumen.value || errorResumen.value) return null;
  return resumen.value?.por_tipo?.[tipo] ?? 0;
}

async function cargarPatrones() {
  cargandoPatrones.value = true;
  errorPatrones.value = "";
  const { ok, status, data } = await apiFetch(`/fraude/patrones?rol_solicitante=${encodeURIComponent(sesion.value.rol)}`);
  cargandoPatrones.value = false;
  if (!ok) {
    errorPatrones.value = mensajeErrorFraude(status, data, "No se pudo cargar la lista de patrones de fraude.");
    return;
  }
  patrones.value = data.patrones || [];
}

async function cargarResumen() {
  cargandoResumen.value = true;
  errorResumen.value = "";
  const { ok, status, data } = await apiFetch(`/fraude/resumen?rol_solicitante=${encodeURIComponent(sesion.value.rol)}`);
  cargandoResumen.value = false;
  if (!ok) {
    errorResumen.value = mensajeErrorFraude(status, data, "No se pudo cargar el resumen de fraude.");
    return;
  }
  resumen.value = data;
}

async function cargarAnillos() {
  cargandoAnillos.value = true;
  errorAnillos.value = "";
  const { ok, status, data } = await apiFetch(`/fraude/alertas?rol_solicitante=${encodeURIComponent(sesion.value.rol)}`);
  cargandoAnillos.value = false;
  if (!ok) {
    errorAnillos.value = mensajeErrorFraude(status, data, "No se pudieron cargar los anillos de reseñas.");
    return;
  }
  anillos.value = data.alertas || [];
  totalAnillos.value = data.total ?? anillos.value.length;
}

async function seleccionar(tipo, { enfocar = false } = {}) {
  if (!pestanas.value.some((p) => p.tipo === tipo)) return;
  const query = { ...route.query };
  if (tipo === RESUMEN) delete query.patron;
  else query.patron = tipo;
  await router.replace({ query });
  if (enfocar) {
    await nextTick();
    listaPestanas.value?.querySelector(`#pestana-${tipo}`)?.focus();
  }
}

function moverConTeclado(evento) {
  const indice = pestanas.value.findIndex((p) => p.tipo === tipoActivo.value);
  const ultimo = pestanas.value.length - 1;
  const destino = { ArrowRight: indice + 1, ArrowLeft: indice - 1, Home: 0, End: ultimo }[evento.key];
  if (destino === undefined) return;
  evento.preventDefault();
  const envuelto = destino > ultimo ? 0 : destino < 0 ? ultimo : destino;
  seleccionar(pestanas.value[envuelto].tipo, { enfocar: true });
}

function actualizarTodo() {
  if (errorPatrones.value) cargarPatrones();
  cargarResumen();
  cargarAnillos();
  recarga.value++;
}

onMounted(() => {
  cargarPatrones();
  cargarResumen();
  cargarAnillos();
});
</script>

<template>
  <div>
    <div class="flex flex-wrap justify-between items-start gap-4 mb-5">
      <div>
        <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mb-1">Alertas de fraude</h2>
        <p class="text-sm text-neutral-500 max-w-3xl">Reseñas sospechosas detectadas en el grafo de cuentas, productos, tiendas y direcciones (Neo4j).</p>
      </div>
      <button
        @click="actualizarTodo"
        class="px-4 py-2 border border-neutral-200 hover:border-neutral-400 text-neutral-700 font-semibold rounded-full text-sm transition"
      >Actualizar</button>
    </div>

    <div
      v-if="errorPatrones"
      role="alert"
      class="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
    >
      <span class="mt-0.5 w-5 h-5 shrink-0 rounded-full bg-red-600 text-white text-xs font-bold flex items-center justify-center" aria-hidden="true">!</span>
      <p class="flex-1">{{ errorPatrones }}</p>
      <button @click="cargarPatrones" class="shrink-0 text-xs font-semibold underline underline-offset-2 hover:text-red-600">Reintentar</button>
    </div>

    <p v-else-if="cargandoPatrones" class="text-sm text-neutral-500" aria-live="polite">Cargando...</p>

    <template v-else>
      <div
        ref="listaPestanas"
        role="tablist"
        aria-label="Tipos de fraude"
        class="flex gap-1 overflow-x-auto border-b border-neutral-200 mb-6"
        @keydown="moverConTeclado"
      >
        <button
          v-for="p in pestanas"
          :key="p.tipo"
          :id="`pestana-${p.tipo}`"
          role="tab"
          type="button"
          :aria-selected="tipoActivo === p.tipo"
          :aria-controls="`panel-${p.tipo}`"
          :tabindex="tipoActivo === p.tipo ? 0 : -1"
          @click="seleccionar(p.tipo)"
          :class="[
            '-mb-px shrink-0 inline-flex items-center gap-2 px-4 py-2.5 border-b-2 text-sm font-semibold whitespace-nowrap transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-600/50 rounded-t-lg',
            tipoActivo === p.tipo ? 'border-neutral-950 text-neutral-950' : 'border-transparent text-neutral-500 hover:text-neutral-800 hover:border-neutral-300',
          ]"
        >
          {{ p.nombre }}
          <span
            v-if="contador(p.tipo) !== null"
            :class="[
              'min-w-[1.5rem] px-1.5 py-0.5 rounded-full text-[11px] font-bold text-center',
              contador(p.tipo) > 0 ? 'bg-red-100 text-red-700' : 'bg-neutral-100 text-neutral-500',
            ]"
          >
            {{ contador(p.tipo) }}<span class="sr-only"> alertas</span>
          </span>
        </button>
      </div>

      <div
        :id="`panel-${tipoActivo}`"
        role="tabpanel"
        :aria-labelledby="`pestana-${tipoActivo}`"
        tabindex="0"
        class="focus:outline-none"
      >
        <KeepAlive>
          <ResumenFraude
            v-if="tipoActivo === RESUMEN"
            :key="RESUMEN"
            :patrones="patrones"
            :resumen="resumen"
            :cargando="cargandoResumen"
            :error="errorResumen"
            :anillos="estadoAnillos"
            @seleccionar="seleccionar"
            @reintentar="cargarResumen"
          />
          <AnillosResenas
            v-else-if="tipoActivo === ANILLOS"
            :key="ANILLOS"
            :alertas="anillos"
            :cargando="cargandoAnillos"
            :error="errorAnillos"
            @reintentar="cargarAnillos"
          />
          <AlertasPatron v-else-if="patronActivo" :key="patronActivo.tipo" :patron="patronActivo" :recarga="recarga" />
        </KeepAlive>

        <p v-if="patronActivo?.tipo === 'grupo_coordinado'" class="mt-6 text-xs text-neutral-500">
          La detección original de anillos de 3 cuentas sigue en su propia pestaña:
          <button type="button" @click="seleccionar(ANILLOS)" class="font-semibold text-accent-700 underline underline-offset-2">Anillos de reseñas (Entrega 2)</button>.
        </p>
      </div>
    </template>
  </div>
</template>
