<script setup>
import { ref, onMounted } from "vue";
import { RouterLink } from "vue-router";
import MiniaturaCategoria from "../MiniaturaCategoria.vue";
import ImagenProducto from "../ImagenProducto.vue";
import FormularioCheckout from "./FormularioCheckout.vue";
import { useCarrito } from "../../composables/useCarrito";

const emit = defineEmits(["completado"]);

const { items, cargarCarrito, actualizarCantidad, quitar, totalPagar } = useCarrito();

const compraConfirmada = ref(null);

function comoProducto(item) {
  return {
    _id: item.idProducto,
    nombre: item.nombre,
    categoria: { id_categoria: item.idCategoria },
    imagenes: item.imagenUrl ? [{ url: item.imagenUrl, es_portada: true }] : [],
  };
}

function seguirComprando() {
  compraConfirmada.value = null;
  emit("completado");
}

onMounted(cargarCarrito);
</script>

<template>
  <section class="pt-6 pb-16">
    <div class="pt-6 pb-8">
      <p class="text-xs font-semibold uppercase tracking-[0.2em] text-neutral-400 mb-3">Carrito</p>
      <h2 class="text-5xl sm:text-6xl font-extrabold text-neutral-950 tracking-tighter leading-[0.95]">Tu carrito</h2>
    </div>

    <div v-if="compraConfirmada" class="border border-neutral-200 rounded-2xl p-6 sm:p-8">
      <p class="text-xs font-semibold uppercase tracking-[0.2em] text-accent-700 mb-2">Compra confirmada</p>
      <h3 class="text-2xl font-extrabold text-neutral-950 tracking-tight">¡Gracias por tu compra!</h3>
      <div class="flex flex-wrap gap-x-8 gap-y-2 mt-4 text-sm">
        <p class="text-neutral-500">Pedido <span class="font-semibold text-neutral-950">#{{ compraConfirmada.idPedido }}</span></p>
        <p class="text-neutral-500">Referencia <span class="font-mono font-semibold text-neutral-950">{{ compraConfirmada.referencia }}</span></p>
      </div>

      <p class="text-xs font-semibold uppercase tracking-wide text-neutral-400 mt-8 mb-1">¿Qué te parecieron tus productos?</p>
      <div class="divide-y divide-neutral-200 border-t border-b border-neutral-200">
        <div v-for="item in compraConfirmada.productos" :key="item.idProducto" class="py-4 flex items-center gap-5">
          <div class="w-16 h-16 shrink-0">
            <ImagenProducto :producto="comoProducto(item)" altura-clase="h-16" />
          </div>
          <div class="flex-1 min-w-0">
            <h4 class="font-semibold text-neutral-950 text-sm truncate">{{ item.nombre }}</h4>
            <p class="text-xs text-neutral-400 mt-1">Cantidad: {{ item.cantidad }}</p>
          </div>
          <RouterLink
            :to="`/producto/${item.idProducto}#escribir-resena`"
            class="shrink-0 px-4 py-2 border border-neutral-300 hover:border-neutral-950 text-neutral-950 font-semibold rounded-full text-xs transition"
          >★ Dejar reseña</RouterLink>
        </div>
      </div>

      <div class="flex justify-end mt-6">
        <button @click="seguirComprando" class="px-6 py-3 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition">
          Seguir comprando
        </button>
      </div>
    </div>

    <div v-else-if="items.length === 0" class="text-center py-24 text-neutral-400">
      <p class="text-sm font-medium">Tu carrito está vacío.</p>
    </div>

    <template v-else>
      <div class="divide-y divide-neutral-200 border-t border-b border-neutral-200">
        <div v-for="item in items" :key="item.idProducto" class="py-5 flex items-center gap-5">
          <div class="w-20 h-20 shrink-0 rounded-xl overflow-hidden bg-neutral-100">
            <img v-if="item.imagenUrl" :src="item.imagenUrl" :alt="item.nombre" class="w-full h-full object-cover">
            <MiniaturaCategoria v-else :id-categoria="item.idCategoria" altura-clase="h-20" />
          </div>
          <div class="flex-1 min-w-0">
            <h3 class="font-semibold text-neutral-950 text-sm truncate">{{ item.nombre }}</h3>
            <p class="text-accent-700 font-bold text-sm mt-1">Q{{ item.precioBase.toFixed(2) }}</p>
          </div>
          <input
            type="number" min="1" :max="item.stockDisponible"
            :value="item.cantidad"
            @change="actualizarCantidad(item.idProducto, Number($event.target.value))"
            class="w-16 border-0 border-b border-neutral-300 focus:border-accent bg-transparent text-sm px-0 py-1 focus:ring-0 outline-none transition text-center"
          >
          <p class="w-24 text-right font-semibold text-neutral-950 text-sm">Q{{ (item.cantidad * item.precioBase).toFixed(2) }}</p>
          <button @click="quitar(item.idProducto)" class="w-8 h-8 flex items-center justify-center text-neutral-400 hover:text-red-600 transition" aria-label="Quitar">✕</button>
        </div>
      </div>

      <div class="flex justify-end mt-6">
        <p class="text-lg font-bold text-neutral-950">Total: <span class="text-accent-700">Q{{ totalPagar.toFixed(2) }}</span></p>
      </div>

      <FormularioCheckout @confirmado="compraConfirmada = $event" />
    </template>
  </section>
</template>
