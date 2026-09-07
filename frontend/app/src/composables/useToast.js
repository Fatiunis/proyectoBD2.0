import { ref } from "vue";

let siguienteId = 1;
const toasts = ref([]);

function toast(mensaje, tipo = "info") {
  const id = siguienteId++;
  toasts.value.push({ id, mensaje, tipo });
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }, 3800);
}

export function useToast() {
  return { toasts, toast };
}
