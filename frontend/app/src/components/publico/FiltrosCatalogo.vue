<script setup>
const props = defineProps({
  filtros: { type: Array, required: true },
  valores: { type: Object, required: true },
});

const emit = defineEmits(["cambiar", "limpiar"]);

function actualizarSeleccion(clave, valor) {
  emit("cambiar", { ...props.valores, [clave]: valor });
}

function actualizarRango(clave, extremo, valor) {
  const actual = props.valores[clave] || {};
  emit("cambiar", { ...props.valores, [clave]: { ...actual, [extremo]: valor } });
}
</script>

<template>
  <div v-if="filtros.length > 0" class="flex flex-col gap-5 pb-6 mb-6 border-b border-neutral-200 lg:border-b-0">
    <div v-for="f in filtros" :key="f.clave" class="w-full">
      <template v-if="f.tipo === 'seleccion'">
        <label class="block text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">{{ f.clave.replaceAll("_", " ") }}</label>
        <select
          :value="valores[f.clave] || ''"
          @change="actualizarSeleccion(f.clave, $event.target.value)"
          class="w-full appearance-none border-0 border-b border-neutral-300 hover:border-neutral-950 bg-transparent text-sm px-0 py-1 focus:ring-0 focus:border-neutral-950 outline-none transition cursor-pointer"
        >
          <option value="">Todos</option>
          <option v-for="v in f.valores" :key="v" :value="v">{{ v }}</option>
        </select>
      </template>
      <template v-else>
        <label class="block text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">{{ f.clave.replaceAll("_", " ") }} ({{ f.min }}–{{ f.max }})</label>
        <div class="flex items-center gap-1.5">
          <input
            type="number" step="any" :placeholder="f.min"
            :value="(valores[f.clave] || {}).min || ''"
            @change="actualizarRango(f.clave, 'min', $event.target.value)"
            class="w-full min-w-0 border-0 border-b border-neutral-300 hover:border-neutral-950 bg-transparent text-sm px-0 py-1 focus:ring-0 focus:border-neutral-950 outline-none transition"
          >
          <span class="text-neutral-300 text-xs shrink-0">–</span>
          <input
            type="number" step="any" :placeholder="f.max"
            :value="(valores[f.clave] || {}).max || ''"
            @change="actualizarRango(f.clave, 'max', $event.target.value)"
            class="w-full min-w-0 border-0 border-b border-neutral-300 hover:border-neutral-950 bg-transparent text-sm px-0 py-1 focus:ring-0 focus:border-neutral-950 outline-none transition"
          >
        </div>
      </template>
    </div>
    <button @click="emit('limpiar')" class="text-xs font-semibold text-neutral-400 hover:text-neutral-900 transition self-start">Limpiar filtros</button>
  </div>
</template>
