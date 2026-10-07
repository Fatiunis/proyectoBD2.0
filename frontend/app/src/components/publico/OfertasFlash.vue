<script setup>
import { ref, computed, watch } from "vue";
import TarjetaOfertaPublica from "./TarjetaOfertaPublica.vue";
import { useOfertasFlash } from "../../composables/useOfertasFlash";
import { porcentajeDescuento } from "../../utils/descuento";

const emit = defineEmits(["ir-a-catalogo"]);

const { ofertas, listo, fallo, ahora, recargar } = useOfertasFlash({ limite: 100 });

const orden = ref("pronto");
const categoria = ref("");

const ORDENES = [
  { valor: "pronto", etiqueta: "Terminan pronto" },
  { valor: "descuento", etiqueta: "Mayor descuento" },
];

const categorias = computed(() => {
  const conteo = new Map();
  for (const o of ofertas.value) {
    if (!o.categoria) continue;
    const id = String(o.categoria.id_categoria);
    const actual = conteo.get(id) || { id, nombre: o.categoria.nombre, cantidad: 0 };
    actual.cantidad++;
    conteo.set(id, actual);
  }
  return [...conteo.values()].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
});

// Si tras una recarga ya no queda ninguna oferta de la categoría elegida, se
// vuelve a "Todas" en vez de dejar la grilla vacía sin explicación.
watch(categorias, (lista) => {
  if (categoria.value && !lista.some((c) => c.id === categoria.value)) categoria.value = "";
});

function disponible(o) {
  return (o.stock_restante ?? 0) > 0 && !(Number.isFinite(o.finMs) && o.finMs <= ahora.value);
}

const lista = computed(() => {
  const filtradas = categoria.value
    ? ofertas.value.filter((o) => String(o.categoria?.id_categoria) === categoria.value)
    : [...ofertas.value];
  const criterio =
    orden.value === "descuento"
      ? (a, b) =>
          porcentajeDescuento(b.precio_oferta, b.precio_base, b.descuento_pct) -
          porcentajeDescuento(a.precio_oferta, a.precio_base, a.descuento_pct)
      : (a, b) => (a.finMs === b.finMs ? 0 : a.finMs < b.finMs ? -1 : 1);
  // Las agotadas o terminadas siempre al final, sin importar el orden elegido.
  return filtradas.sort((a, b) => disponible(b) - disponible(a) || criterio(a, b));
});

const claseChip = (activo) => [
  "px-4 py-1.5 rounded-full text-sm font-semibold whitespace-nowrap border transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
  activo ? "bg-neutral-950 border-neutral-950 text-white" : "bg-white border-neutral-200 text-neutral-600 hover:border-neutral-400",
];
</script>

<template>
  <section aria-labelledby="titulo-ofertas-flash">
    <header class="pt-6 pb-8 flex flex-wrap items-end gap-6 justify-between">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.2em] text-neutral-400 mb-3 flex items-center gap-2">
          <svg viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5 text-accent" aria-hidden="true"><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12L13 2Z"/></svg>
          Por tiempo limitado
        </p>
        <h2 id="titulo-ofertas-flash" class="text-4xl lg:text-5xl font-extrabold text-neutral-950 tracking-tighter leading-[0.95]">Ofertas flash</h2>
        <p class="text-sm text-neutral-500 mt-3 max-w-xl">Precios especiales con cupo limitado. Entra a la oferta para reservar tus unidades antes de que se acaben.</p>
      </div>

      <div v-if="ofertas.length" class="inline-flex p-1 rounded-full bg-neutral-100" role="group" aria-label="Ordenar ofertas">
        <button
          v-for="o in ORDENES"
          :key="o.valor"
          type="button"
          @click="orden = o.valor"
          :aria-pressed="orden === o.valor"
          :class="[
            'px-4 py-1.5 rounded-full text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
            orden === o.valor ? 'bg-white text-neutral-950 shadow-sm' : 'text-neutral-500 hover:text-neutral-800',
          ]"
        >{{ o.etiqueta }}</button>
      </div>
    </header>

    <div v-if="categorias.length > 1" class="flex gap-2 overflow-x-auto pb-2 mb-6 scrollbar-fina" role="group" aria-label="Filtrar por categoría">
      <button type="button" @click="categoria = ''" :aria-pressed="categoria === ''" :class="claseChip(categoria === '')">
        Todas <span class="opacity-60 font-medium">{{ ofertas.length }}</span>
      </button>
      <button
        v-for="c in categorias"
        :key="c.id"
        type="button"
        @click="categoria = c.id"
        :aria-pressed="categoria === c.id"
        :class="claseChip(categoria === c.id)"
      >{{ c.nombre }} <span class="opacity-60 font-medium">{{ c.cantidad }}</span></button>
    </div>

    <div v-if="!listo" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6" aria-busy="true" aria-label="Cargando ofertas">
      <div v-for="n in 4" :key="n" class="rounded-2xl border border-neutral-200 overflow-hidden animate-pulse">
        <div class="h-44 bg-neutral-100"></div>
        <div class="p-4 space-y-3">
          <div class="h-3 w-1/3 bg-neutral-100 rounded"></div>
          <div class="h-4 w-3/4 bg-neutral-100 rounded"></div>
          <div class="h-6 w-1/2 bg-neutral-100 rounded"></div>
          <div class="h-9 bg-neutral-100 rounded-full"></div>
        </div>
      </div>
    </div>

    <div v-else-if="lista.length" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 pb-6">
      <TarjetaOfertaPublica v-for="o in lista" :key="o.producto_id" :oferta="o" :ahora="ahora" />
    </div>

    <div v-else class="text-center py-20 px-6 rounded-3xl border border-dashed border-neutral-200">
      <div class="w-14 h-14 mx-auto rounded-full bg-accent-50 flex items-center justify-center mb-4" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="currentColor" class="w-7 h-7 text-accent"><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12L13 2Z"/></svg>
      </div>
      <template v-if="fallo">
        <p class="text-lg font-semibold text-neutral-950">No pudimos cargar las ofertas</p>
        <p class="text-sm text-neutral-500 mt-1">Revisa tu conexión e intenta de nuevo.</p>
        <button type="button" @click="recargar" class="mt-6 px-5 py-2.5 bg-neutral-950 hover:bg-neutral-800 text-white rounded-full text-sm font-semibold transition">Reintentar</button>
      </template>
      <template v-else>
        <p class="text-lg font-semibold text-neutral-950">No hay ofertas flash en este momento</p>
        <p class="text-sm text-neutral-500 mt-1">Vuelve pronto: aparecen nuevas ofertas con frecuencia.</p>
        <button type="button" @click="emit('ir-a-catalogo')" class="mt-6 px-5 py-2.5 bg-neutral-950 hover:bg-neutral-800 text-white rounded-full text-sm font-semibold transition">Ver el catálogo</button>
      </template>
    </div>
  </section>
</template>
