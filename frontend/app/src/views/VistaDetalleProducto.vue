<script setup>
import { ref, computed, watch, onUnmounted } from "vue";
import { useRouter, RouterLink } from "vue-router";
import { apiFetch } from "../services/api";
import { useToast } from "../composables/useToast";
import { useCarrito } from "../composables/useCarrito";
import { useSesion } from "../composables/useSesion";
import NavPublica from "../components/publico/NavPublica.vue";
import ImagenProducto from "../components/ImagenProducto.vue";
import OfertaLimitada from "../components/publico/OfertaLimitada.vue";
import ResenasProducto from "../components/publico/ResenasProducto.vue";
import { porcentajeDescuento } from "../utils/descuento";
import { formatoCuentaRegresiva } from "../utils/tiempo";

const props = defineProps({
  id: { type: String, required: true },
});

const router = useRouter();
const { toast } = useToast();
const { agregar } = useCarrito();
const { sesion } = useSesion();

const producto = ref(null);
const cargando = ref(true);
const cantidad = ref(1);

const atributosVisibles = computed(() =>
  Object.entries(producto.value?.atributos || {}).filter(
    ([, valor]) => valor !== "" && valor !== null && valor !== undefined && !(typeof valor === "number" && Number.isNaN(valor))
  )
);

async function cargarProducto(id) {
  cargando.value = true;
  producto.value = null;
  onCambioOferta(null);
  const { ok, data } = await apiFetch(`/productos/${id}`);
  cargando.value = false;

  if (!ok) {
    toast("No se pudo cargar el producto.", "error");
    router.replace("/");
    return;
  }
  producto.value = data;
  cantidad.value = 1;
}

const oferta = ref(null);
const finOfertaMs = ref(0);
const ahora = ref(Date.now());
let relojOferta = null;

function detenerRelojOferta() {
  if (relojOferta) {
    clearInterval(relojOferta);
    relojOferta = null;
  }
}

function onCambioOferta(valor) {
  oferta.value = valor;
  ahora.value = Date.now();
  if (!valor) {
    detenerRelojOferta();
    return;
  }
  finOfertaMs.value = valor.segundos_restantes == null ? Infinity : ahora.value + valor.segundos_restantes * 1000;
  if (!relojOferta) relojOferta = setInterval(() => (ahora.value = Date.now()), 1000);
}

onUnmounted(detenerRelojOferta);

const segundosOferta = computed(() => Math.max(0, Math.ceil((finOfertaMs.value - ahora.value) / 1000)));
const ofertaVigente = computed(() => !!oferta.value && segundosOferta.value > 0);
const ofertaActiva = computed(() => ofertaVigente.value && oferta.value.stock_restante > 0);
const ofertaAgotada = computed(() => ofertaVigente.value && oferta.value.stock_restante <= 0);
const precioNormal = computed(() => Number(oferta.value?.precio_base ?? producto.value?.precio_base ?? 0));
const descuentoOferta = computed(() =>
  ofertaActiva.value ? porcentajeDescuento(oferta.value.precio_oferta, precioNormal.value, oferta.value.descuento_pct) : 0
);
const ahorroOferta = computed(() =>
  ofertaActiva.value ? Math.max(0, precioNormal.value - Number(oferta.value.precio_oferta)) : 0
);

function irAOferta() {
  const bloque = document.getElementById("oferta-flash");
  if (!bloque) return;
  bloque.scrollIntoView({ behavior: "smooth", block: "start" });
  bloque.focus({ preventScroll: true });
}

watch(() => props.id, (id) => id && cargarProducto(id), { immediate: true });

function agregarAlCarrito() {
  agregar(producto.value, cantidad.value);
  toast(`${producto.value.nombre} agregado al carrito.`, "success");
}

const esComprador = computed(() => sesion.value?.rol === "comprador");
const anclaResenas = computed(() => (esComprador.value ? "escribir-resena" : "resenas"));

// Scroll manual: un RouterLink con el mismo hash que ya está en la URL no dispara navegación.
function irAResenas() {
  document.getElementById(anclaResenas.value)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function onCambiarVista(vista) {
  router.push(vista === "catalogo" ? "/" : { path: "/", query: { vista } });
}

function onBuscar(texto) {
  router.push({ path: "/", query: { vista: "catalogo", q: texto } });
}
</script>

<template>
  <div class="bg-white text-neutral-950 min-h-screen flex flex-col">
    <NavPublica vista-actual="detalle" @cambiar-vista="onCambiarVista" @buscar="onBuscar" />

    <main class="max-w-5xl mx-auto px-6 lg:px-10 py-8 flex-grow w-full">
      <RouterLink to="/" class="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-950 transition mb-6">
        ← Volver al catálogo
      </RouterLink>

      <div v-if="cargando" class="py-24 text-center text-sm text-neutral-400">Cargando producto…</div>

      <div v-else-if="producto" class="grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-14">
        <div class="lg:sticky lg:top-24 lg:self-start">
          <ImagenProducto :producto="producto" altura-clase="h-[26rem] lg:h-[32rem]" />
        </div>

        <div>
          <p class="text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-400">{{ producto.categoria.nombre }}</p>
          <h1 class="text-3xl lg:text-4xl font-extrabold text-neutral-950 tracking-tight mt-2 leading-tight">{{ producto.nombre }}</h1>
          <div v-if="ofertaActiva" class="mt-4 rounded-2xl border border-accent/40 bg-accent-50 px-5 py-4" aria-label="Oferta flash activa">
            <div class="flex flex-wrap items-center gap-2">
              <span class="px-2.5 py-0.5 rounded-full bg-accent text-white text-xs font-semibold"><span aria-hidden="true">⚡</span> Oferta flash</span>
              <span v-if="descuentoOferta > 0" class="px-2.5 py-0.5 rounded-full bg-neutral-950 text-white text-xs font-semibold">-{{ descuentoOferta }}%</span>
              <span v-if="segundosOferta === Infinity" class="ml-auto text-xs font-semibold text-neutral-950">Sin límite de tiempo</span>
              <span v-else class="ml-auto text-xs font-semibold text-neutral-950">
                Termina en <span class="tabular-nums">{{ formatoCuentaRegresiva(segundosOferta) }}</span>
              </span>
            </div>
            <p class="text-accent-700 font-extrabold text-4xl tracking-tight mt-2">Q{{ Number(oferta.precio_oferta).toFixed(2) }}</p>
            <p class="text-sm text-neutral-500 mt-1">
              Precio normal <span class="line-through">Q{{ precioNormal.toFixed(2) }}</span>
              <span v-if="ahorroOferta > 0" class="font-semibold text-accent-700"> · Ahorras Q{{ ahorroOferta.toFixed(2) }}</span>
            </p>
            <p class="text-xs text-neutral-500 mt-1">Quedan {{ oferta.stock_restante }} de {{ oferta.cantidad_limite }} unidades a este precio</p>
            <button
              type="button"
              @click="irAOferta"
              class="mt-3 px-4 py-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition"
            >Reservar a precio de oferta</button>
          </div>
          <template v-else>
            <p class="text-accent-700 font-extrabold text-3xl mt-3">Q{{ producto.precio_base.toFixed(2) }}</p>
            <p v-if="ofertaAgotada" class="text-xs font-semibold text-neutral-400 mt-1">Oferta flash agotada</p>
          </template>
          <a
            :href="`#${anclaResenas}`"
            @click.prevent="irAResenas"
            class="inline-block text-xs font-semibold text-neutral-500 hover:text-accent-700 underline-offset-4 hover:underline transition mt-2 mb-5"
          >{{ esComprador ? "★ Escribir reseña" : "Ver reseñas" }}</a>
          <p class="text-[15px] text-neutral-600 leading-relaxed mb-7">{{ producto.descripcion }}</p>

          <div class="border-t border-neutral-200 pt-5 mb-6">
            <h2 class="text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-3">Especificaciones</h2>
            <dl v-if="atributosVisibles.length > 0" class="grid grid-cols-2 gap-x-6 gap-y-3">
              <template v-for="[clave, valor] in atributosVisibles" :key="clave">
                <dt class="text-xs text-neutral-400 self-start">{{ clave.replaceAll("_", " ") }}</dt>
                <dd class="text-sm text-neutral-800 font-medium self-start">{{ Array.isArray(valor) ? valor.join(", ") : valor }}</dd>
              </template>
            </dl>
            <p v-else class="text-xs text-neutral-400">Sin especificaciones registradas para este producto</p>
          </div>

          <div class="text-xs text-neutral-400 space-y-1 border-t border-neutral-200 pt-5 mb-7">
            <div><span class="font-medium text-neutral-600">SKU</span> · {{ producto.sku }}</div>
            <div><span class="font-medium text-neutral-600">ID</span> · <span class="font-mono">{{ producto._id }}</span></div>
            <div><span class="font-medium text-neutral-600">Stock disponible</span> · {{ producto.stock_disponible ?? "N/D" }}</div>
            <div><span class="font-medium text-neutral-600">Vendedor</span> · {{ producto.vendedor ? producto.vendedor.nombre_comercial : "N/D" }}</div>
          </div>

          <div id="oferta-flash" tabindex="-1" class="scroll-mt-24 outline-none not-empty:mb-6">
            <OfertaLimitada
              :producto-id="producto._id"
              :id-vendedor="producto.vendedor?.id_vendedor"
              :precio-base="producto.precio_base"
              @cambio-oferta="onCambioOferta"
            />
          </div>

          <div class="border-t border-neutral-200 pt-6">
            <p v-if="ofertaActiva" class="text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-3">
              Comprar a precio normal (Q{{ producto.precio_base.toFixed(2) }})
            </p>
            <div class="flex items-center gap-3">
              <input
                type="number" min="1" :max="producto.stock_disponible || 1"
                v-model.number="cantidad"
                aria-label="Cantidad"
                class="w-20 border-0 border-b border-neutral-300 focus:border-accent bg-transparent text-sm px-0 py-1 focus:ring-0 outline-none transition"
              >
              <button
                @click="agregarAlCarrito"
                :disabled="!producto.stock_disponible"
                :class="ofertaActiva
                  ? 'border border-neutral-300 hover:border-neutral-950 text-neutral-950 bg-white py-2.5'
                  : 'bg-neutral-950 hover:bg-neutral-800 disabled:hover:bg-neutral-950 text-white py-3.5'"
                class="flex-1 disabled:opacity-40 font-semibold rounded-full text-sm transition"
              >{{ producto.stock_disponible ? (ofertaActiva ? "Agregar al carrito a precio normal" : "Agregar al carrito") : "Sin stock" }}</button>
            </div>
          </div>
        </div>
      </div>

      <ResenasProducto v-if="producto" :producto-id="producto._id" class="border-t border-neutral-200" />
    </main>

    <footer class="border-t border-neutral-200 bg-white text-neutral-400 text-xs py-6 text-center tracking-wide">
      TiendaYa · Portal E-Commerce con arquitectura políglota (PostgreSQL + MongoDB)
    </footer>
  </div>
</template>
