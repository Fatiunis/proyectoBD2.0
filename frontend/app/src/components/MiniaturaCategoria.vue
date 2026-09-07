<script setup>
import { computed } from "vue";
import { categoriaVisual } from "../utils/categoriaVisual";

const props = defineProps({
  idCategoria: { type: [Number, String], default: null },
  alturaClase: { type: String, default: "h-56" },
});

const visual = computed(() => categoriaVisual(props.idCategoria));
</script>

<template>
  <div :class="[alturaClase, visual.fondo, 'w-full rounded-2xl flex items-center justify-center text-neutral-800/70']">
    <div class="w-10 h-10" v-html="visual.svg"></div>
  </div>
</template>
