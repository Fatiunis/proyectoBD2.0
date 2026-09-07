import { ref } from "vue";
import { apiFetch } from "../services/api";

const categorias = ref([]);
const cargado = ref(false);

async function cargarCategorias() {
  const { data } = await apiFetch("/categorias");
  categorias.value = data || [];
  cargado.value = true;
}

export function useCategorias() {
  return { categorias, cargado, cargarCategorias };
}
