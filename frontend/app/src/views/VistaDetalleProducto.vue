<script setup>
import { ref, computed, watch } from "vue";
import { useRouter, RouterLink } from "vue-router";
import { apiFetch } from "../services/api";
import { useToast } from "../composables/useToast";
import { useCarrito } from "../composables/useCarrito";
import NavPublica from "../components/publico/NavPublica.vue";
import ImagenProducto from "../components/ImagenProducto.vue";

const props = defineProps({
  id: { type: String, required: true },
});

const router = useRouter();
const { toast } = useToast();
const { agregar } = useCarrito();

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

watch(() => props.id, (id) => id && cargarProducto(id), { immediate: true });

function agregarAlCarrito() {
  agregar(producto.value, cantidad.value);
  toast(`${producto.value.nombre} agregado al carrito.`, "success");
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
          <p class="text-accent-700 font-extrabold text-3xl mt-3 mb-5">Q{{ producto.precio_base.toFixed(2) }}</p>
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

          <div class="border-t border-neutral-200 pt-6 flex items-center gap-3">
            <input
              type="number" min="1" :max="producto.stock_disponible || 1"
              v-model.number="cantidad"
              class="w-20 border-0 border-b border-neutral-300 focus:border-accent bg-transparent text-sm px-0 py-1 focus:ring-0 outline-none transition"
            >
            <button
              @click="agregarAlCarrito"
              :disabled="!producto.stock_disponible"
              class="flex-1 py-3.5 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-40 disabled:hover:bg-neutral-950 text-white font-semibold rounded-full text-sm transition"
            >{{ producto.stock_disponible ? "Agregar al carrito" : "Sin stock" }}</button>
          </div>
        </div>
      </div>
    </main>

    <footer class="border-t border-neutral-200 bg-white text-neutral-400 text-xs py-6 text-center tracking-wide">
      TiendaYa · Portal E-Commerce con arquitectura políglota (PostgreSQL + MongoDB)
    </footer>
  </div>
</template>
