<script setup>
import { ref, onMounted } from "vue";
import { useCategorias } from "../../composables/useCategorias";
import FormularioCategoria from "./FormularioCategoria.vue";
import ModalAdmin from "./ModalAdmin.vue";

const { categorias, cargarCategorias } = useCategorias();

const mostrarModalCrear = ref(false);

function onCategoriaCreada() {
  cargarCategorias();
  mostrarModalCrear.value = false;
}

onMounted(cargarCategorias);
</script>

<template>
  <div>
    <div class="flex justify-between items-start mb-6">
      <div>
        <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mb-1">Categorías</h2>
        <p class="text-sm text-neutral-500">Taxonomía del catálogo y atributos propios de cada categoría (PostgreSQL)</p>
      </div>
      <button @click="mostrarModalCrear = true" class="px-4 py-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition">+ Nueva categoría</button>
    </div>

    <div class="flex-1 min-w-0 bg-white p-5 rounded-2xl border border-neutral-200">
      <div class="overflow-x-auto lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto scrollbar-fina">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-white z-10">
            <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
              <th class="p-2.5">ID</th>
              <th class="p-2.5">Nombre</th>
              <th class="p-2.5">Descripción</th>
              <th class="p-2.5">Atributos configurados</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in categorias" :key="c.id_categoria" class="border-b border-neutral-100 hover:bg-neutral-50/80 transition align-top">
              <td class="p-2.5 text-neutral-400 font-mono text-xs">{{ c.id_categoria }}</td>
              <td class="p-2.5 font-medium text-neutral-950">{{ c.nombre }}</td>
              <td class="p-2.5 text-neutral-500 text-xs">{{ c.descripcion || "—" }}</td>
              <td class="p-2.5">
                <span v-if="(c.esquema_atributos || []).length === 0" class="text-xs text-neutral-400">Sin atributos</span>
                <span
                  v-for="a in c.esquema_atributos"
                  :key="a.clave"
                  class="inline-block mr-1 mb-1 px-1.5 py-0.5 bg-accent-50 text-accent-700 rounded-full text-[10px] font-semibold"
                >{{ a.etiqueta }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <ModalAdmin :abierto="mostrarModalCrear" titulo="Crear nueva categoría" ancho-clase="max-w-2xl" @cerrar="mostrarModalCrear = false">
      <FormularioCategoria @creada="onCategoriaCreada" />
    </ModalAdmin>
  </div>
</template>
