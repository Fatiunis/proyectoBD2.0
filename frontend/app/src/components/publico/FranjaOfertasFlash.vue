<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from "vue";
import { RouterLink } from "vue-router";
import ImagenProducto from "../ImagenProducto.vue";
import { useOfertasFlash, ofertaDisponible } from "../../composables/useOfertasFlash";
import { formatoCuentaRegresiva } from "../../utils/tiempo";
import { porcentajeDescuento } from "../../utils/descuento";

const MAXIMO = 12;
const CLAVE_CONTRAIDA = "tiendaya_franja_ofertas_contraida";

const emit = defineEmits(["ver-todas"]);

// Se pide la lista completa (no solo las visibles) para que las tarjetas del
// catálogo puedan marcar cualquier producto en oferta con la misma petición.
const { ofertas, listo, ahora } = useOfertasFlash({ limite: 100 });

const ordenadas = computed(() =>
  [...ofertas.value].sort(
    (a, b) =>
      ofertaDisponible(b, ahora.value) - ofertaDisponible(a, ahora.value) ||
      (a.finMs === b.finMs ? 0 : a.finMs < b.finMs ? -1 : 1)
  )
);
const visibles = computed(() => ordenadas.value.slice(0, MAXIMO));
const activas = computed(() => ofertas.value.filter((o) => ofertaDisponible(o, ahora.value)).length);
const textoActivas = computed(() => `${activas.value} ${activas.value === 1 ? "oferta flash activa" : "ofertas flash activas"}`);

function leerContraida() {
  try {
    return sessionStorage.getItem(CLAVE_CONTRAIDA) === "1";
  } catch {
    return false;
  }
}

const contraida = ref(leerContraida());

function alternar() {
  contraida.value = !contraida.value;
  try {
    sessionStorage.setItem(CLAVE_CONTRAIDA, contraida.value ? "1" : "0");
  } catch {
    // Sin sessionStorage (modo privado estricto) solo no se recuerda el estado.
  }
  if (!contraida.value) nextTick(actualizarFlechas);
}

function estado(o) {
  const sinFin = !Number.isFinite(o.finMs);
  const segundos = sinFin ? Infinity : Math.max(0, Math.ceil((o.finMs - ahora.value) / 1000));
  const termino = !sinFin && segundos <= 0;
  const quedan = Math.max(0, o.stock_restante ?? 0);
  return {
    disponible: !termino && quedan > 0,
    etiqueta: termino ? "Terminó" : quedan === 0 ? "Agotada" : null,
    tiempo: sinFin ? null : formatoCuentaRegresiva(segundos),
    urgente: !termino && segundos < 600,
    quedan,
    descuento: porcentajeDescuento(o.precio_oferta, o.precio_base, o.descuento_pct),
  };
}

function imagenDe(o) {
  return {
    _id: o.producto_id,
    nombre: o.nombre,
    categoria: o.categoria,
    imagenes: o.imagen_url ? [{ url: o.imagen_url, es_portada: true }] : [],
  };
}

function q(n) {
  return `Q${Number(n || 0).toFixed(2)}`;
}

const carril = ref(null);
const puedeIzquierda = ref(false);
const puedeDerecha = ref(false);

function actualizarFlechas() {
  const el = carril.value;
  if (!el) return;
  puedeIzquierda.value = el.scrollLeft > 4;
  puedeDerecha.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 4;
}

function desplazar(direccion) {
  carril.value?.scrollBy({ left: direccion * carril.value.clientWidth * 0.85, behavior: "smooth" });
}

watch(() => visibles.value.length, () => nextTick(actualizarFlechas));
onMounted(() => window.addEventListener("resize", actualizarFlechas));
onUnmounted(() => window.removeEventListener("resize", actualizarFlechas));

// Sobre el fondo oscuro el contorno verde no contrasta: se usa ámbar.
const claseFoco = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300";
</script>

<template>
  <section
    v-if="listo && activas > 0"
    class="mb-5 rounded-2xl border border-accent-900 bg-linear-to-r from-accent-900 via-accent-800 to-accent-900 text-white shadow-md shadow-accent-900/20"
    aria-labelledby="titulo-franja-ofertas"
  >
    <header class="flex items-center gap-2 px-3 py-2">
      <h2 id="titulo-franja-ofertas" class="min-w-0">
        <button
          type="button"
          @click="alternar"
          :aria-expanded="String(!contraida)"
          aria-controls="carril-franja-ofertas"
          :class="['flex items-center gap-2 min-w-0 max-w-full rounded-full pr-2 text-left', claseFoco]"
        >
          <span class="w-6 h-6 rounded-full bg-amber-400 flex items-center justify-center shrink-0 shadow-sm shadow-amber-400/30" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5 text-accent-900"><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12L13 2Z"/></svg>
          </span>
          <span class="text-sm font-extrabold tracking-tight text-white truncate">
            <template v-if="contraida">{{ textoActivas }}</template>
            <template v-else>Ofertas flash</template>
          </span>
          <span v-if="!contraida" class="hidden sm:inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-white/10 border border-white/15 text-[11px] font-semibold text-amber-200 shrink-0">
            <span class="relative flex w-1.5 h-1.5" aria-hidden="true">
              <span class="absolute inline-flex w-full h-full rounded-full bg-amber-400 opacity-75 animate-ping"></span>
              <span class="relative inline-flex w-1.5 h-1.5 rounded-full bg-amber-400"></span>
            </span>
            {{ activas }} {{ activas === 1 ? "activa" : "activas" }}
          </span>
          <svg
            viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            :class="['w-4 h-4 text-white/70 shrink-0 transition-transform', contraida ? '' : 'rotate-180']"
            aria-hidden="true"
          ><path d="m6 9 6 6 6-6"/></svg>
        </button>
      </h2>

      <div class="ml-auto flex items-center gap-1.5 shrink-0">
        <template v-if="!contraida">
          <button
            type="button"
            @click="desplazar(-1)"
            :disabled="!puedeIzquierda"
            aria-label="Ver ofertas anteriores"
            :class="['hidden md:flex w-7 h-7 rounded-full bg-white/10 border border-white/15 text-white hover:bg-white/20 hover:border-white/30 items-center justify-center transition disabled:opacity-30 disabled:hover:bg-white/10 disabled:hover:border-white/15', claseFoco]"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-3.5 h-3.5" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>
          </button>
          <button
            type="button"
            @click="desplazar(1)"
            :disabled="!puedeDerecha"
            aria-label="Ver más ofertas"
            :class="['hidden md:flex w-7 h-7 rounded-full bg-white/10 border border-white/15 text-white hover:bg-white/20 hover:border-white/30 items-center justify-center transition disabled:opacity-30 disabled:hover:bg-white/10 disabled:hover:border-white/15', claseFoco]"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-3.5 h-3.5" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>
          </button>
        </template>
        <button
          type="button"
          @click="emit('ver-todas')"
          :class="['px-3 py-1 rounded-full text-xs font-semibold text-amber-300 hover:bg-white/10 hover:text-amber-200 transition whitespace-nowrap', claseFoco]"
          :aria-label="contraida ? 'Ver todas las ofertas flash' : undefined"
        >{{ contraida ? "Ver" : "Ver todas" }} →</button>
      </div>
    </header>

    <ul
      v-show="!contraida"
      id="carril-franja-ofertas"
      ref="carril"
      @scroll.passive="actualizarFlechas"
      class="flex gap-2 overflow-x-auto snap-x snap-mandatory scroll-smooth px-3 pb-3 scroll-px-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      aria-label="Ofertas flash"
    >
      <li v-for="o in visibles" :key="o.producto_id" class="snap-start shrink-0 w-[15.5rem]">
        <RouterLink
          :to="`/producto/${o.producto_id}`"
          :aria-label="`${o.nombre}: oferta ${q(o.precio_oferta)}, antes ${q(o.precio_base)}, ${estado(o).etiqueta ? estado(o).etiqueta.toLowerCase() : `quedan ${estado(o).quedan}`}`"
          :class="[
            'flex items-center gap-2.5 h-full bg-white/10 rounded-xl border p-2 transition',
            estado(o).disponible ? 'border-white/10 hover:bg-white/15 hover:border-white/25' : 'border-white/10 opacity-55',
            claseFoco,
          ]"
        >
          <div :class="['relative w-14 h-14 shrink-0', estado(o).disponible ? '' : 'grayscale']">
            <ImagenProducto :producto="imagenDe(o)" altura-clase="h-14" class="rounded-lg!" />
            <span
              v-if="estado(o).descuento > 0"
              class="absolute -top-1 -left-1 px-1.5 py-px rounded-full bg-amber-400 text-accent-900 text-[10px] font-extrabold tracking-tight shadow-sm"
            >-{{ estado(o).descuento }}%</span>
          </div>
          <div class="min-w-0 flex-1" aria-hidden="true">
            <p class="text-[13px] font-semibold text-white leading-tight truncate" :title="o.nombre">{{ o.nombre }}</p>
            <p class="flex items-baseline gap-1.5 mt-0.5">
              <span :class="['text-sm font-extrabold tracking-tight', estado(o).disponible ? 'text-amber-300' : 'text-neutral-300']">{{ q(o.precio_oferta) }}</span>
              <span class="text-[11px] text-neutral-300 line-through">{{ q(o.precio_base) }}</span>
            </p>
            <p class="flex items-center gap-1.5 mt-0.5 text-[11px] text-neutral-300">
              <template v-if="estado(o).etiqueta">
                <span class="font-semibold text-neutral-200">{{ estado(o).etiqueta }}</span>
              </template>
              <template v-else>
                <span v-if="estado(o).tiempo" :class="['font-semibold tabular-nums', estado(o).urgente ? 'text-amber-300' : 'text-white']">{{ estado(o).tiempo }}</span>
                <span v-if="estado(o).tiempo" aria-hidden="true">·</span>
                <span>quedan {{ estado(o).quedan }}</span>
              </template>
            </p>
          </div>
        </RouterLink>
      </li>
    </ul>
  </section>
</template>
