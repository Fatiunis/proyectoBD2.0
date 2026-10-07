<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";
import ModalAdmin from "./ModalAdmin.vue";
import TarjetaOferta from "./TarjetaOferta.vue";
import FormularioOferta from "./FormularioOferta.vue";

const { sesion } = useSesion();
const { toast } = useToast();

const REFRESCO_MS = 15000;

const ofertas = ref([]);
const productos = ref([]);
const cargando = ref(true);
const cargandoProductos = ref(true);
const avisoCarga = ref("");
const ahora = ref(Date.now());
const ultimaActualizacion = ref(null);
const mostrarModal = ref(false);
const claveFormulario = ref(0);
const finalizandoId = ref(null);

let intervaloReloj = null;
let intervaloRefresco = null;
let refrescoPorVencimiento = null;
let consultando = false;

const mapaProductos = computed(() => Object.fromEntries(productos.value.map((p) => [p._id, p])));
const idsConOferta = computed(() => ofertas.value.filter((o) => o.finMs > ahora.value).map((o) => o.producto_id));

const resumen = computed(() => {
  const activas = ofertas.value.filter((o) => o.finMs > ahora.value);
  return {
    activas: activas.length,
    vendidas: activas.reduce((s, o) => s + (o.unidades_vendidas || 0), 0),
    restantes: activas.reduce((s, o) => s + (o.stock_restante || 0), 0),
  };
});

const haceCuanto = computed(() => {
  if (!ultimaActualizacion.value) return "";
  const s = Math.max(0, Math.round((ahora.value - ultimaActualizacion.value) / 1000));
  return s < 5 ? "justo ahora" : `hace ${s} s`;
});

async function cargarOfertas() {
  if (consultando) return;
  consultando = true;
  const id = sesion.value.id_usuario;
  const { ok, status, data } = await apiFetch(
    `/vendedores/${id}/ofertas?rol_solicitante=${encodeURIComponent(sesion.value.rol)}&id_usuario=${id}`
  );
  consultando = false;

  if (ok) {
    const recibido = Date.now();
    ofertas.value = (data.ofertas || [])
      .map((o) => ({ ...o, finMs: o.segundos_restantes == null ? Infinity : recibido + o.segundos_restantes * 1000 }));
    avisoCarga.value = "";
    ultimaActualizacion.value = recibido;
    ahora.value = recibido;
  } else if (status === 404) {
    avisoCarga.value = "El listado de ofertas aún no está disponible en el servidor. Puedes crear ofertas igual; aparecerán aquí cuando el listado esté habilitado.";
  } else {
    avisoCarga.value = data?.error || "No se pudo actualizar el listado de ofertas.";
  }
}

// /productos pagina con máximo 100 por página: se pide la primera y el resto en paralelo.
async function cargarProductos() {
  const params = new URLSearchParams({ por_pagina: 100, vendedor_id: sesion.value.id_usuario });
  const primera = await apiFetch(`/productos?${params}&pagina=1`);
  if (!primera.ok) {
    toast("No se pudo cargar tu catálogo para el selector.", "error");
    cargandoProductos.value = false;
    return;
  }
  const restantes = await Promise.all(
    Array.from({ length: Math.max((primera.data.total_paginas || 1) - 1, 0) }, (_, i) =>
      apiFetch(`/productos?${params}&pagina=${i + 2}`)
    )
  );
  productos.value = [primera, ...restantes].flatMap((r) => (r.ok ? r.data.items : []));
  cargandoProductos.value = false;
}

function onVencida() {
  clearTimeout(refrescoPorVencimiento);
  refrescoPorVencimiento = setTimeout(cargarOfertas, 4000);
}

async function finalizar(oferta) {
  finalizandoId.value = oferta.producto_id;
  const { ok, data } = await apiFetch(`/ofertas/${oferta.producto_id}`, {
    method: "DELETE",
    body: JSON.stringify({ rol_solicitante: sesion.value.rol, id_usuario: sesion.value.id_usuario }),
  });
  finalizandoId.value = null;

  if (ok) {
    toast(`Oferta de ${oferta.nombre} finalizada`, "success");
    ofertas.value = ofertas.value.filter((o) => o.producto_id !== oferta.producto_id);
  } else {
    toast(data?.error || "No se pudo finalizar la oferta.", "error");
  }
  cargarOfertas();
}

function abrirNueva() {
  claveFormulario.value++;
  mostrarModal.value = true;
}

function onCreada() {
  mostrarModal.value = false;
  cargarOfertas();
}

onMounted(async () => {
  intervaloReloj = setInterval(() => (ahora.value = Date.now()), 1000);
  intervaloRefresco = setInterval(cargarOfertas, REFRESCO_MS);
  cargarProductos();
  await cargarOfertas();
  cargando.value = false;
});

onUnmounted(() => {
  clearInterval(intervaloReloj);
  clearInterval(intervaloRefresco);
  clearTimeout(refrescoPorVencimiento);
});
</script>

<template>
  <div>
    <div class="flex flex-wrap justify-between items-start gap-4 mb-6">
      <div>
        <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mb-1">Ofertas flash</h2>
        <p class="text-sm text-neutral-500">Precio especial por tiempo y cupo limitado sobre tus productos (Redis)</p>
      </div>
      <button
        @click="abrirNueva"
        class="px-4 py-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition flex items-center gap-2"
      >
        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" /></svg>
        Nueva oferta flash
      </button>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
      <div class="bg-white p-5 rounded-2xl border border-neutral-200">
        <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Ofertas activas</p>
        <p class="text-2xl font-extrabold text-neutral-950">{{ resumen.activas }}</p>
      </div>
      <div class="bg-white p-5 rounded-2xl border border-neutral-200">
        <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Unidades vendidas</p>
        <p class="text-2xl font-extrabold text-accent-700">{{ resumen.vendidas }}</p>
      </div>
      <div class="bg-white p-5 rounded-2xl border border-neutral-200">
        <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Unidades restantes</p>
        <p class="text-2xl font-extrabold text-neutral-950">{{ resumen.restantes }}</p>
      </div>
    </div>

    <div
      v-if="avisoCarga"
      role="status"
      class="mb-5 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
    >
      <span class="mt-0.5 w-5 h-5 shrink-0 rounded-full bg-amber-400 text-amber-950 text-xs font-bold flex items-center justify-center" aria-hidden="true">!</span>
      <p class="flex-1">{{ avisoCarga }}</p>
      <button @click="cargarOfertas" class="shrink-0 text-xs font-semibold underline underline-offset-2 hover:text-amber-700">Reintentar</button>
    </div>

    <div v-if="cargando" class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5" aria-busy="true">
      <div v-for="n in 3" :key="n" class="bg-white rounded-2xl border border-neutral-200 overflow-hidden animate-pulse">
        <div class="h-40 bg-neutral-100"></div>
        <div class="p-5 space-y-3">
          <div class="h-4 bg-neutral-100 rounded w-3/4"></div>
          <div class="h-6 bg-neutral-100 rounded w-1/3"></div>
          <div class="h-12 bg-neutral-100 rounded-xl"></div>
          <div class="h-2.5 bg-neutral-100 rounded-full"></div>
        </div>
      </div>
    </div>

    <div
      v-else-if="ofertas.length === 0"
      class="bg-white rounded-2xl border border-dashed border-neutral-300 px-6 py-14 flex flex-col items-center text-center"
    >
      <div class="w-16 h-16 rounded-2xl bg-accent-50 text-accent flex items-center justify-center mb-4">
        <svg class="w-8 h-8" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" /></svg>
      </div>
      <h3 class="text-lg font-bold text-neutral-950 tracking-tight">Aún no tienes ofertas activas</h3>
      <p class="text-sm text-neutral-500 max-w-sm mt-1 mb-5">
        Lanza una oferta flash con un precio especial, un cupo de unidades y una cuenta regresiva para mover tu inventario.
      </p>
      <button
        @click="abrirNueva"
        class="px-5 py-2.5 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition"
      >Crear mi primera oferta</button>
    </div>

    <template v-else>
      <div class="flex items-center justify-between mb-3 text-xs text-neutral-400">
        <p>Ordenadas por las que vencen antes</p>
        <p v-if="haceCuanto">Actualizado {{ haceCuanto }}</p>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-5">
        <TarjetaOferta
          v-for="o in ofertas"
          :key="o.producto_id"
          :oferta="o"
          :producto="mapaProductos[o.producto_id] || null"
          :ahora="ahora"
          :finalizando="finalizandoId === o.producto_id"
          @finalizar="finalizar(o)"
          @vencida="onVencida"
        />
      </div>
    </template>

    <ModalAdmin :abierto="mostrarModal" titulo="Nueva oferta flash" ancho-clase="max-w-4xl" @cerrar="mostrarModal = false">
      <FormularioOferta
        :key="claveFormulario"
        :productos="productos"
        :ids-con-oferta="idsConOferta"
        :cargando-productos="cargandoProductos"
        :ahora="ahora"
        @creada="onCreada"
        @cancelar="mostrarModal = false"
      />
    </ModalAdmin>
  </div>
</template>
