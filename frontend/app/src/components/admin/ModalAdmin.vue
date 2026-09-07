<script setup>
defineProps({
  abierto: { type: Boolean, default: false },
  titulo: { type: String, default: "" },
  anchoClase: { type: String, default: "max-w-lg" },
});

const emit = defineEmits(["cerrar"]);

function cerrarSiFondo(e) {
  if (e.target === e.currentTarget) emit("cerrar");
}
</script>

<template>
  <div
    v-if="abierto"
    @click="cerrarSiFondo"
    class="fixed inset-0 bg-neutral-950/70 backdrop-blur-sm flex items-center justify-center p-4 z-50"
  >
    <div :class="['bg-white rounded-3xl shadow-2xl w-full max-h-[85vh] overflow-y-auto scrollbar-fina relative', anchoClase]" @click.stop>
      <button @click="emit('cerrar')" class="absolute top-4 right-4 w-8 h-8 rounded-full bg-white/90 hover:bg-neutral-100 text-neutral-500 flex items-center justify-center shadow-sm z-10" aria-label="Cerrar">✕</button>
      <div class="p-7">
        <h3 v-if="titulo" class="text-lg font-bold text-neutral-950 tracking-tight mb-5">{{ titulo }}</h3>
        <slot />
      </div>
    </div>
  </div>
</template>
