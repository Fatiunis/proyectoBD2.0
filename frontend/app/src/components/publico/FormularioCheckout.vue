<script setup>
import { ref, reactive, computed, watch, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";
import { useCarrito } from "../../composables/useCarrito";

const { sesion } = useSesion();
const { toast } = useToast();
const { items, cargarCarrito, limpiarLocal } = useCarrito();

const emit = defineEmits(["confirmado"]);

const direcciones = ref([]);
const cargandoDirecciones = ref(false);
const idDireccion = ref(null);
const metodoPago = ref("tarjeta_credito");
const enviando = ref(false);

// Clave de idempotencia (Entrega 3): una por intento de compra. Se conserva
// entre reintentos (si la primera respuesta no llegó, el backend reconoce la
// clave y devuelve el mismo pedido en vez de cobrar otra vez) y se renueva
// solo cuando la compra se confirma.
function nuevaClave() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
let claveIdempotencia = nuevaClave();

// Aviso persistente cuando la compra no se pudo confirmar (además del toast):
// dice qué pasó, si hubo cobro y si es seguro reintentar.
const aviso = ref(null); // { tipo: "error" | "incierto", mensaje }

// Fallas simuladas (solo si el backend tiene PERMITIR_FALLAS_SIMULADAS=1).
const puntosDeFalla = ref([]);
const fallaSimulada = ref("");
onMounted(async () => {
  const { ok, data } = await apiFetch("/checkout/fallas-simuladas");
  if (ok && data.habilitadas) puntosDeFalla.value = data.puntos;
});

const mostrarFormDireccion = ref(false);
const guardandoDireccion = ref(false);
const nuevaDireccion = reactive({
  direccion_linea1: "",
  direccion_linea2: "",
  ciudad: "",
  departamento_estado: "",
  codigo_postal: "",
});

const idComprador = computed(() =>
  sesion.value?.rol === "comprador" ? sesion.value.id_usuario : null
);

function textoDireccion(d) {
  return [d.direccion_linea1, d.direccion_linea2, d.ciudad, d.departamento_estado]
    .filter(Boolean)
    .join(", ");
}

function limpiarNuevaDireccion() {
  Object.keys(nuevaDireccion).forEach((k) => (nuevaDireccion[k] = ""));
}

async function cargarDirecciones(id) {
  direcciones.value = [];
  idDireccion.value = null;
  mostrarFormDireccion.value = false;
  if (!id) return;

  cargandoDirecciones.value = true;
  const { ok, data } = await apiFetch(`/usuarios/${id}/direcciones`);
  cargandoDirecciones.value = false;
  if (id !== idComprador.value) return;

  if (!ok || !Array.isArray(data)) {
    toast(data?.error || "No se pudieron cargar tus direcciones.", "error");
    return;
  }
  direcciones.value = data;
  const principal = data.find((d) => d.es_principal) || data[0];
  idDireccion.value = principal ? principal.id_direccion : null;
  mostrarFormDireccion.value = data.length === 0;
}

watch(idComprador, cargarDirecciones, { immediate: true });

async function guardarDireccion() {
  guardandoDireccion.value = true;
  const payload = { ...nuevaDireccion };
  if (!payload.direccion_linea2.trim()) delete payload.direccion_linea2;

  const { ok, data } = await apiFetch(`/usuarios/${idComprador.value}/direcciones`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  guardandoDireccion.value = false;

  if (!ok) {
    toast(data?.error || "No se pudo guardar la dirección.", "error");
    return;
  }
  direcciones.value.push(data);
  idDireccion.value = data.id_direccion;
  limpiarNuevaDireccion();
  mostrarFormDireccion.value = false;
  toast("Dirección agregada.", "success");
}

function cancelarNuevaDireccion() {
  limpiarNuevaDireccion();
  mostrarFormDireccion.value = false;
}

async function confirmarCompra() {
  enviando.value = true;
  aviso.value = null;
  const payload = {
    id_comprador: sesion.value.id_usuario,
    id_direccion: Number(idDireccion.value),
    metodo_pago: metodoPago.value,
    clave_idempotencia: claveIdempotencia,
  };
  if (fallaSimulada.value) payload.simular_falla = fallaSimulada.value;

  const { ok, status, data } = await apiFetch("/checkout", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  enviando.value = false;

  if (ok) {
    claveIdempotencia = nuevaClave();
    fallaSimulada.value = "";
    if (data.repetido) {
      toast(`Tu pedido #${data.id_pedido} ya estaba confirmado; no se cobró dos veces.`, "success");
    } else {
      toast(`Compra confirmada · Pedido #${data.id_pedido} · Referencia ${data.referencia_pago}`, "success");
    }
    if (data.sincronizacion_pendiente) {
      toast("Tu pedido está confirmado. El stock del catálogo y tu carrito pueden tardar unos segundos en actualizarse.", "info");
    }
    // Una línea normal y una de oferta del mismo producto se agrupan: la reseña es por producto.
    const porProducto = new Map();
    for (const { idProducto, nombre, imagenUrl, cantidad, idCategoria } of items.value) {
      const previo = porProducto.get(idProducto);
      if (previo) previo.cantidad += cantidad;
      else porProducto.set(idProducto, { idProducto, nombre, imagenUrl, cantidad, idCategoria });
    }
    limpiarLocal();
    emit("confirmado", {
      idPedido: data.id_pedido,
      referencia: data.referencia_pago,
      productos: [...porProducto.values()],
      sincronizacionPendiente: !!data.sincronizacion_pendiente,
    });
  } else if (data?.codigo === "CARRITO_VACIO" || data?.codigo === "RESERVA_OFERTA_EXPIRADA") {
    toast(data.error, "error");
    await cargarCarrito();
  } else if (status === 0) {
    // No llegó la respuesta: no sabemos si el pago se confirmó. Reintentar con
    // la MISMA clave es seguro (si ya se confirmó, el backend devuelve ese pedido).
    aviso.value = {
      tipo: "incierto",
      mensaje: "Perdimos la conexión mientras confirmábamos tu compra, así que no sabemos si se completó. "
        + "Puedes reintentar con tranquilidad: si ya se había confirmado, no se te cobrará dos veces.",
    };
  } else if (status === 503) {
    // Falla de infraestructura antes de confirmar: el backend garantiza que no hubo cobro.
    aviso.value = { tipo: "error", mensaje: data.error };
    toast(data.error, "error");
  } else {
    toast(data?.error || "No se pudo completar la compra.", "error");
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
    <div v-else class="space-y-5 mt-6 max-w-sm">
      <div>
        <label for="checkout-direccion" class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Dirección de envío</label>

        <p v-if="cargandoDirecciones" class="text-sm text-neutral-500 py-2">Cargando direcciones...</p>

        <template v-else>
          <select
            v-if="direcciones.length"
            id="checkout-direccion"
            v-model="idDireccion"
            class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent"
          >
            <option v-for="d in direcciones" :key="d.id_direccion" :value="d.id_direccion">
              {{ textoDireccion(d) }}{{ d.es_principal ? " (principal)" : "" }}
            </option>
          </select>
          <p v-else-if="!mostrarFormDireccion" class="text-sm text-neutral-500 py-2">
            No tienes direcciones registradas.
          </p>

          <button
            v-if="!mostrarFormDireccion"
            type="button"
            @click="mostrarFormDireccion = true"
            class="mt-2 text-xs font-semibold text-accent hover:underline"
          >
            {{ direcciones.length ? "Agregar otra dirección" : "Agregar dirección" }}
          </button>
        </template>
      </div>

      <form
        v-if="mostrarFormDireccion && !cargandoDirecciones"
        @submit.prevent="guardarDireccion"
        class="space-y-4 border border-neutral-200 rounded-2xl p-4"
      >
        <p class="text-xs font-semibold uppercase tracking-wide text-neutral-400">Nueva dirección</p>
        <input v-model="nuevaDireccion.direccion_linea1" required placeholder="Dirección (línea 1)" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        <input v-model="nuevaDireccion.direccion_linea2" placeholder="Apartamento, piso, referencia (opcional)" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        <div class="grid grid-cols-2 gap-4">
          <input v-model="nuevaDireccion.ciudad" required placeholder="Ciudad" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
          <input v-model="nuevaDireccion.departamento_estado" required placeholder="Departamento" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <input v-model="nuevaDireccion.codigo_postal" required placeholder="Código postal" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        <div class="flex gap-2 pt-1">
          <button type="submit" :disabled="guardandoDireccion" class="flex-1 py-2 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 text-white font-semibold rounded-full text-xs transition">
            {{ guardandoDireccion ? "Guardando..." : "Guardar dirección" }}
          </button>
          <button v-if="direcciones.length" type="button" @click="cancelarNuevaDireccion" class="px-4 py-2 border border-neutral-200 hover:bg-neutral-50 text-neutral-700 font-semibold rounded-full text-xs transition">
            Cancelar
          </button>
        </div>
      </form>

      <form @submit.prevent="confirmarCompra" class="space-y-5">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Método de pago</label>
          <select v-model="metodoPago" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
            <option value="tarjeta_credito">Tarjeta de crédito</option>
            <option value="tarjeta_debito">Tarjeta de débito</option>
            <option value="transferencia">Transferencia</option>
            <option value="paypal">PayPal</option>
          </select>
        </div>
        <div
          v-if="aviso"
          role="alert"
          :class="['rounded-2xl border px-4 py-3 text-sm', aviso.tipo === 'incierto' ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-red-200 bg-red-50 text-red-800']"
        >
          <p class="font-semibold mb-1">{{ aviso.tipo === "incierto" ? "No pudimos confirmar tu compra" : "Tu compra no se completó" }}</p>
          <p>{{ aviso.mensaje }}</p>
        </div>

        <div v-if="puntosDeFalla.length" class="rounded-2xl border border-dashed border-neutral-300 p-3">
          <label class="block text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Simular falla (solo desarrollo)</label>
          <select v-model="fallaSimulada" class="w-full border-0 border-b border-neutral-300 py-1.5 text-xs focus:ring-0 focus:border-accent outline-none transition bg-transparent">
            <option value="">Sin falla</option>
            <option v-for="p in puntosDeFalla" :key="p.punto" :value="p.punto">{{ p.descripcion }}</option>
          </select>
        </div>

        <button type="submit" :disabled="enviando || !idDireccion" class="w-full py-3 mt-2 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 text-white font-semibold rounded-full text-sm transition">
          {{ enviando ? "Procesando..." : aviso ? "Reintentar compra" : "Confirmar compra" }}
        </button>
      </form>
    </div>
  </div>
</template>
