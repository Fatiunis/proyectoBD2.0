<script setup>
import { computed } from "vue";
import { RouterLink } from "vue-router";
import ImagenProducto from "../ImagenProducto.vue";
import { ofertaActivaDe } from "../../composables/useOfertasFlash";
import { porcentajeDescuento } from "../../utils/descuento";

const props = defineProps({
  producto: { type: Object, required: true },
});

const atributosVisibles = computed(() =>
  Object.entries(props.producto.atributos || {}).filter(
    ([, valor]) => valor !== "" && valor !== null && valor !== undefined && !(typeof valor === "number" && Number.isNaN(valor))
  )
);

const oferta = computed(() => ofertaActivaDe(props.producto._id));
const descuento = computed(() =>
  oferta.value ? porcentajeDescuento(oferta.value.precio_oferta, oferta.value.precio_base, oferta.value.descuento_pct) : 0
);
</script>

<template>
  <RouterLink :to="`/producto/${producto._id}`" class="block cursor-pointer group">
    <div class="relative overflow-hidden rounded-2xl">
      <div class="transition-transform duration-500 group-hover:scale-[1.03]">
        <ImagenProducto :producto="producto" />
      </div>
      <span
        v-if="oferta && descuento > 0"
        class="absolute top-3 left-3 inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-accent text-white text-xs font-extrabold tracking-tight shadow-sm"
      >
        <svg viewBox="0 0 24 24" fill="currentColor" class="w-3 h-3" aria-hidden="true"><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12L13 2Z"/></svg>
        <span><span class="sr-only">Oferta flash: </span>-{{ descuento }}%</span>
      </span>
    </div>
    <div class="pt-4">
      <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-400">{{ producto.categoria.nombre }}</p>
      <h3 class="font-semibold text-neutral-950 text-[15px] mt-1 leading-snug">{{ producto.nombre }}</h3>
      <p v-if="oferta" class="flex items-baseline gap-2 mt-1.5">
        <span class="text-accent-700 font-bold text-lg">Q{{ Number(oferta.precio_oferta).toFixed(2) }}</span>
        <span class="text-sm text-neutral-400 line-through"><span class="sr-only">Antes </span>Q{{ producto.precio_base.toFixed(2) }}</span>
      </p>
      <p v-else class="text-accent-700 font-bold text-lg mt-1.5">Q{{ producto.precio_base.toFixed(2) }}</p>
      <div class="mt-2 space-y-0.5">
        <div v-for="[clave, valor] in atributosVisibles" :key="clave" class="text-xs text-neutral-500">
          <span class="font-medium text-neutral-700">{{ clave.replaceAll("_", " ") }}:</span> {{ Array.isArray(valor) ? valor.join(", ") : valor }}
        </div>
      </div>
    </div>
  </RouterLink>
</template>
