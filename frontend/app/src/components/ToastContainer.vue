<script setup>
import { useToast } from "../composables/useToast";

const { toasts } = useToast();

const ESTILOS = {
  success: "bg-neutral-950",
  error: "bg-red-600",
  info: "bg-neutral-950",
};
</script>

<template>
  <div class="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-2">
    <TransitionGroup name="toast">
      <div
        v-for="t in toasts"
        :key="t.id"
        :class="[ESTILOS[t.tipo] || ESTILOS.info, 'text-white text-sm font-medium px-4 py-3 rounded-full shadow-lg max-w-xs']"
      >
        {{ t.mensaje }}
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(0.5rem);
}
</style>
