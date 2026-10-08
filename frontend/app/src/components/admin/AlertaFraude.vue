<script setup>
import { ref, computed, useId } from "vue";
import { useRouter } from "vue-router";
import { ESTILO_NIVEL, ETIQUETA_NIVEL, etiquetaEvidencia, valorEvidencia, ordenarEvidencia } from "../../utils/fraude";

const props = defineProps({
  alerta: { type: Object, required: true },
});

const router = useRouter();
const idDetalle = useId();
const abierto = ref(false);

const NOMBRES_VISIBLES = 3;

const cuentas = computed(() => props.alerta.cuentas || []);
const productos = computed(() => props.alerta.productos || []);
const nombrePorId = computed(() => Object.fromEntries(cuentas.value.map((c) => [c.id_usuario, c.nombre])));

const quienes = computed(() => cuentas.value.slice(0, NOMBRES_VISIBLES).map((c) => c.nombre).join(", "));
const quienesExtra = computed(() => Math.max(0, cuentas.value.length - NOMBRES_VISIBLES));

const que = computed(() => {
  if (props.alerta.vendedor) return `Tienda ${props.alerta.vendedor.nombre}`;
  if (!productos.value.length) return "";
  const primero = productos.value[0].nombre || productos.value[0].id_producto;
  return productos.value.length === 1 ? primero : `${primero} y ${productos.value.length - 1} producto${productos.value.length === 2 ? "" : "s"} más`;
});

const evidencia = computed(() => ordenarEvidencia(props.alerta.evidencia).filter(([clave]) => clave !== "pares"));
const pares = computed(() => props.alerta.evidencia?.pares || []);

function nombreCuenta(id) {
  return nombrePorId.value[id] || `#${id}`;
}

function enlaceProducto(id) {
  return router.resolve(`/producto/${encodeURIComponent(id)}`).href;
}
</script>

<template>
  <article class="bg-white rounded-2xl border border-neutral-200">
    <div class="flex items-start gap-3 px-4 py-3">
      <span :class="['mt-0.5 shrink-0 px-2.5 py-0.5 rounded-full text-xs font-bold border', ESTILO_NIVEL[alerta.nivel] || ESTILO_NIVEL.bajo]">
        Riesgo {{ (ETIQUETA_NIVEL[alerta.nivel] || alerta.nivel || "").toLowerCase() }}
      </span>
      <div class="min-w-0 flex-1">
        <p class="text-sm text-neutral-950 truncate">
          <span class="font-semibold">{{ quienes }}</span>
          <span v-if="quienesExtra" class="text-neutral-500 font-semibold"> +{{ quienesExtra }}</span>
          <template v-if="que">
            <span class="text-neutral-400" aria-hidden="true"> → </span>
            <span class="sr-only">, sobre </span>
            <span class="text-neutral-700">{{ que }}</span>
          </template>
        </p>
        <p class="text-sm text-neutral-600 mt-0.5 leading-snug">{{ alerta.motivo }}</p>
      </div>
      <button
        type="button"
        @click="abierto = !abierto"
        :aria-expanded="abierto"
        :aria-controls="idDetalle"
        class="shrink-0 px-3 py-1 bg-neutral-100 hover:bg-neutral-200 text-neutral-700 text-xs font-semibold rounded-full transition"
      >{{ abierto ? "Ocultar" : "Ver detalle" }}</button>
    </div>

    <div v-if="abierto" :id="idDetalle" class="border-t border-neutral-100 bg-neutral-50/70 rounded-b-2xl px-4 py-4 space-y-4">
      <div class="grid gap-4 md:grid-cols-2">
        <div>
          <h4 class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1.5">Cuentas ({{ cuentas.length }})</h4>
          <ul class="flex flex-wrap gap-1.5">
            <li v-for="c in cuentas" :key="c.id_usuario" class="px-2.5 py-1 rounded-full bg-white border border-neutral-200 text-xs font-medium text-neutral-800">
              {{ c.nombre }} <span class="text-neutral-400">#{{ c.id_usuario }}</span>
            </li>
          </ul>
        </div>
        <div>
          <h4 class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1.5">Productos ({{ productos.length }})</h4>
          <ul class="flex flex-wrap gap-1.5">
            <li v-for="p in productos" :key="p.id_producto">
              <a
                :href="enlaceProducto(p.id_producto)"
                target="_blank"
                rel="noopener"
                class="inline-block px-2.5 py-1 rounded-full bg-white border border-neutral-200 hover:border-accent-600 text-xs text-accent-700 font-medium transition"
                :title="`Abrir ${p.nombre || p.id_producto} en una pestaña nueva`"
              >{{ p.nombre || p.id_producto }}</a>
            </li>
          </ul>
        </div>
      </div>

      <div v-if="alerta.vendedor" class="text-sm">
        <span class="text-neutral-500">Tienda:</span>
        <span class="font-semibold text-neutral-900"> {{ alerta.vendedor.nombre }}</span>
      </div>

      <div v-if="evidencia.length">
        <h4 class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-2">Evidencia</h4>
        <dl class="grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3 text-sm">
          <div v-for="[clave, valor] in evidencia" :key="clave" class="min-w-0">
            <dt class="text-xs text-neutral-500">{{ etiquetaEvidencia(clave) }}</dt>
            <dd class="font-semibold text-neutral-900 break-words">{{ valorEvidencia(clave, valor) }}</dd>
          </div>
        </dl>
      </div>

      <div v-if="pares.length">
        <h4 class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1.5">{{ etiquetaEvidencia("pares") }}</h4>
        <ul class="grid gap-x-6 gap-y-1 sm:grid-cols-2 text-sm text-neutral-700">
          <li v-for="(par, i) in pares" :key="i">
            {{ (par.cuentas || []).map(nombreCuenta).join(" y ") }}:
            <span class="font-semibold text-neutral-900">{{ par.productos_en_comun }} producto{{ par.productos_en_comun === 1 ? "" : "s" }} en común</span>
          </li>
        </ul>
      </div>
    </div>
  </article>
</template>
