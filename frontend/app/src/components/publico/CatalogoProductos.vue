<script setup>
import { ref, watch, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import FiltrosCatalogo from "./FiltrosCatalogo.vue";
import TarjetaProducto from "./TarjetaProducto.vue";
import Paginacion from "../comunes/Paginacion.vue";

const props = defineProps({
  busqueda: { type: String, default: "" },
});

const categoriasDisponibles = ref([]);
const categoriaSeleccionada = ref("");
const esquemaFiltrosActual = ref([]);
const valoresFiltros = ref({});
const productos = ref([]);
const cargado = ref(false);
const pagina = ref(1);
const total = ref(0);
const POR_PAGINA = 24;
const contenedorGrilla = ref(null);

async function cargarOpcionesCategoria() {
  const { data: categorias } = await apiFetch("/categorias");
  categoriasDisponibles.value = (categorias || []).filter((c) => (c.esquema_atributos || []).length > 0);
}

async function seleccionarCategoria(idCategoria) {
  categoriaSeleccionada.value = idCategoria;
  await cargarFiltrosAtributos(idCategoria);
  pagina.value = 1;
  cargarProductos();
}

async function cargarFiltrosAtributos(catId) {
  valoresFiltros.value = {};
  if (!catId) {
    esquemaFiltrosActual.value = [];
    return;
  }
  const { data: filtros } = await apiFetch(`/categorias/${catId}/filtros`);
  esquemaFiltrosActual.value = filtros || [];
}

function onCambiarFiltros(nuevosValores) {
  valoresFiltros.value = nuevosValores;
  pagina.value = 1;
  cargarProductos();
}

function limpiarFiltrosAtributos() {
  valoresFiltros.value = {};
  pagina.value = 1;
  cargarProductos();
}

async function cargarProductos() {
  const params = new URLSearchParams();
  if (categoriaSeleccionada.value) params.set("categoria_id", categoriaSeleccionada.value);
  if (props.busqueda) params.set("q", props.busqueda);
  params.set("pagina", pagina.value);
  params.set("por_pagina", POR_PAGINA);

  esquemaFiltrosActual.value.forEach((f) => {
    const valor = valoresFiltros.value[f.clave];
    if (f.tipo === "seleccion") {
      if (valor) params.set(`atributo_${f.clave}`, valor);
    } else if (valor) {
      if (valor.min) params.set(`atributo_${f.clave}_min`, valor.min);
      if (valor.max) params.set(`atributo_${f.clave}_max`, valor.max);
    }
  });

  const { data } = await apiFetch(`/productos?${params.toString()}`);
  productos.value = data.items || [];
  total.value = data.total || 0;
  cargado.value = true;
}

function onCambiarPagina(nueva) {
  pagina.value = nueva;
  cargarProductos();
  contenedorGrilla.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

watch(
  () => props.busqueda,
  () => {
    pagina.value = 1;
    cargarProductos();
  }
);

onMounted(async () => {
  await cargarOpcionesCategoria();
  await cargarProductos();
});
</script>

<template>
  <section class="lg:flex lg:items-start lg:gap-10">
    <aside class="lg:w-64 lg:shrink-0 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:pr-2 scrollbar-fina">
      <div class="pt-6 pb-6">
        <p class="text-xs font-semibold uppercase tracking-[0.2em] text-neutral-400 mb-3">Catálogo</p>
        <h2 class="text-4xl lg:text-5xl font-extrabold text-neutral-950 tracking-tighter leading-[0.95]">Productos</h2>
      </div>

      <nav class="flex lg:flex-col gap-1 border-b lg:border-b-0 border-neutral-200 mb-6 lg:mb-6 overflow-x-auto lg:overflow-visible">
        <button
          @click="seleccionarCategoria('')"
          :class="['px-4 lg:px-3 py-3 text-sm font-semibold whitespace-nowrap lg:whitespace-normal text-left transition border-b-2 lg:border-b-0 lg:border-l-2', categoriaSeleccionada === '' ? 'border-neutral-950 text-neutral-950' : 'border-transparent text-neutral-400 hover:text-neutral-700']"
        >Todas</button>
        <button
          v-for="c in categoriasDisponibles"
          :key="c.id_categoria"
          @click="seleccionarCategoria(c.id_categoria)"
          :class="['px-4 lg:px-3 py-3 text-sm font-semibold whitespace-nowrap lg:whitespace-normal text-left transition border-b-2 lg:border-b-0 lg:border-l-2', String(categoriaSeleccionada) === String(c.id_categoria) ? 'border-neutral-950 text-neutral-950' : 'border-transparent text-neutral-400 hover:text-neutral-700']"
        >{{ c.nombre }}</button>
      </nav>

      <FiltrosCatalogo :filtros="esquemaFiltrosActual" :valores="valoresFiltros" @cambiar="onCambiarFiltros" @limpiar="limpiarFiltrosAtributos" />
    </aside>

    <div class="flex-1 min-w-0" ref="contenedorGrilla">
      <div
        v-if="productos.length > 0"
        class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-6 gap-y-12 pt-6 lg:pt-0 pb-6 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:pr-2 scrollbar-fina"
      >
        <TarjetaProducto v-for="p in productos" :key="p._id" :producto="p" />
      </div>
      <div v-else-if="cargado" class="text-center py-24 text-neutral-400">
        <p class="text-sm font-medium">No se encontraron productos con estos filtros.</p>
      </div>
      <Paginacion :total="total" :pagina="pagina" :por-pagina="POR_PAGINA" @cambiar-pagina="onCambiarPagina" />
    </div>
  </section>
</template>
