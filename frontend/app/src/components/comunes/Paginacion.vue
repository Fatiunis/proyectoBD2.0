<script setup>
import { computed } from "vue";

const props = defineProps({
  total: { type: Number, default: 0 },
  pagina: { type: Number, default: 1 },
  porPagina: { type: Number, default: 24 },
});

const emit = defineEmits(["cambiar-pagina"]);

const totalPaginas = computed(() => Math.ceil(props.total / props.porPagina));

function irA(nueva) {
  if (nueva < 1 || nueva > totalPaginas.value || nueva === props.pagina) return;
  emit("cambiar-pagina", nueva);
}
</script>

<template>
  <div v-if="totalPaginas > 1" class="flex items-center justify-center gap-4 pt-4">
    <button
      @click="irA(pagina - 1)"
      :disabled="pagina === 1"
      class="px-4 py-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition disabled:opacity-40 disabled:cursor-not-allowed"
    >
      Anterior
    </button>
    <p class="text-sm text-neutral-500">Página {{ pagina }} de {{ totalPaginas }}</p>
    <button
      @click="irA(pagina + 1)"
      :disabled="pagina === totalPaginas || total === 0"
      class="px-4 py-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition disabled:opacity-40 disabled:cursor-not-allowed"
    >
      Siguiente
    </button>
  </div>
</template>
