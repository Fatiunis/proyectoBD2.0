<script setup>
import { ref, computed, watch } from "vue";
import MiniaturaCategoria from "./MiniaturaCategoria.vue";

const props = defineProps({
  producto: { type: Object, required: true },
  alturaClase: { type: String, default: "h-56" },
});

const hayError = ref(false);
watch(() => props.producto?._id, () => (hayError.value = false));

const portada = computed(() => {
  const imagenes = props.producto?.imagenes || [];
  return imagenes.find((img) => img.es_portada) || imagenes[0];
});

const mostrarImagen = computed(() => !!portada.value?.url && !hayError.value);
</script>

<template>
  <MiniaturaCategoria
    v-if="!mostrarImagen"
    :id-categoria="producto.categoria?.id_categoria"
    :altura-clase="alturaClase"
  />
  <div v-else :class="[alturaClase, 'w-full rounded-2xl overflow-hidden bg-neutral-100']">
    <img
      :src="portada.url"
      :alt="producto.nombre"
      loading="lazy"
      class="w-full h-full object-cover"
      @error="hayError = true"
    />
  </div>
</template>
