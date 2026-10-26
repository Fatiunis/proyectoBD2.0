<script setup>
import { ref, computed, watch } from "vue";
import { RouterLink } from "vue-router";
import { apiFetch } from "../../services/api";
import ImagenProducto from "../ImagenProducto.vue";
import { ofertaActivaDe } from "../../composables/useOfertasFlash";

// Franja de productos por similitud semántica (entrega final, pgvector).
//   - productoId: "productos relacionados" de la página de detalle
//     (GET /api/productos/:id/relacionados).
//   - consulta: búsqueda por significado del texto libre
//     (GET /api/busqueda/semantica).
// Es una ayuda, no una función crítica: si el componente vectorial no
// responde (503 VECTORES_NO_DISPONIBLE) o no hay resultados, la franja
// simplemente no se muestra.

const props = defineProps({
  productoId: { type: String, default: null },
  consulta: { type: String, default: null },
  titulo: { type: String, required: true },
  subtitulo: { type: String, default: "" },
  limite: { type: Number, default: 6 },
});

const items = ref([]);
const cargando = ref(false);
let vigente = 0;

const ruta = computed(() => {
  if (props.productoId) return `/productos/${encodeURIComponent(props.productoId)}/relacionados?limite=${props.limite}`;
  if (props.consulta) return `/busqueda/semantica?${new URLSearchParams({ q: props.consulta, limite: props.limite })}`;
  return null;
});

async function cargar() {
  const n = ++vigente;
  items.value = [];
  if (!ruta.value) return;
  cargando.value = true;
  const { ok, data } = await apiFetch(ruta.value);
  if (n !== vigente) return;
  cargando.value = false;
  items.value = ok ? data.items || [] : [];
}

watch(ruta, cargar, { immediate: true });

function precio(p) {
  const oferta = ofertaActivaDe(p._id);
  return Number(oferta ? oferta.precio_oferta : p.precio_base).toFixed(2);
}

// La similitud coseno va de -1 a 1; en la práctica los productos parecidos
// quedan entre 0.5 y 1. Se muestra como porcentaje solo como orientación, y
// solo entre productos: la similitud frase→producto de la búsqueda queda en
// otra escala (0.3-0.6 aunque el resultado sea bueno) y se leería como mala.
function afinidad(p) {
  return Math.round(Math.max(0, Math.min(1, p.similitud)) * 100);
}
</script>

<template>
  <section v-if="items.length > 0" class="py-10" :aria-label="titulo">
    <div class="flex flex-wrap items-end justify-between gap-2 mb-6">
      <div>
        <h2 class="text-xl font-extrabold text-neutral-950 tracking-tight">{{ titulo }}</h2>
        <p v-if="subtitulo" class="text-sm text-neutral-500 mt-1">{{ subtitulo }}</p>
      </div>
    </div>
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-4 gap-y-8">
      <RouterLink
        v-for="p in items"
        :key="p._id"
        :to="`/producto/${p._id}`"
        class="block group min-w-0"
      >
        <div class="overflow-hidden rounded-2xl">
          <div class="transition-transform duration-500 group-hover:scale-[1.03]">
            <ImagenProducto :producto="p" altura-clase="h-36" />
          </div>
        </div>
        <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-400 mt-3 truncate">{{ p.categoria?.nombre }}</p>
        <h3 class="text-sm font-semibold text-neutral-950 leading-snug mt-0.5 line-clamp-2">{{ p.nombre }}</h3>
        <div class="flex items-baseline justify-between gap-2 mt-1">
          <span class="text-accent-700 font-bold text-sm">Q{{ precio(p) }}</span>
          <span v-if="productoId" class="text-[10px] text-neutral-400 tabular-nums" :title="`Similitud coseno ${p.similitud}`">{{ afinidad(p) }}% afín</span>
        </div>
      </RouterLink>
    </div>
  </section>
</template>
