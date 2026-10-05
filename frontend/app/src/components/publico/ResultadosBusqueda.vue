<script setup>
import { ref, reactive, computed, watch, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import TarjetaProducto from "./TarjetaProducto.vue";
import Paginacion from "../comunes/Paginacion.vue";

// Resultados de búsqueda (Entrega 3). Fuente: GET /api/busqueda (Elasticsearch):
// relevancia, tolerancia a errores, "¿quisiste decir?" y facetas calculadas con
// agregaciones del motor. Si el buscador no está disponible (503), se repite la
// búsqueda contra GET /api/productos?q= (índice de texto de MongoDB) y se avisa
// que es una búsqueda simplificada, sin facetas ni tolerancia a errores.

const props = defineProps({
  busqueda: { type: String, required: true },
});
const emit = defineEmits(["buscar"]);

const POR_PAGINA = 24;
const ORDENES = [
  { valor: "relevancia", etiqueta: "Más relevantes" },
  { valor: "precio_asc", etiqueta: "Precio: menor a mayor" },
  { valor: "precio_desc", etiqueta: "Precio: mayor a menor" },
];

const filtros = reactive({ categoria_id: null, marca: null, vendedor_id: null, precio: null });
const orden = ref("relevancia");
const pagina = ref(1);

const productos = ref([]);
const total = ref(0);
const facetas = ref({ categorias: [], marcas: [], tiendas: [], precios: [] });
const sugerencia = ref(null);
const motor = ref("elasticsearch");
const cargando = ref(false);
const error = ref("");
const contenedor = ref(null);
let consultaVigente = 0;

const hayFiltros = computed(() => Object.values(filtros).some((v) => v !== null));

function parametros() {
  const p = new URLSearchParams({ q: props.busqueda, orden: orden.value, pagina: pagina.value, por_pagina: POR_PAGINA });
  if (filtros.categoria_id !== null) p.set("categoria_id", filtros.categoria_id);
  if (filtros.marca !== null) p.set("marca", filtros.marca);
  if (filtros.vendedor_id !== null) p.set("vendedor_id", filtros.vendedor_id);
  if (filtros.precio) {
    if (filtros.precio.precio_min != null) p.set("precio_min", filtros.precio.precio_min);
    if (filtros.precio.precio_max != null) p.set("precio_max", filtros.precio.precio_max);
  }
  return p;
}

async function cargar() {
  const consulta = ++consultaVigente;
  cargando.value = true;
  error.value = "";
  const { ok, status, data } = await apiFetch(`/busqueda?${parametros()}`);
  if (consulta !== consultaVigente) return;

  if (ok) {
    productos.value = data.items;
    total.value = data.total;
    facetas.value = data.facetas;
    sugerencia.value = data.sugerencia;
    motor.value = "elasticsearch";
  } else if (status === 503) {
    await cargarRespaldo(consulta);
  } else {
    productos.value = [];
    total.value = 0;
    error.value = data?.error || "No se pudo completar la búsqueda.";
  }
  cargando.value = false;
}

async function cargarRespaldo(consulta) {
  const p = new URLSearchParams({ q: props.busqueda, pagina: pagina.value, por_pagina: POR_PAGINA });
  const { ok, data } = await apiFetch(`/productos?${p}`);
  if (consulta !== consultaVigente) return;
  motor.value = "mongo";
  sugerencia.value = null;
  facetas.value = { categorias: [], marcas: [], tiendas: [], precios: [] };
  productos.value = ok ? data.items : [];
  total.value = ok ? data.total : 0;
  if (!ok) error.value = data?.error || "No se pudo completar la búsqueda.";
}

function alternar(campo, valor) {
  filtros[campo] = filtros[campo] === valor ? null : valor;
  pagina.value = 1;
  cargar();
}

function alternarPrecio(rango) {
  const igual = filtros.precio && filtros.precio.rango === rango.rango;
  filtros.precio = igual ? null : rango;
  pagina.value = 1;
  cargar();
}

function limpiarFiltros() {
  Object.keys(filtros).forEach((k) => (filtros[k] = null));
  pagina.value = 1;
  cargar();
}

function cambiarOrden() {
  pagina.value = 1;
  cargar();
}

function onCambiarPagina(nueva) {
  pagina.value = nueva;
  cargar();
  contenedor.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

watch(
  () => props.busqueda,
  () => {
    Object.keys(filtros).forEach((k) => (filtros[k] = null));
    pagina.value = 1;
    cargar();
  }
);

onMounted(cargar);

function claseOpcion(activa) {
  return [
    "w-full flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg text-sm text-left transition",
    activa ? "bg-neutral-950 text-white font-semibold" : "text-neutral-600 hover:bg-neutral-100",
  ];
}
</script>

<template>
  <section class="lg:flex lg:items-start lg:gap-10" ref="contenedor">
    <aside class="lg:w-64 lg:shrink-0 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:pr-2 scrollbar-fina">
      <div class="pt-6 pb-6">
        <p class="text-xs font-semibold uppercase tracking-[0.2em] text-neutral-400 mb-3">Búsqueda</p>
        <h2 class="text-3xl lg:text-4xl font-extrabold text-neutral-950 tracking-tighter leading-[0.95] break-words">"{{ busqueda }}"</h2>
        <p class="text-sm text-neutral-500 mt-3">{{ total }} {{ total === 1 ? "resultado" : "resultados" }}</p>
      </div>

      <div v-if="motor === 'elasticsearch'" class="space-y-6 pb-6">
        <button v-if="hayFiltros" @click="limpiarFiltros" class="text-xs font-semibold text-accent hover:underline">Limpiar filtros</button>

        <div v-if="facetas.categorias.length">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Categoría</p>
          <button v-for="c in facetas.categorias" :key="c.id_categoria" @click="alternar('categoria_id', c.id_categoria)" :class="claseOpcion(filtros.categoria_id === c.id_categoria)">
            <span class="truncate">{{ c.nombre }}</span><span class="text-xs opacity-60">{{ c.cantidad }}</span>
          </button>
        </div>

        <div v-if="facetas.marcas.length">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Marca</p>
          <button v-for="m in facetas.marcas" :key="m.marca" @click="alternar('marca', m.marca)" :class="claseOpcion(filtros.marca === m.marca)">
            <span class="truncate">{{ m.marca }}</span><span class="text-xs opacity-60">{{ m.cantidad }}</span>
          </button>
        </div>

        <div v-if="facetas.precios.some((p) => p.cantidad > 0)">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Precio</p>
          <template v-for="p in facetas.precios" :key="p.rango">
            <button v-if="p.cantidad > 0" @click="alternarPrecio(p)" :class="claseOpcion(filtros.precio?.rango === p.rango)">
              <span>{{ p.rango }}</span><span class="text-xs opacity-60">{{ p.cantidad }}</span>
            </button>
          </template>
        </div>

        <div v-if="facetas.tiendas.length">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Tienda</p>
          <button v-for="t in facetas.tiendas" :key="t.id_vendedor" @click="alternar('vendedor_id', t.id_vendedor)" :class="claseOpcion(filtros.vendedor_id === t.id_vendedor)">
            <span class="truncate">{{ t.nombre }}</span><span class="text-xs opacity-60">{{ t.cantidad }}</span>
          </button>
        </div>
      </div>
    </aside>

    <div class="flex-1 min-w-0">
      <div v-if="motor === 'mongo'" class="mb-6 mt-6 lg:mt-0 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        El buscador avanzado no está disponible en este momento. Te mostramos una búsqueda simplificada:
        sin filtros por categoría o marca y sin corrección de errores de escritura.
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 mb-6 mt-6 lg:mt-0">
        <p v-if="sugerencia" class="text-sm text-neutral-600">
          ¿Quisiste decir
          <button @click="emit('buscar', sugerencia)" class="font-semibold text-accent hover:underline">{{ sugerencia }}</button>?
        </p>
        <span v-else></span>
        <select v-if="motor === 'elasticsearch'" v-model="orden" @change="cambiarOrden" class="border-0 border-b border-neutral-300 bg-transparent text-sm py-1 focus:ring-0 focus:border-neutral-950 outline-none cursor-pointer">
          <option v-for="o in ORDENES" :key="o.valor" :value="o.valor">{{ o.etiqueta }}</option>
        </select>
      </div>

      <div v-if="productos.length > 0" :class="['grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-6 gap-y-12 pb-6 transition-opacity', cargando ? 'opacity-50' : '']">
        <TarjetaProducto v-for="p in productos" :key="p._id" :producto="p" />
      </div>
      <div v-else-if="!cargando" class="text-center py-24 text-neutral-400">
        <p class="text-sm font-medium">{{ error || `No encontramos productos para "${busqueda}".` }}</p>
        <p v-if="!error && sugerencia" class="text-sm mt-2">Prueba con <button @click="emit('buscar', sugerencia)" class="font-semibold text-accent hover:underline">{{ sugerencia }}</button>.</p>
      </div>
      <Paginacion :total="total" :pagina="pagina" :por-pagina="POR_PAGINA" @cambiar-pagina="onCambiarPagina" />
    </div>
  </section>
</template>
