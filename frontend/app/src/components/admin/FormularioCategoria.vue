<script setup>
import { ref } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";
import { useCategorias } from "../../composables/useCategorias";

const emit = defineEmits(["creada"]);

const { sesion } = useSesion();
const { toast } = useToast();
const { categorias } = useCategorias();

const nombre = ref("");
const descripcion = ref("");
const padre = ref("");
const filas = ref([{ clave: "", etiqueta: "", tipo: "texto" }]);

function agregarFila() {
  filas.value.push({ clave: "", etiqueta: "", tipo: "texto" });
}

function quitarFila(index) {
  filas.value.splice(index, 1);
}

async function crearCategoria() {
  const esquemaAtributos = filas.value
    .map((f) => ({ clave: f.clave.trim(), etiqueta: f.etiqueta.trim(), tipo: f.tipo }))
    .filter((f) => f.clave && f.etiqueta);

  const payload = {
    nombre: nombre.value,
    descripcion: descripcion.value,
    id_categoria_padre: padre.value || null,
    esquema_atributos: esquemaAtributos,
    rol_solicitante: sesion.value.rol,
  };

  const { ok, data } = await apiFetch("/categorias", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  if (ok) {
    toast(`Categoría "${payload.nombre}" creada con ${esquemaAtributos.length} atributo(s).`, "success");
    nombre.value = "";
    descripcion.value = "";
    padre.value = "";
    filas.value = [{ clave: "", etiqueta: "", tipo: "texto" }];
    emit("creada");
  } else {
    toast(data.error || "No se pudo crear la categoría.", "error");
  }
}
</script>

<template>
  <div>
    <form @submit.prevent="crearCategoria" class="space-y-5">
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Nombre</label>
          <input type="text" v-model="nombre" required placeholder="Ej. Zapatos" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Categoría padre (opcional)</label>
          <select v-model="padre" class="w-full border-0 border-b border-neutral-300 py-2 bg-transparent text-sm focus:ring-0 focus:border-accent outline-none transition">
            <option value="">Ninguna</option>
            <option v-for="c in categorias" :key="c.id_categoria" :value="c.id_categoria">{{ c.nombre }}</option>
          </select>
        </div>
      </div>
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Descripción</label>
        <input type="text" v-model="descripcion" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>

      <div class="p-4 bg-neutral-50 border border-neutral-200 rounded-xl">
        <div class="flex justify-between items-center mb-3">
          <h4 class="text-xs font-semibold uppercase tracking-wide text-neutral-400">Atributos del formulario de producto</h4>
          <button type="button" @click="agregarFila" class="text-xs font-semibold text-accent-700 hover:underline">+ Agregar atributo</button>
        </div>
        <div class="grid grid-cols-[1fr_1fr_110px_28px] gap-2 mb-2">
          <span class="text-[10px] font-bold uppercase text-neutral-400">Clave</span>
          <span class="text-[10px] font-bold uppercase text-neutral-400">Etiqueta visible</span>
          <span class="text-[10px] font-bold uppercase text-neutral-400">Tipo</span>
          <span></span>
        </div>
        <div class="space-y-2">
          <div v-for="(fila, index) in filas" :key="index" class="grid grid-cols-[1fr_1fr_110px_28px] gap-2 items-center">
            <input type="text" v-model="fila.clave" placeholder="ej. talla_zapato" class="min-w-0 border border-neutral-300 p-1.5 rounded-lg bg-white text-xs font-mono focus:ring-2 focus:ring-accent-600 focus:border-accent-600 outline-none transition">
            <input type="text" v-model="fila.etiqueta" placeholder="ej. Talla" class="min-w-0 border border-neutral-300 p-1.5 rounded-lg bg-white text-xs focus:ring-2 focus:ring-accent-600 focus:border-accent-600 outline-none transition">
            <select v-model="fila.tipo" class="min-w-0 border border-neutral-300 p-1.5 rounded-lg text-xs bg-white focus:ring-2 focus:ring-accent-600 focus:border-accent-600 outline-none transition">
              <option value="texto">Texto</option>
              <option value="numero">Número</option>
            </select>
            <button type="button" @click="quitarFila(index)" class="text-neutral-400 hover:text-red-600 text-sm font-bold transition" title="Quitar atributo">✕</button>
          </div>
        </div>
        <p class="text-[11px] text-neutral-400 mt-2">La "clave" se usa como nombre del campo en la base documental (sin espacios ni acentos, ej. <code>talla_zapato</code>).</p>
      </div>

      <button type="submit" class="w-full py-3 mt-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition">Crear categoría</button>
    </form>
  </div>
</template>
