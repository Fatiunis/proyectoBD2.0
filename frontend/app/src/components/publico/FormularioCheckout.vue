<script setup>
import { ref } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";
import { useCarrito } from "../../composables/useCarrito";

const { sesion } = useSesion();
const { toast } = useToast();
const { items, vaciar } = useCarrito();

const emit = defineEmits(["completado"]);

const idDireccion = ref("");
const metodoPago = ref("tarjeta_credito");
const referenciaPago = ref("");
const enviando = ref(false);

async function confirmarCompra() {
  enviando.value = true;
  const payload = {
    id_comprador: sesion.value.id_usuario,
    id_direccion: Number(idDireccion.value),
    metodo_pago: metodoPago.value,
    referencia_pago: referenciaPago.value,
    items: items.value.map((i) => ({ id_producto: i.idSqlOrigen, cantidad: i.cantidad })),
  };

  const { ok, data } = await apiFetch("/checkout", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  enviando.value = false;

  if (ok) {
    toast(data.mensaje, "success");
    vaciar();
    emit("completado");
  } else {
    toast(data.error || "No se pudo completar la compra.", "error");
  }
}
</script>

<template>
  <div class="border-t border-neutral-200 pt-8 mt-8">
    <h3 class="text-lg font-bold text-neutral-950 tracking-tight mb-1">Finalizar compra</h3>

    <div v-if="!sesion" class="text-sm text-neutral-500 mt-4">
      Debes iniciar sesión como comprador para completar el checkout.
    </div>
    <div v-else-if="sesion.rol !== 'comprador'" class="text-sm text-neutral-500 mt-4">
      Solo una cuenta con rol "comprador" puede completar una compra.
    </div>
    <form v-else @submit.prevent="confirmarCompra" class="space-y-5 mt-6 max-w-sm">
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">ID de dirección de envío</label>
        <input type="number" min="1" v-model="idDireccion" required placeholder="Ej: 1" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Método de pago</label>
        <select v-model="metodoPago" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
          <option value="tarjeta_credito">Tarjeta de crédito</option>
          <option value="tarjeta_debito">Tarjeta de débito</option>
          <option value="transferencia">Transferencia</option>
          <option value="paypal">PayPal</option>
        </select>
      </div>
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Referencia de pago</label>
        <input type="text" v-model="referenciaPago" required placeholder="Ej: número de autorización" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>
      <button type="submit" :disabled="enviando" class="w-full py-3 mt-2 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 text-white font-semibold rounded-full text-sm transition">
        {{ enviando ? "Procesando..." : "Confirmar compra" }}
      </button>
    </form>
  </div>
</template>
