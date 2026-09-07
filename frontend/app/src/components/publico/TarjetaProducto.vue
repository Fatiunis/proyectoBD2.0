<script setup>
import ImagenProducto from "../ImagenProducto.vue";

const props = defineProps({
  producto: { type: Object, required: true },
});

const emit = defineEmits(["click"]);
</script>

<template>
  <div @click="emit('click', producto._id)" class="cursor-pointer group">
    <div class="overflow-hidden rounded-2xl">
      <div class="transition-transform duration-500 group-hover:scale-[1.03]">
        <ImagenProducto :producto="producto" />
      </div>
    </div>
    <div class="pt-4">
      <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-400">{{ producto.categoria.nombre }}</p>
      <h3 class="font-semibold text-neutral-950 text-[15px] mt-1 leading-snug">{{ producto.nombre }}</h3>
      <p class="text-accent-700 font-bold text-lg mt-1.5">Q{{ producto.precio_base.toFixed(2) }}</p>
      <div class="mt-2 space-y-0.5">
        <div v-for="[clave, valor] in Object.entries(producto.atributos || {})" :key="clave" class="text-xs text-neutral-500">
          <span class="font-medium text-neutral-700">{{ clave.replaceAll("_", " ") }}:</span> {{ Array.isArray(valor) ? valor.join(", ") : valor }}
        </div>
      </div>
    </div>
  </div>
</template>
