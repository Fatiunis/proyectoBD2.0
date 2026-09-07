<script setup>
import MiniaturaCategoria from "../MiniaturaCategoria.vue";
import FormularioCheckout from "./FormularioCheckout.vue";
import { useCarrito } from "../../composables/useCarrito";

const emit = defineEmits(["completado"]);

const { items, actualizarCantidad, quitar, totalPagar } = useCarrito();
</script>

<template>
  <section class="pt-6 pb-16">
    <div class="pt-6 pb-8">
      <p class="text-xs font-semibold uppercase tracking-[0.2em] text-neutral-400 mb-3">Carrito</p>
      <h2 class="text-5xl sm:text-6xl font-extrabold text-neutral-950 tracking-tighter leading-[0.95]">Tu carrito</h2>
    </div>

    <div v-if="items.length === 0" class="text-center py-24 text-neutral-400">
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

      <FormularioCheckout @completado="emit('completado')" />
    </template>
  </section>
</template>
