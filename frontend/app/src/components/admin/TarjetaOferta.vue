<script setup>
import { ref, computed, watch } from "vue";
import { RouterLink } from "vue-router";
import ImagenProducto from "../ImagenProducto.vue";
import { formatoCuentaRegresiva } from "../../utils/tiempo";
import { porcentajeDescuento } from "../../utils/descuento";

const props = defineProps({
  oferta: { type: Object, required: true },
  producto: { type: Object, default: null },
  ahora: { type: Number, required: true },
  finalizando: { type: Boolean, default: false },
});
const emit = defineEmits(["finalizar", "vencida"]);

const confirmando = ref(false);

const segundos = computed(() => Math.max(0, Math.ceil((props.oferta.finMs - props.ahora) / 1000)));
const vencida = computed(() => segundos.value <= 0);

watch(vencida, (v) => {
  if (v) {
    confirmando.value = false;
    emit("vencida");
  }
});

const productoImagen = computed(() => ({
  _id: props.oferta.producto_id,
  nombre: props.oferta.nombre,
  categoria: props.producto?.categoria || null,
  imagenes: props.oferta.imagen_url
    ? [{ url: props.oferta.imagen_url, es_portada: true }]
    : props.producto?.imagenes || [],
}));

const limite = computed(() => props.oferta.cantidad_limite || 0);
const vendidas = computed(() => props.oferta.unidades_vendidas || 0);
const reservadas = computed(() => props.oferta.unidades_reservadas || 0);
const disponibles = computed(() => Math.max(0, props.oferta.stock_restante ?? limite.value - vendidas.value - reservadas.value));

function pct(n) {
  return limite.value ? Math.min(100, (n / limite.value) * 100) : 0;
}

const descuento = computed(() =>
  porcentajeDescuento(props.oferta.precio_oferta, props.oferta.precio_base, props.oferta.descuento_pct)
);

const pocoTiempo = computed(() => !vencida.value && segundos.value < 600);
const pocoCupo = computed(() => !vencida.value && limite.value > 0 && disponibles.value / limite.value < 0.1);
const agotada = computed(() => !vencida.value && disponibles.value === 0 && reservadas.value === 0);

// Ofertas creadas antes de existir la ventana de tiempo no tienen TTL (finMs = Infinity).
const sinFin = computed(() => !Number.isFinite(props.oferta.finMs));
const textoTiempo = computed(() => {
  if (vencida.value) return "Finalizada";
  return sinFin.value ? "Sin límite" : formatoCuentaRegresiva(segundos.value);
});
const horaFin = computed(() =>
  sinFin.value
    ? "sin fecha"
    : new Date(props.oferta.finMs).toLocaleString("es-GT", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Guatemala" })
);

function q(n) {
  return `Q${Number(n || 0).toFixed(2)}`;
}
</script>

<template>
  <article
    :class="[
      'bg-white rounded-2xl border flex flex-col overflow-hidden transition',
      vencida ? 'border-neutral-200 opacity-60' : pocoTiempo || pocoCupo ? 'border-amber-300 ring-2 ring-amber-200/60' : 'border-neutral-200 hover:border-neutral-300',
    ]"
  >
    <div class="relative">
      <ImagenProducto :producto="productoImagen" altura-clase="h-40" class="rounded-none!" />
      <span
        v-if="descuento > 0"
        class="absolute top-3 left-3 px-2.5 py-1 rounded-full bg-accent text-white text-xs font-bold shadow-sm"
      >-{{ descuento }}%</span>
      <span
        v-if="vencida"
        class="absolute top-3 right-3 px-2.5 py-1 rounded-full bg-neutral-950 text-white text-[11px] font-semibold"
      >Finalizada</span>
      <span
        v-else-if="agotada"
        class="absolute top-3 right-3 px-2.5 py-1 rounded-full bg-neutral-950 text-white text-[11px] font-semibold"
      >Agotada</span>
      <span
        v-else-if="pocoTiempo || pocoCupo"
        class="absolute top-3 right-3 px-2.5 py-1 rounded-full bg-amber-400 text-amber-950 text-[11px] font-semibold"
      >{{ pocoTiempo ? "Últimos minutos" : "Últimas unidades" }}</span>
    </div>

    <div class="p-5 flex flex-col gap-4 flex-1">
      <div>
        <p class="text-[11px] text-neutral-400 font-mono">{{ oferta.producto_id }}</p>
        <h3 class="font-semibold text-neutral-950 leading-snug line-clamp-2" :title="oferta.nombre">{{ oferta.nombre }}</h3>
        <div class="flex items-baseline gap-2 mt-1.5">
          <p class="text-xl font-extrabold text-accent-700 tracking-tight">{{ q(oferta.precio_oferta) }}</p>
          <p class="text-sm text-neutral-400 line-through">{{ q(oferta.precio_base) }}</p>
        </div>
      </div>

      <div
        :class="[
          'rounded-xl px-3.5 py-2.5 flex items-center justify-between gap-3',
          vencida ? 'bg-neutral-100' : pocoTiempo ? 'bg-amber-50' : 'bg-neutral-50',
        ]"
      >
        <div>
          <p class="text-[10px] uppercase tracking-wider font-bold text-neutral-400">{{ vencida ? "Estado" : "Termina en" }}</p>
          <p
            :class="['text-lg font-extrabold tabular-nums tracking-tight', vencida ? 'text-neutral-500' : pocoTiempo ? 'text-amber-700' : 'text-neutral-950']"
            aria-live="off"
          >{{ textoTiempo }}</p>
        </div>
        <p class="text-[11px] text-neutral-400 text-right leading-tight">Fin<br>{{ horaFin }}</p>
      </div>

      <div>
        <div class="flex items-baseline justify-between mb-1.5">
          <p class="text-sm font-semibold text-neutral-950">Quedan {{ disponibles }} de {{ limite }}</p>
          <p :class="['text-xs font-semibold', pocoCupo ? 'text-amber-700' : 'text-neutral-400']">{{ Math.round(pct(disponibles)) }}% libre</p>
        </div>
        <div
          class="h-2.5 rounded-full bg-neutral-100 overflow-hidden flex"
          role="img"
          :aria-label="`${vendidas} vendidas, ${reservadas} reservadas, ${disponibles} disponibles de ${limite}`"
        >
          <div class="h-full bg-accent transition-all duration-500" :style="{ width: pct(vendidas) + '%' }"></div>
          <div class="h-full bg-accent/40 transition-all duration-500" :style="{ width: pct(reservadas) + '%' }"></div>
        </div>
        <div class="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-[11px] text-neutral-500">
          <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-accent"></span>{{ vendidas }} vendidas</span>
          <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-accent/40"></span>{{ reservadas }} reservadas</span>
          <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-neutral-200"></span>{{ disponibles }} disponibles</span>
        </div>
      </div>

      <div class="mt-auto pt-1">
        <div v-if="confirmando" class="rounded-xl border border-red-200 bg-red-50 p-3" role="alert">
          <p class="text-xs text-red-800 font-semibold mb-2.5">¿Finalizar ahora? Las reservas en curso se liberan y el precio vuelve a la normalidad.</p>
          <div class="flex gap-2">
            <button
              type="button"
              @click="confirmando = false"
              :disabled="finalizando"
              class="flex-1 px-3 py-1.5 border border-neutral-300 hover:border-neutral-400 bg-white text-neutral-700 rounded-full text-xs font-semibold transition disabled:opacity-50"
            >Cancelar</button>
            <button
              type="button"
              @click="emit('finalizar')"
              :disabled="finalizando"
              class="flex-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-full text-xs font-semibold transition disabled:opacity-60 flex items-center justify-center gap-1.5"
            >
              <span v-if="finalizando" class="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin"></span>
              {{ finalizando ? "Finalizando..." : "Sí, finalizar" }}
            </button>
          </div>
        </div>
        <div v-else class="flex gap-2">
          <RouterLink
            :to="`/producto/${oferta.producto_id}`"
            target="_blank"
            class="flex-1 text-center px-3 py-2 border border-neutral-200 hover:border-neutral-400 text-neutral-700 rounded-full text-xs font-semibold transition"
          >Ver en tienda</RouterLink>
          <button
            type="button"
            v-if="!vencida"
            @click="confirmando = true"
            class="flex-1 px-3 py-2 border border-neutral-200 hover:border-red-300 hover:bg-red-50 hover:text-red-700 text-neutral-700 rounded-full text-xs font-semibold transition"
          >Finalizar</button>
        </div>
      </div>
    </div>
  </article>
</template>
