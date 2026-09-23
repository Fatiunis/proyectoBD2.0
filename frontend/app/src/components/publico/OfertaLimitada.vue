<script setup>
import { ref, computed, watch, onUnmounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";

const props = defineProps({
  productoId: { type: String, required: true },
  idVendedor: { type: Number, default: null },
});

const { sesion } = useSesion();
const { toast } = useToast();

const oferta = ref(null);
const cargando = ref(true);
const terminada = ref(false);
const cantidadReserva = ref(1);
const reservando = ref(false);
const cantidadLimiteNueva = ref(10);
const duracionMinutosNueva = ref(60);
const creando = ref(false);
const finalizando = ref(false);
const finMs = ref(0);
const ahora = ref(Date.now());

let intervalo = null;
let ticks = 0;
let consultando = false;

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

function detenerTemporizador() {
  if (intervalo) {
    clearInterval(intervalo);
    intervalo = null;
  }
}

function tick() {
  ahora.value = Date.now();
  ticks += 1;
  if (segundosRestantes.value <= 0 || ticks % 3 === 0) {
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
  const { ok, status, data } = await apiFetch(`/ofertas/${id}`);
  consultando = false;
  if (id !== props.productoId) return;

  if (ok) {
    oferta.value = data;
    terminada.value = false;
    ahora.value = Date.now();
    finMs.value = ahora.value + (data.segundos_restantes || 0) * 1000;
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
  cargando.value = true;
  await cargarOferta(id);
  cargando.value = false;
}

watch(() => props.productoId, (id) => id && iniciar(id), { immediate: true });
onUnmounted(detenerTemporizador);

async function reservar() {
  if (!esComprador.value || !oferta.value) return;
  reservando.value = true;
  const { ok, data } = await apiFetch(`/ofertas/${props.productoId}/reservar`, {
    method: "POST",
    body: JSON.stringify({ id_usuario: sesion.value.id_usuario, cantidad: cantidadReserva.value }),
  });
  reservando.value = false;

  if (ok) {
    toast(data.mensaje || "Reserva confirmada", "success");
  } else if (data?.error === "Stock insuficiente en la oferta") {
    toast("Ya no queda stock suficiente en la oferta", "error");
  } else {
    toast(data?.error || "No se pudo reservar en la oferta.", "error");
  }
  await cargarOferta(props.productoId);
}

async function crearOferta() {
  creando.value = true;
  const { ok, data } = await apiFetch("/ofertas", {
    method: "POST",
    body: JSON.stringify({
      producto_id: props.productoId,
      cantidad_limite: Number(cantidadLimiteNueva.value),
      duracion_minutos: Number(duracionMinutosNueva.value),
      rol_solicitante: sesion.value.rol,
      id_usuario: sesion.value.id_usuario,
    }),
  });
  creando.value = false;

  if (ok) {
    toast(data?.mensaje || "Oferta relámpago iniciada", "success");
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
      <div class="flex items-center justify-between gap-3">
        <p class="text-sm font-semibold text-accent-700">
          Quedan {{ oferta.stock_restante }} de {{ oferta.cantidad_limite }} unidades — ¡oferta por tiempo limitado!
        </p>
        <button
          v-if="puedeGestionar"
          @click="finalizarOferta"
          :disabled="finalizando"
          class="shrink-0 text-xs font-semibold text-neutral-400 hover:text-red-600 disabled:opacity-50 transition"
        >Finalizar oferta</button>
      </div>

      <div class="flex items-baseline justify-between gap-3 text-xs">
        <p class="font-semibold text-neutral-950">Termina en <span class="tabular-nums">{{ tiempoRestante }}</span></p>
        <p class="text-neutral-400">Finaliza el {{ horaFin }}</p>
      </div>

      <div class="h-2 rounded-full bg-neutral-100 overflow-hidden">
        <div class="h-full bg-accent transition-all" :style="{ width: porcentaje + '%' }"></div>
      </div>

      <div class="flex items-center gap-3 pt-1">
        <input
          type="number" min="1" :max="oferta.stock_restante"
          v-model.number="cantidadReserva"
          class="w-20 border-0 border-b border-neutral-300 focus:border-accent bg-transparent text-sm px-0 py-1 focus:ring-0 outline-none transition"
        >
        <button
          @click="reservar"
          :disabled="!esComprador || reservando || oferta.stock_restante < 1"
          class="flex-1 py-2.5 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-40 disabled:hover:bg-neutral-950 text-white font-semibold rounded-full text-sm transition"
        >{{ reservando ? "Reservando..." : "Reservar" }}</button>
      </div>
      <p v-if="!sesion" class="text-xs text-neutral-400">Debes iniciar sesión como comprador para reservar en esta oferta.</p>
      <p v-else-if="!esComprador" class="text-xs text-neutral-400">Solo una cuenta con rol "comprador" puede reservar en una oferta.</p>
    </div>

    <template v-else>
      <p v-if="terminada" class="text-sm font-semibold text-neutral-400" :class="{ 'mb-4': puedeGestionar }">La oferta relámpago terminó.</p>

      <div v-if="puedeGestionar" class="flex flex-wrap items-end gap-3">
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
          @click="crearOferta"
          :disabled="creando"
          class="px-4 py-2.5 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 text-white font-semibold rounded-full text-sm transition"
        >{{ creando ? "Creando..." : "Iniciar oferta relámpago" }}</button>
      </div>
    </template>
  </div>
</template>
