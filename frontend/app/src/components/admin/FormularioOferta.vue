<script setup>
import { ref, computed, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";
import ImagenProducto from "../ImagenProducto.vue";
import { porcentajeDescuento } from "../../utils/descuento";

const props = defineProps({
  productos: { type: Array, required: true },
  idsConOferta: { type: Array, default: () => [] },
  cargandoProductos: { type: Boolean, default: false },
  ahora: { type: Number, required: true },
});
const emit = defineEmits(["creada", "cancelar"]);

const { sesion } = useSesion();
const { toast } = useToast();

// Mismos límites que valida el backend en POST /api/ofertas.
const DURACION_MAXIMA_MINUTOS = 10080;
const CHIPS_DESCUENTO = [10, 20, 30, 50];
const CHIPS_DURACION = [
  { etiqueta: "1 h", minutos: 60 },
  { etiqueta: "6 h", minutos: 360 },
  { etiqueta: "24 h", minutos: 1440 },
  { etiqueta: "3 días", minutos: 4320 },
];
const UNIDADES_DURACION = { minutos: 1, horas: 60, dias: 1440 };

const busqueda = ref("");
const idSeleccionado = ref(null);
const precioTexto = ref("");
const descuentoTexto = ref("");
const cupo = ref(10);
const duracionMinutos = ref(60);
const duracionPersonalizada = ref(false);
const duracionValor = ref(60);
const duracionUnidad = ref("minutos");
const intentoEnviar = ref(false);
const tocados = ref({});
const enviando = ref(false);
const errorServidor = ref("");
const inputBusqueda = ref(null);

onMounted(() => inputBusqueda.value?.focus());

const conOferta = computed(() => new Set(props.idsConOferta));
const productoSeleccionado = computed(() => props.productos.find((p) => p._id === idSeleccionado.value) || null);
const precioBase = computed(() => productoSeleccionado.value?.precio_base ?? null);

const productosFiltrados = computed(() => {
  const t = busqueda.value.trim().toLowerCase();
  const lista = t
    ? props.productos.filter((p) => `${p.nombre} ${p.sku} ${p._id}`.toLowerCase().includes(t))
    : props.productos;
  return [...lista].sort((a, b) => Number(conOferta.value.has(a._id)) - Number(conOferta.value.has(b._id)) || a.nombre.localeCompare(b.nombre));
});

function redondear2(n) {
  return Math.round(n * 100) / 100;
}

function seleccionar(p) {
  if (conOferta.value.has(p._id)) return;
  idSeleccionado.value = p._id;
  errorServidor.value = "";
  if (descuentoTexto.value !== "" && Number(descuentoTexto.value) > 0) aplicarDescuento(Number(descuentoTexto.value));
  else if (precioTexto.value !== "") onPrecio();
}

function onPrecio() {
  tocados.value.precio = true;
  const p = Number(precioTexto.value);
  if (precioBase.value && precioTexto.value !== "" && Number.isFinite(p)) {
    const pct = redondear2((1 - p / precioBase.value) * 100);
    descuentoTexto.value = String(p > 0 ? Math.min(pct, 99.99) : pct);
  } else if (precioTexto.value === "") {
    descuentoTexto.value = "";
  }
}

function onDescuento() {
  tocados.value.precio = true;
  if (descuentoTexto.value === "") {
    precioTexto.value = "";
    return;
  }
  aplicarDescuento(Number(descuentoTexto.value), false);
}

function aplicarDescuento(pct, actualizarCampo = true) {
  tocados.value.precio = true;
  if (actualizarCampo) descuentoTexto.value = String(pct);
  if (precioBase.value && Number.isFinite(pct)) {
    precioTexto.value = redondear2(precioBase.value * (1 - pct / 100)).toFixed(2);
  }
}

function elegirDuracion(minutos) {
  duracionPersonalizada.value = false;
  duracionMinutos.value = minutos;
  tocados.value.duracion = true;
}

function activarPersonalizada() {
  duracionPersonalizada.value = true;
  onDuracionPersonalizada();
}

function onDuracionPersonalizada() {
  tocados.value.duracion = true;
  const v = Number(duracionValor.value);
  duracionMinutos.value = duracionValor.value === "" || !Number.isFinite(v) ? NaN : v * UNIDADES_DURACION[duracionUnidad.value];
}

const errores = computed(() => {
  const e = {};
  if (!productoSeleccionado.value) e.producto = "Elige uno de tus productos.";

  const texto = String(precioTexto.value).trim();
  const p = Number(texto);
  if (texto === "") e.precio = "Ingresa el precio de oferta o un % de descuento.";
  else if (!Number.isFinite(p)) e.precio = "Ingresa un número válido.";
  else if (p <= 0) e.precio = "Debe ser mayor que Q0.00.";
  else if (!/^\d+(\.\d{1,2})?$/.test(texto)) e.precio = "Máximo 2 decimales.";
  else if (precioBase.value != null && p >= precioBase.value) e.precio = `Debe ser menor que el precio normal (Q${precioBase.value.toFixed(2)}).`;

  const c = Number(cupo.value);
  if (cupo.value === "" || !Number.isInteger(c) || c <= 0) e.cupo = "Debe ser un número entero mayor que 0.";

  const d = duracionMinutos.value;
  if (!Number.isInteger(d)) e.duracion = "La duración debe ser un número entero de minutos.";
  else if (d < 1 || d > DURACION_MAXIMA_MINUTOS) e.duracion = "Debe durar entre 1 minuto y 7 días.";
  return e;
});

const formularioValido = computed(() => Object.keys(errores.value).length === 0);

function errorVisible(campo) {
  return (intentoEnviar.value || tocados.value[campo]) && errores.value[campo];
}

const descuentoPreview = computed(() => {
  const p = Number(precioTexto.value);
  if (!precioBase.value || errores.value.precio) return null;
  return { precio: p, ahorro: precioBase.value - p, pct: porcentajeDescuento(p, precioBase.value) };
});

const finEstimado = computed(() => {
  if (errores.value.duracion) return null;
  return new Date(props.ahora + duracionMinutos.value * 60000).toLocaleString("es-GT", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Guatemala",
  });
});

const duracionLegible = computed(() => {
  const d = duracionMinutos.value;
  if (!Number.isInteger(d) || d < 1) return "";
  const dias = Math.floor(d / 1440);
  const horas = Math.floor((d % 1440) / 60);
  const min = d % 60;
  return [dias && `${dias} d`, horas && `${horas} h`, min && `${min} min`].filter(Boolean).join(" ");
});

const avisoStock = computed(() => {
  const stock = productoSeleccionado.value?.stock_disponible;
  if (stock == null || errores.value.cupo) return "";
  return Number(cupo.value) > stock ? `El cupo supera el stock disponible del producto (${stock}).` : "";
});

async function enviar() {
  intentoEnviar.value = true;
  errorServidor.value = "";
  if (!formularioValido.value || enviando.value) return;

  enviando.value = true;
  const { ok, status, data } = await apiFetch("/ofertas", {
    method: "POST",
    body: JSON.stringify({
      producto_id: idSeleccionado.value,
      cantidad_limite: Number(cupo.value),
      duracion_minutos: duracionMinutos.value,
      precio_oferta: Number(precioTexto.value),
      rol_solicitante: sesion.value.rol,
      id_usuario: sesion.value.id_usuario,
    }),
  });
  enviando.value = false;

  if (ok) {
    toast(`Oferta flash creada para ${productoSeleccionado.value.nombre}`, "success");
    emit("creada", idSeleccionado.value);
  } else if (status === 409) {
    errorServidor.value = "Este producto ya tiene una oferta activa. Finalízala primero o elige otro producto.";
  } else {
    errorServidor.value = data?.error || "No se pudo crear la oferta.";
  }
}

function q(n) {
  return `Q${Number(n || 0).toFixed(2)}`;
}

const claseInput =
  "w-full border border-neutral-200 focus:border-accent focus:ring-2 focus:ring-accent/20 rounded-xl px-3 py-2 text-sm bg-white outline-none transition";
function claseChip(activo) {
  return [
    "px-3 py-1 rounded-full text-xs font-semibold border transition",
    activo ? "bg-neutral-950 border-neutral-950 text-white" : "border-neutral-200 text-neutral-600 hover:border-neutral-400",
  ];
}
</script>

<template>
  <form @submit.prevent="enviar" novalidate class="grid lg:grid-cols-[1fr_300px] gap-6">
    <div class="space-y-5 min-w-0">
      <fieldset class="min-w-0">
        <legend class="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">Producto</legend>
        <label for="oferta-busqueda" class="sr-only">Buscar producto</label>
        <input
          id="oferta-busqueda"
          ref="inputBusqueda"
          v-model="busqueda"
          type="search"
          placeholder="Buscar por nombre, SKU o ID..."
          :class="claseInput"
        >
        <div
          class="mt-2 border border-neutral-200 rounded-xl max-h-56 overflow-y-auto scrollbar-fina divide-y divide-neutral-100"
          role="listbox"
          aria-label="Tus productos"
        >
          <p v-if="cargandoProductos" class="p-4 text-sm text-neutral-400 text-center">Cargando tus productos...</p>
          <p v-else-if="productosFiltrados.length === 0" class="p-4 text-sm text-neutral-400 text-center">
            {{ productos.length === 0 ? "Aún no tienes productos en tu catálogo." : "Ningún producto coincide con la búsqueda." }}
          </p>
          <button
            v-for="p in productosFiltrados"
            :key="p._id"
            type="button"
            role="option"
            :aria-selected="p._id === idSeleccionado"
            :disabled="conOferta.has(p._id)"
            @click="seleccionar(p)"
            :class="[
              'w-full flex items-center gap-3 px-3 py-2 text-left transition',
              p._id === idSeleccionado ? 'bg-accent-50' : 'hover:bg-neutral-50',
              conOferta.has(p._id) ? 'opacity-50 cursor-not-allowed' : '',
            ]"
          >
            <div class="w-11 shrink-0"><ImagenProducto :producto="p" altura-clase="h-11" class="rounded-lg! [&_svg]:scale-75" /></div>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium text-neutral-950 truncate">{{ p.nombre }}</p>
              <p class="text-[11px] text-neutral-400 font-mono truncate">{{ p._id }} · {{ p.sku }}</p>
            </div>
            <span v-if="conOferta.has(p._id)" class="shrink-0 text-[10px] font-bold uppercase px-2 py-0.5 bg-amber-100 text-amber-800 rounded-full">Ya en oferta</span>
            <span v-else class="shrink-0 text-sm font-semibold text-neutral-950">{{ q(p.precio_base) }}</span>
            <span
              v-if="p._id === idSeleccionado"
              class="shrink-0 w-5 h-5 rounded-full bg-accent text-white text-xs flex items-center justify-center"
              aria-hidden="true"
            >✓</span>
          </button>
        </div>
        <p v-if="errorVisible('producto')" class="text-xs text-red-600 mt-1.5">{{ errores.producto }}</p>
      </fieldset>

      <div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label for="oferta-precio" class="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">Precio de oferta (Q)</label>
            <input
              id="oferta-precio"
              v-model="precioTexto"
              @input="onPrecio"
              type="number" min="0.01" step="0.01" inputmode="decimal"
              :placeholder="precioBase ? `Menor a ${precioBase.toFixed(2)}` : '0.00'"
              :aria-invalid="!!errorVisible('precio')"
              aria-describedby="oferta-precio-ayuda"
              :class="[claseInput, errorVisible('precio') ? 'border-red-300' : '']"
            >
          </div>
          <div>
            <label for="oferta-descuento" class="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">o descuento (%)</label>
            <input
              id="oferta-descuento"
              v-model="descuentoTexto"
              @input="onDescuento"
              type="number" min="1" max="99" step="1" inputmode="decimal"
              placeholder="20"
              :disabled="!precioBase"
              :class="[claseInput, 'disabled:bg-neutral-50 disabled:text-neutral-400']"
            >
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2 mt-2">
          <span class="text-[11px] text-neutral-400">Rápido:</span>
          <button
            v-for="pct in CHIPS_DESCUENTO"
            :key="pct"
            type="button"
            :disabled="!precioBase"
            @click="aplicarDescuento(pct)"
            :class="[claseChip(Number(descuentoTexto) === pct), 'disabled:opacity-40 disabled:cursor-not-allowed']"
          >-{{ pct }}%</button>
        </div>
        <p id="oferta-precio-ayuda" class="text-xs mt-1.5" :class="errorVisible('precio') ? 'text-red-600' : 'text-neutral-400'">
          {{ errorVisible("precio") || (precioBase ? `Precio normal: Q${precioBase.toFixed(2)}. No se puede cambiar una vez creada.` : "Elige un producto para calcular el descuento.") }}
        </p>
      </div>

      <div>
        <label for="oferta-cupo" class="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">Cupo de unidades</label>
        <input
          id="oferta-cupo"
          v-model.number="cupo"
          @input="tocados.cupo = true"
          type="number" min="1" step="1"
          :aria-invalid="!!errorVisible('cupo')"
          :class="[claseInput, 'max-w-40', errorVisible('cupo') ? 'border-red-300' : '']"
        >
        <p v-if="errorVisible('cupo')" class="text-xs text-red-600 mt-1.5">{{ errores.cupo }}</p>
        <p v-else-if="avisoStock" class="text-xs text-amber-700 mt-1.5">{{ avisoStock }}</p>
        <p v-else class="text-xs text-neutral-400 mt-1.5">Unidades que se venden al precio de oferta.</p>
      </div>

      <fieldset class="min-w-0">
        <legend class="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">Duración</legend>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="chip in CHIPS_DURACION"
            :key="chip.minutos"
            type="button"
            @click="elegirDuracion(chip.minutos)"
            :aria-pressed="!duracionPersonalizada && duracionMinutos === chip.minutos"
            :class="claseChip(!duracionPersonalizada && duracionMinutos === chip.minutos)"
          >{{ chip.etiqueta }}</button>
          <button type="button" @click="activarPersonalizada" :aria-pressed="duracionPersonalizada" :class="claseChip(duracionPersonalizada)">Personalizada</button>
        </div>
        <div v-if="duracionPersonalizada" class="flex gap-2 mt-2.5 max-w-xs">
          <label for="oferta-duracion" class="sr-only">Duración personalizada</label>
          <input
            id="oferta-duracion"
            v-model.number="duracionValor"
            @input="onDuracionPersonalizada"
            type="number" min="1" step="1"
            :aria-invalid="!!errorVisible('duracion')"
            :class="[claseInput, errorVisible('duracion') ? 'border-red-300' : '']"
          >
          <label for="oferta-unidad" class="sr-only">Unidad</label>
          <select id="oferta-unidad" v-model="duracionUnidad" @change="onDuracionPersonalizada" :class="[claseInput, 'w-32']">
            <option value="minutos">minutos</option>
            <option value="horas">horas</option>
            <option value="dias">días</option>
          </select>
        </div>
        <p v-if="errorVisible('duracion')" class="text-xs text-red-600 mt-1.5">{{ errores.duracion }}</p>
        <p v-else class="text-xs text-neutral-400 mt-1.5">{{ duracionLegible }} · máximo 7 días.</p>
      </fieldset>
    </div>

    <aside class="space-y-4">
      <div>
        <p class="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-2">Así la verá el comprador</p>
        <div class="rounded-2xl border border-neutral-200 p-4 space-y-3 bg-white">
          <ImagenProducto
            v-if="productoSeleccionado"
            :producto="productoSeleccionado"
            altura-clase="h-32"
          />
          <div v-else class="h-32 rounded-2xl border-2 border-dashed border-neutral-200 flex items-center justify-center text-xs text-neutral-400">Sin producto</div>
          <p class="text-sm font-semibold text-neutral-950 line-clamp-2">{{ productoSeleccionado?.nombre || "Tu producto" }}</p>
          <div>
            <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-accent-700">Oferta relámpago</p>
            <div class="flex items-baseline flex-wrap gap-x-2 gap-y-1 mt-0.5">
              <p class="text-2xl font-extrabold text-accent-700 tracking-tight">{{ descuentoPreview ? q(descuentoPreview.precio) : "Q—" }}</p>
              <p v-if="precioBase" class="text-xs text-neutral-400 line-through">{{ q(precioBase) }}</p>
              <span v-if="descuentoPreview && descuentoPreview.pct > 0" class="px-2 py-0.5 rounded-full bg-accent text-white text-[11px] font-semibold">-{{ descuentoPreview.pct }}%</span>
            </div>
            <p v-if="descuentoPreview" class="text-xs font-semibold text-accent-700 mt-1">Ahorra {{ q(descuentoPreview.ahorro) }}</p>
          </div>
          <p class="text-xs font-semibold text-neutral-950">Quedan {{ errores.cupo ? "—" : cupo }} de {{ errores.cupo ? "—" : cupo }} unidades</p>
          <div class="h-1.5 rounded-full bg-accent"></div>
          <p class="text-[11px] text-neutral-400">{{ finEstimado ? `Finaliza el ${finEstimado}` : "Elige una duración válida" }}</p>
        </div>
      </div>

      <div v-if="errorServidor" role="alert" class="rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-xs text-red-800 font-medium">
        {{ errorServidor }}
      </div>

      <div class="flex gap-2">
        <button
          type="button"
          @click="emit('cancelar')"
          class="flex-1 px-4 py-2.5 border border-neutral-200 hover:border-neutral-400 text-neutral-700 rounded-full text-sm font-semibold transition"
        >Cancelar</button>
        <button
          type="submit"
          :disabled="enviando || (intentoEnviar && !formularioValido)"
          class="flex-[2] px-4 py-2.5 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-full text-sm transition flex items-center justify-center gap-2"
        >
          <span v-if="enviando" class="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" aria-hidden="true"></span>
          {{ enviando ? "Creando..." : "Lanzar oferta" }}
        </button>
      </div>
    </aside>
  </form>
</template>
