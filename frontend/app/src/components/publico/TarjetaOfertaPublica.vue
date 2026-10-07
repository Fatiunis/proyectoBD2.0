<script setup>
import { computed } from "vue";
import { RouterLink } from "vue-router";
import ImagenProducto from "../ImagenProducto.vue";
import { formatoCuentaRegresiva } from "../../utils/tiempo";
import { porcentajeDescuento } from "../../utils/descuento";

const props = defineProps({
  oferta: { type: Object, required: true },
  ahora: { type: Number, required: true },
});

const productoImagen = computed(() => ({
  _id: props.oferta.producto_id,
  nombre: props.oferta.nombre,
  categoria: props.oferta.categoria,
  imagenes: props.oferta.imagen_url ? [{ url: props.oferta.imagen_url, es_portada: true }] : [],
}));

const sinFin = computed(() => !Number.isFinite(props.oferta.finMs));
const segundos = computed(() => (sinFin.value ? Infinity : Math.max(0, Math.ceil((props.oferta.finMs - props.ahora) / 1000))));
const termino = computed(() => !sinFin.value && segundos.value <= 0);
const urgente = computed(() => !termino.value && segundos.value < 600);

const limite = computed(() => props.oferta.cantidad_limite || 0);
const quedan = computed(() => Math.max(0, props.oferta.stock_restante ?? 0));
const agotada = computed(() => !termino.value && quedan.value === 0);
const activa = computed(() => !termino.value && !agotada.value);
const pctQuedan = computed(() => (limite.value ? Math.min(100, (quedan.value / limite.value) * 100) : 0));
const ultimas = computed(() => activa.value && limite.value > 0 && quedan.value / limite.value < 0.1);

const descuento = computed(() =>
  porcentajeDescuento(props.oferta.precio_oferta, props.oferta.precio_base, props.oferta.descuento_pct)
);
const ahorro = computed(() => Math.max(0, Number(props.oferta.precio_base) - Number(props.oferta.precio_oferta)));

const textoTiempo = computed(() => {
  if (termino.value) return "Terminó";
  return sinFin.value ? "Sin límite de tiempo" : formatoCuentaRegresiva(segundos.value);
});

const detalle = computed(() => `/producto/${props.oferta.producto_id}`);

function q(n) {
  return `Q${Number(n || 0).toFixed(2)}`;
}
</script>

<template>
  <article
    :class="[
      'group relative bg-white rounded-2xl border flex flex-col overflow-hidden h-full transition',
      activa ? 'border-neutral-200 hover:border-neutral-300 hover:shadow-lg hover:shadow-neutral-950/5' : 'border-neutral-200',
      urgente && activa ? 'ring-2 ring-amber-300/70 border-amber-300' : '',
    ]"
  >
    <RouterLink :to="detalle" tabindex="-1" aria-hidden="true" :class="['relative block overflow-hidden', activa ? '' : 'opacity-50 grayscale']">
      <div class="transition-transform duration-500 group-hover:scale-[1.03]">
        <ImagenProducto :producto="productoImagen" altura-clase="h-44" class="rounded-none!" />
      </div>
      <span
        v-if="descuento > 0"
        class="absolute top-3 left-3 px-2.5 py-1 rounded-full bg-accent text-white text-xs font-extrabold tracking-tight shadow-sm"
      >-{{ descuento }}%</span>
    </RouterLink>

    <span
      v-if="termino || agotada"
      class="absolute top-3 right-3 px-2.5 py-1 rounded-full bg-neutral-950 text-white text-[11px] font-semibold"
    >{{ termino ? "Terminó" : "Agotada" }}</span>
    <span
      v-else-if="ultimas"
      class="absolute top-3 right-3 px-2.5 py-1 rounded-full bg-amber-400 text-amber-950 text-[11px] font-bold"
    >¡Últimas unidades!</span>

    <div class="p-4 flex flex-col gap-3 flex-1">
      <div>
        <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-400 truncate">
          {{ oferta.categoria?.nombre || "Oferta" }}<template v-if="oferta.vendedor?.nombre"> · {{ oferta.vendedor.nombre }}</template>
        </p>
        <h3 class="mt-1 font-semibold text-[15px] leading-snug line-clamp-2 min-h-[2.6rem]" :title="oferta.nombre">
          <RouterLink :to="detalle" class="text-neutral-950 hover:underline focus-visible:outline-none focus-visible:underline">{{ oferta.nombre }}</RouterLink>
        </h3>
      </div>

      <div>
        <div class="flex items-baseline gap-2 flex-wrap">
          <p :class="['text-2xl font-extrabold tracking-tight', activa ? 'text-accent-700' : 'text-neutral-400']">{{ q(oferta.precio_oferta) }}</p>
          <p class="text-sm text-neutral-400 line-through">{{ q(oferta.precio_base) }}</p>
        </div>
        <p v-if="ahorro > 0 && activa" class="text-xs font-semibold text-accent-700 mt-0.5">Ahorras {{ q(ahorro) }}</p>
      </div>

      <div
        :class="[
          'rounded-xl px-3 py-2 flex items-center gap-2',
          !activa ? 'bg-neutral-100 text-neutral-500' : urgente ? 'bg-amber-50 text-amber-800' : 'bg-neutral-50 text-neutral-700',
        ]"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="['w-4 h-4 shrink-0', urgente && activa ? 'animate-pulse' : '']" aria-hidden="true"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2"/><path d="M9 2h6"/></svg>
        <p class="text-[11px] font-semibold uppercase tracking-wider">{{ termino ? "Estado" : sinFin ? "Vigencia" : "Termina en" }}</p>
        <p class="ml-auto text-sm font-extrabold tabular-nums tracking-tight">{{ textoTiempo }}</p>
      </div>

      <div>
        <div class="flex items-baseline justify-between mb-1.5">
          <p class="text-xs font-semibold text-neutral-700">Quedan {{ quedan }} de {{ limite }}</p>
          <p v-if="activa" class="text-[11px] text-neutral-400">{{ Math.round(pctQuedan) }}%</p>
        </div>
        <div
          class="h-2 rounded-full bg-neutral-100 overflow-hidden"
          role="progressbar"
          :aria-valuenow="quedan"
          aria-valuemin="0"
          :aria-valuemax="limite"
          :aria-label="`Quedan ${quedan} de ${limite} unidades en oferta`"
        >
          <div
            :class="['h-full rounded-full transition-all duration-500', ultimas ? 'bg-amber-500' : 'bg-accent']"
            :style="{ width: pctQuedan + '%' }"
          ></div>
        </div>
      </div>

      <RouterLink
        v-if="activa"
        :to="detalle"
        class="mt-auto text-center px-4 py-2.5 bg-neutral-950 hover:bg-neutral-800 text-white rounded-full text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        :aria-label="`Ver oferta de ${oferta.nombre}`"
      >Ver oferta</RouterLink>
      <p v-else class="mt-auto text-center px-4 py-2.5 rounded-full bg-neutral-100 text-neutral-500 text-sm font-semibold">
        {{ termino ? "Oferta terminada" : "Sin unidades en oferta" }}
      </p>
    </div>
  </article>
</template>
