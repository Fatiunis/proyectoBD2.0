<script setup>
import { ref, computed, watch, onUnmounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";
import { useCarrito } from "../../composables/useCarrito";
import { formatoMinSeg } from "../../utils/tiempo";

const props = defineProps({
  productoId: { type: String, required: true },
  idVendedor: { type: Number, default: null },
  precioBase: { type: Number, default: null },
});

const { sesion } = useSesion();
const { toast } = useToast();
const { cargarCarrito } = useCarrito();

const oferta = ref(null);
const cargando = ref(true);
const terminada = ref(false);
const cantidadReserva = ref(1);
const reservando = ref(false);
const cantidadLimiteNueva = ref(10);
const duracionMinutosNueva = ref(60);
const precioOfertaNuevo = ref(null);
const creando = ref(false);
const finalizando = ref(false);
const finMs = ref(0);
const finReservaMs = ref(0);
const ahora = ref(Date.now());

let intervalo = null;
let ticks = 0;
let consultando = false;
let reservaVencidaAvisada = false;

const esComprador = computed(() => sesion.value?.rol === "comprador");
const puedeGestionar = computed(() => {
  if (sesion.value?.rol === "administrador") return true;
  return sesion.value?.rol === "vendedor" && props.idVendedor != null && sesion.value.id_usuario === props.idVendedor;
});
const porcentaje = computed(() => {
  if (!oferta.value || !oferta.value.cantidad_limite) return 0;
  return Math.round((oferta.value.stock_restante / oferta.value.cantidad_limite) * 100);
});
const segundosRestantes = computed(() => Math.max(0, Math.ceil((finMs.value - ahora.value) / 1000)));
const tiempoRestante = computed(() => {
  const s = segundosRestantes.value;
  const dosDigitos = (n) => String(n).padStart(2, "0");
  if (s >= 3600) {
    return `${Math.floor(s / 3600)} h ${dosDigitos(Math.floor((s % 3600) / 60))} min`;
  }
  return `${dosDigitos(Math.floor(s / 60))}:${dosDigitos(s % 60)}`;
});
const horaFin = computed(() => {
  if (!oferta.value) return "";
  // fecha_fin trae offset explícito, así que representa el instante exacto sin depender del reloj del cliente.
  const fin = oferta.value.fecha_fin ? new Date(oferta.value.fecha_fin) : new Date(finMs.value);
  return fin.toLocaleString("es-GT", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Guatemala" });
});

const reservaUsuario = computed(() => oferta.value?.reserva_usuario || null);
const segundosReserva = computed(() => Math.max(0, Math.ceil((finReservaMs.value - ahora.value) / 1000)));

function descuento(precioOferta, precioBase) {
  if (!precioOferta || !precioBase) return 0;
  return Math.round((1 - precioOferta / precioBase) * 100);
}

const descuentoOferta = computed(() =>
  oferta.value ? descuento(oferta.value.precio_oferta, oferta.value.precio_base) : 0
);

const precioNuevoValido = computed(() => {
  const p = Number(precioOfertaNuevo.value);
  return precioOfertaNuevo.value !== null && precioOfertaNuevo.value !== "" && p > 0 && (props.precioBase == null || p < props.precioBase);
});
const errorPrecioNuevo = computed(() => {
  if (precioOfertaNuevo.value === null || precioOfertaNuevo.value === "") return "";
  const p = Number(precioOfertaNuevo.value);
  if (!(p > 0)) return "Debe ser mayor que 0.";
  if (props.precioBase != null && p >= props.precioBase) return `Debe ser menor que el precio normal (Q${props.precioBase.toFixed(2)}).`;
  return "";
});
const descuentoNuevo = computed(() =>
  precioNuevoValido.value ? descuento(Number(precioOfertaNuevo.value), props.precioBase) : 0
);

function detenerTemporizador() {
  if (intervalo) {
    clearInterval(intervalo);
    intervalo = null;
  }
}

function tick() {
  ahora.value = Date.now();
  ticks += 1;
  const reservaVencida = reservaUsuario.value && segundosReserva.value <= 0;
  if (reservaVencida && !reservaVencidaAvisada) {
    reservaVencidaAvisada = true;
    cargarCarrito();
  }
  if (segundosRestantes.value <= 0 || reservaVencida || ticks % 3 === 0) {
    cargarOferta(props.productoId);
  }
}

function asegurarTemporizador() {
  if (intervalo) return;
  ticks = 0;
  intervalo = setInterval(tick, 1000);
}

async function cargarOferta(id) {
  if (consultando) return;
  consultando = true;
  const consulta = sesion.value ? `?id_usuario=${sesion.value.id_usuario}` : "";
  const { ok, status, data } = await apiFetch(`/ofertas/${id}${consulta}`);
  consultando = false;
  if (id !== props.productoId) return;

  if (ok) {
    oferta.value = data;
    terminada.value = false;
    ahora.value = Date.now();
    finMs.value = ahora.value + (data.segundos_restantes || 0) * 1000;
    if (data.reserva_usuario) {
      finReservaMs.value = ahora.value + (data.reserva_usuario.segundos_restantes || 0) * 1000;
      if (data.reserva_usuario.segundos_restantes > 0) reservaVencidaAvisada = false;
    }
    cantidadReserva.value = Math.min(Math.max(cantidadReserva.value || 1, 1), data.stock_restante || 1);
    asegurarTemporizador();
  } else if (status === 404) {
    if (oferta.value && segundosRestantes.value <= 3) terminada.value = true;
    oferta.value = null;
    detenerTemporizador();
  }
}

async function iniciar(id) {
  detenerTemporizador();
  oferta.value = null;
  terminada.value = false;
  precioOfertaNuevo.value = null;
  cargando.value = true;
  await cargarOferta(id);
  cargando.value = false;
}

watch(() => props.productoId, (id) => id && iniciar(id), { immediate: true });
watch(() => sesion.value?.id_usuario, () => props.productoId && cargarOferta(props.productoId));
onUnmounted(detenerTemporizador);

async function reservar() {
  if (!esComprador.value || !oferta.value || reservaUsuario.value) return;
  reservando.value = true;
  const { ok, data } = await apiFetch(`/ofertas/${props.productoId}/reservar`, {
    method: "POST",
    body: JSON.stringify({
      id_usuario: sesion.value.id_usuario,
      cantidad: cantidadReserva.value,
      rol_solicitante: "comprador",
    }),
  });
  reservando.value = false;

  if (ok) {
    toast("Reservado por 1 minuto: completa tu compra antes de que se libere", "success");
    await cargarCarrito();
  } else if (data?.error === "Stock insuficiente en la oferta") {
    toast("Ya no queda stock suficiente en la oferta", "error");
  } else {
    toast(data?.error || "No se pudo reservar en la oferta.", "error");
  }
  await cargarOferta(props.productoId);
}

async function crearOferta() {
  if (!precioNuevoValido.value) return;
  creando.value = true;
  const { ok, data } = await apiFetch("/ofertas", {
    method: "POST",
    body: JSON.stringify({
      producto_id: props.productoId,
      cantidad_limite: Number(cantidadLimiteNueva.value),
      duracion_minutos: Number(duracionMinutosNueva.value),
      precio_oferta: Number(precioOfertaNuevo.value),
      rol_solicitante: sesion.value.rol,
      id_usuario: sesion.value.id_usuario,
    }),
  });
  creando.value = false;

  if (ok) {
    toast(data?.mensaje || "Oferta relámpago iniciada", "success");
    precioOfertaNuevo.value = null;
  } else {
    toast(data?.error || "No se pudo crear la oferta.", "error");
  }
  await cargarOferta(props.productoId);
}

async function finalizarOferta() {
  finalizando.value = true;
  const { ok, data } = await apiFetch(`/ofertas/${props.productoId}`, {
    method: "DELETE",
    body: JSON.stringify({ rol_solicitante: sesion.value.rol, id_usuario: sesion.value.id_usuario }),
  });
  finalizando.value = false;

  if (ok) {
    toast(data?.mensaje || "Oferta finalizada", "success");
    oferta.value = null;
    detenerTemporizador();
  } else {
    toast(data?.error || "No se pudo finalizar la oferta.", "error");
  }
  await cargarOferta(props.productoId);
}
</script>

<template>
  <div v-if="!cargando && (oferta || puedeGestionar || terminada)" class="border-t border-neutral-200 pt-6 mt-2">
    <div v-if="oferta" class="space-y-3">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.15em] text-accent-700">Oferta relámpago</p>
          <div class="flex items-baseline flex-wrap gap-x-3 gap-y-1 mt-1">
            <p class="text-3xl font-extrabold text-accent-700 tracking-tight">Q{{ Number(oferta.precio_oferta).toFixed(2) }}</p>
            <p v-if="oferta.precio_base" class="text-sm text-neutral-400 line-through">Q{{ Number(oferta.precio_base).toFixed(2) }}</p>
            <span v-if="descuentoOferta > 0" class="px-2 py-0.5 rounded-full bg-accent text-white text-xs font-semibold">-{{ descuentoOferta }}%</span>
          </div>
        </div>
        <button
          v-if="puedeGestionar"
          @click="finalizarOferta"
          :disabled="finalizando"
          class="shrink-0 text-xs font-semibold text-neutral-400 hover:text-red-600 disabled:opacity-50 transition"
        >Finalizar oferta</button>
      </div>

      <p class="text-sm font-semibold text-neutral-950">
        Quedan {{ oferta.stock_restante }} de {{ oferta.cantidad_limite }} unidades
      </p>

      <div class="flex items-baseline justify-between gap-3 text-xs">
        <p class="font-semibold text-neutral-950">Termina en <span class="tabular-nums">{{ tiempoRestante }}</span></p>
        <p class="text-neutral-400">Finaliza el {{ horaFin }}</p>
      </div>

      <div class="h-2 rounded-full bg-neutral-100 overflow-hidden">
        <div class="h-full bg-accent transition-all" :style="{ width: porcentaje + '%' }"></div>
      </div>

      <div v-if="reservaUsuario" class="border border-accent/40 bg-accent-50 rounded-2xl px-4 py-3 text-sm text-neutral-950">
        Tienes <span class="font-semibold">{{ reservaUsuario.cantidad }}</span> reservadas · se liberan en
        <span class="font-semibold tabular-nums">{{ formatoMinSeg(segundosReserva) }}</span>
        <p class="text-xs text-neutral-500 mt-1">Ya están en tu carrito: confirma la compra antes de que se liberen.</p>
      </div>

      <div v-else class="flex items-center gap-3 pt-1">
        <input
          type="number" min="1" :max="oferta.stock_restante"
          v-model.number="cantidadReserva"
          class="w-20 border-0 border-b border-neutral-300 focus:border-accent bg-transparent text-sm px-0 py-1 focus:ring-0 outline-none transition"
        >
        <button
          @click="reservar"
          :disabled="!esComprador || reservando || oferta.stock_restante < 1"
          class="flex-1 py-2.5 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-40 disabled:hover:bg-neutral-950 text-white font-semibold rounded-full text-sm transition"
        >{{ reservando ? "Reservando..." : "Reservar y agregar al carrito" }}</button>
      </div>
      <p v-if="!sesion" class="text-xs text-neutral-400">Debes iniciar sesión como comprador para reservar en esta oferta.</p>
      <p v-else-if="!esComprador" class="text-xs text-neutral-400">Solo una cuenta con rol "comprador" puede reservar en una oferta.</p>
      <p v-else-if="!reservaUsuario" class="text-xs text-neutral-400">La reserva se aparta por 1 minuto al precio de oferta.</p>
    </div>

    <template v-else>
      <p v-if="terminada" class="text-sm font-semibold text-neutral-400" :class="{ 'mb-4': puedeGestionar }">La oferta relámpago terminó.</p>

      <form v-if="puedeGestionar" @submit.prevent="crearOferta" class="space-y-3">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Precio de oferta (Q)</label>
            <input
              type="number" min="0.01" step="0.01" :max="precioBase ?? undefined" required
              v-model.number="precioOfertaNuevo"
              class="w-28 border-0 border-b border-neutral-300 focus:border-accent bg-transparent text-sm px-0 py-1 focus:ring-0 outline-none transition"
            >
          </div>
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Cantidad límite</label>
            <input
              type="number" min="1"
              v-model.number="cantidadLimiteNueva"
              class="w-24 border-0 border-b border-neutral-300 focus:border-accent bg-transparent text-sm px-0 py-1 focus:ring-0 outline-none transition"
            >
          </div>
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Duración (minutos)</label>
            <input
              type="number" min="1" max="10080"
              v-model.number="duracionMinutosNueva"
              class="w-24 border-0 border-b border-neutral-300 focus:border-accent bg-transparent text-sm px-0 py-1 focus:ring-0 outline-none transition"
            >
          </div>
          <button
            type="submit"
            :disabled="creando || !precioNuevoValido"
            class="px-4 py-2.5 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 text-white font-semibold rounded-full text-sm transition"
          >{{ creando ? "Creando..." : "Iniciar oferta relámpago" }}</button>
        </div>
        <p v-if="errorPrecioNuevo" class="text-xs text-red-600">{{ errorPrecioNuevo }}</p>
        <p v-else-if="descuentoNuevo > 0" class="text-xs font-semibold text-accent-700">
          -{{ descuentoNuevo }}% sobre el precio normal (Q{{ precioBase.toFixed(2) }})
        </p>
        <p class="text-xs text-neutral-400">El precio no se puede cambiar una vez creada la oferta.</p>
      </form>
    </template>
  </div>
</template>
