<script setup>
import { ref, watch } from "vue";
import { apiFetch } from "../../services/api";
import { useToast } from "../../composables/useToast";
import { useCarrito } from "../../composables/useCarrito";
import ImagenProducto from "../ImagenProducto.vue";

const props = defineProps({
  productoId: { type: String, default: null },
});

const emit = defineEmits(["cerrar"]);

const { toast } = useToast();
const { agregar } = useCarrito();

const producto = ref(null);
const cantidad = ref(1);

watch(
  () => props.productoId,
  async (id) => {
    producto.value = null;
    if (!id) return;

    cantidad.value = 1;
    const { ok, data } = await apiFetch(`/productos/${id}`);
    if (!ok) {
      toast("No se pudo cargar el detalle del producto.", "error");
      emit("cerrar");
      return;
    }
    producto.value = data;
  }
);

function cerrar(e) {
  if (e && e.target !== e.currentTarget) return;
  emit("cerrar");
}

function agregarAlCarrito() {
  agregar(producto.value, cantidad.value);
  toast(`${producto.value.nombre} agregado al carrito.`, "success");
}
</script>

<template>
  <div
    v-if="producto"
    @click="cerrar"
    class="fixed inset-0 bg-neutral-950/70 backdrop-blur-sm flex items-center justify-center p-4 z-50"
  >
    <div class="bg-white rounded-3xl shadow-2xl max-w-lg w-full max-h-[85vh] overflow-y-auto relative" @click.stop>
      <button @click="emit('cerrar')" class="absolute top-4 right-4 w-8 h-8 rounded-full bg-white/90 hover:bg-neutral-100 text-neutral-500 flex items-center justify-center shadow-sm z-10" aria-label="Cerrar">✕</button>

      <div class="p-1"><ImagenProducto :producto="producto" altura-clase="h-56" /></div>
      <div class="p-7">
        <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-400">{{ producto.categoria.nombre }}</p>
        <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mt-1.5">{{ producto.nombre }}</h2>
        <p class="text-accent-700 font-bold text-2xl mt-1.5 mb-3">Q{{ producto.precio_base.toFixed(2) }}</p>
        <p class="text-sm text-neutral-600 leading-relaxed mb-5">{{ producto.descripcion }}</p>

        <div class="border-t border-neutral-200 pt-4 mb-4">
          <h4 class="text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-2">Atributos</h4>
          <div class="space-y-1">
            <template v-if="Object.keys(producto.atributos || {}).length > 0">
              <div v-for="[clave, valor] in Object.entries(producto.atributos)" :key="clave" class="text-sm text-neutral-600">
                <span class="font-semibold text-neutral-800">{{ clave.replaceAll("_", " ") }}:</span> {{ Array.isArray(valor) ? valor.join(", ") : valor }}
              </div>
            </template>
            <span v-else class="text-xs text-neutral-400">Sin atributos registrados</span>
          </div>
        </div>

        <div class="text-xs text-neutral-400 space-y-1 border-t border-neutral-200 pt-4 mb-5">
          <div><span class="font-medium text-neutral-600">SKU</span> · {{ producto.sku }}</div>
          <div><span class="font-medium text-neutral-600">ID</span> · <span class="font-mono">{{ producto._id }}</span></div>
          <div><span class="font-medium text-neutral-600">Stock disponible</span> · {{ producto.stock_disponible ?? "N/D" }}</div>
          <div><span class="font-medium text-neutral-600">Vendedor</span> · {{ producto.vendedor ? producto.vendedor.nombre_comercial : "N/D" }}</div>
        </div>

        <div class="border-t border-neutral-200 pt-5 flex items-center gap-3">
          <input
            type="number" min="1" :max="producto.stock_disponible || 1"
            v-model.number="cantidad"
            class="w-16 border-0 border-b border-neutral-300 focus:border-accent bg-transparent text-sm px-0 py-1 focus:ring-0 outline-none transition"
          >
          <button
            @click="agregarAlCarrito"
            :disabled="!producto.stock_disponible"
            class="flex-1 py-3 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-40 disabled:hover:bg-neutral-950 text-white font-semibold rounded-full text-sm transition"
          >{{ producto.stock_disponible ? "Agregar al carrito" : "Sin stock" }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
