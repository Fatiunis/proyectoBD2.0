<script setup>
import { ref, computed, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";
import { useCategorias } from "../../composables/useCategorias";

const props = defineProps({
  productoParaEditar: { type: Object, default: null },
});
const emit = defineEmits(["guardado", "nuevo"]);

const { sesion } = useSesion();
const { toast } = useToast();
const { categorias } = useCategorias();

const formRef = ref(null);

const sku = ref("");
const nombre = ref("");
const descripcion = ref("");
const precio = ref("");
const stock = ref("");
const categoriaId = ref(null);
const atributosValores = ref({});
const atributosPersonalizados = ref([{ clave: "", valor: "" }]);

const categoriaActual = computed(() => categorias.value.find((c) => c.id_categoria === categoriaId.value) || null);
const esquemaAtributos = computed(() => categoriaActual.value?.esquema_atributos || []);

function inicializarAtributos(existentes = {}) {
  const nuevo = {};
  esquemaAtributos.value.forEach((attr) => {
    nuevo[attr.clave] = existentes[attr.clave] ?? "";
  });
  atributosValores.value = nuevo;
}

function agregarFilaPersonalizada() {
  atributosPersonalizados.value.push({ clave: "", valor: "" });
}

function quitarFilaPersonalizada(index) {
  atributosPersonalizados.value.splice(index, 1);
}

function onCambiarCategoria() {
  inicializarAtributos({});
}

if (props.productoParaEditar) {
  const p = props.productoParaEditar;
  sku.value = p.sku;
  nombre.value = p.nombre;
  descripcion.value = p.descripcion;
  precio.value = p.precio_base;
  stock.value = p.stock_disponible ?? 0;
  categoriaId.value = p.categoria.id_categoria;
  inicializarAtributos(p.atributos || {});

  const clavesEsquema = new Set(esquemaAtributos.value.map((attr) => attr.clave));
  const extras = Object.entries(p.atributos || {})
    .filter(([clave]) => !clavesEsquema.has(clave))
    .map(([clave, valor]) => ({ clave, valor: String(valor) }));
  atributosPersonalizados.value = extras.length > 0 ? extras : [{ clave: "", valor: "" }];
} else {
  categoriaId.value = categorias.value[0]?.id_categoria ?? null;
  inicializarAtributos({});
}

onMounted(() => {
  if (props.productoParaEditar) {
    formRef.value?.scrollIntoView({ behavior: "smooth" });
  }
});

async function guardarProducto() {
  const atributos = {};
  esquemaAtributos.value.forEach((attr) => {
    const valor = atributosValores.value[attr.clave];
    if (attr.tipo === "numero") {
      const numero = parseFloat(valor);
      if (!Number.isNaN(numero)) atributos[attr.clave] = numero;
    } else if (valor !== "" && valor !== null && valor !== undefined) {
      atributos[attr.clave] = valor;
    }
  });

  atributosPersonalizados.value.forEach((fila) => {
    const clave = fila.clave.trim();
    const valor = fila.valor.trim();
    if (!clave || !valor) return;
    if (clave in atributos) {
      toast(`"${clave}" ya es un atributo de la categoría, se ignoró el atributo personalizado con esa clave.`, "error");
      return;
    }
    atributos[clave] = valor;
  });

  const payload = {
    sku: sku.value,
    nombre: nombre.value,
    descripcion: descripcion.value,
    precio_base: parseFloat(precio.value),
    stock_disponible: parseInt(stock.value),
    id_categoria: categoriaId.value,
    nombre_categoria: categoriaActual.value ? categoriaActual.value.nombre : "General",
    id_vendedor: sesion.value.id_usuario,
    nombre_vendedor: sesion.value.nombre,
    rol_solicitante: sesion.value.rol,
    atributos,
  };

  const { ok, data } = await apiFetch("/productos", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  if (ok) {
    toast("Producto guardado y evento registrado en el historial.", "success");
    emit("guardado");
  } else {
    toast(data.error || "No se pudo guardar el producto.", "error");
  }
}
</script>

<template>
  <div ref="formRef">
    <div class="flex justify-between items-center mb-1">
      <p class="text-xs text-neutral-400">Formulario dinámico adaptable por categoría</p>
      <button type="button" @click="emit('nuevo')" class="text-xs font-semibold text-accent-700 hover:underline">+ Nuevo producto</button>
    </div>

    <form @submit.prevent="guardarProducto" class="space-y-5 mt-5">
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">SKU</label>
          <input type="text" v-model="sku" required class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Nombre</label>
          <input type="text" v-model="nombre" required class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
      </div>

      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Descripción</label>
        <textarea v-model="descripcion" required rows="2" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent"></textarea>
      </div>

      <div class="grid grid-cols-3 gap-4">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Precio (Q)</label>
          <input type="number" step="0.01" v-model="precio" required class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Stock</label>
          <input type="number" v-model="stock" required class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Categoría</label>
          <select v-model="categoriaId" @change="onCambiarCategoria" class="w-full border-0 border-b border-neutral-300 py-2 bg-transparent text-sm focus:ring-0 focus:border-accent outline-none transition">
            <option v-for="c in categorias" :key="c.id_categoria" :value="c.id_categoria">{{ c.nombre }}</option>
          </select>
        </div>
      </div>

      <div class="p-4 bg-neutral-50 border border-neutral-200 rounded-xl">
        <h4 class="text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-3">Atributos polimórficos de categoría</h4>
        <div class="grid grid-cols-2 gap-4">
          <p v-if="esquemaAtributos.length === 0" class="text-xs text-neutral-400 col-span-2">
            Esta categoría todavía no tiene atributos configurados. Agrégalos desde la pestaña "Categorías".
          </p>
          <div v-for="attr in esquemaAtributos" :key="attr.clave">
            <label class="text-xs font-medium text-neutral-600">{{ attr.etiqueta }}</label>
            <input
              :type="attr.tipo === 'numero' ? 'number' : 'text'"
              :step="attr.tipo === 'numero' ? 'any' : null"
              v-model="atributosValores[attr.clave]"
              class="w-full border border-neutral-300 p-1.5 rounded-lg bg-white text-sm focus:ring-2 focus:ring-accent-600 focus:border-accent-600 outline-none transition"
            >
          </div>
        </div>
      </div>

      <div class="p-4 bg-neutral-50 border border-neutral-200 rounded-xl">
        <div class="flex justify-between items-center mb-3">
          <h4 class="text-xs font-semibold uppercase tracking-wide text-neutral-400">Atributos adicionales de este producto</h4>
          <button type="button" @click="agregarFilaPersonalizada" class="text-xs font-semibold text-accent-700 hover:underline">+ Agregar atributo</button>
        </div>
        <div class="grid grid-cols-[1fr_1fr_28px] gap-2 mb-2">
          <span class="text-[10px] font-bold uppercase text-neutral-400">Clave</span>
          <span class="text-[10px] font-bold uppercase text-neutral-400">Valor</span>
          <span></span>
        </div>
        <div class="space-y-2">
          <div v-for="(fila, index) in atributosPersonalizados" :key="index" class="grid grid-cols-[1fr_1fr_28px] gap-2 items-center">
            <input type="text" v-model="fila.clave" placeholder="ej. tipo_bisagra" class="min-w-0 border border-neutral-300 p-1.5 rounded-lg bg-white text-xs font-mono focus:ring-2 focus:ring-accent-600 focus:border-accent-600 outline-none transition">
            <input type="text" v-model="fila.valor" class="min-w-0 border border-neutral-300 p-1.5 rounded-lg bg-white text-xs focus:ring-2 focus:ring-accent-600 focus:border-accent-600 outline-none transition">
            <button type="button" @click="quitarFilaPersonalizada(index)" class="text-neutral-400 hover:text-red-600 text-sm font-bold transition" title="Quitar atributo">✕</button>
          </div>
        </div>
        <p class="text-[11px] text-neutral-400 mt-2">La "clave" se usa como nombre del campo en la base documental (sin espacios ni acentos, ej. <code>talla_zapato</code>).</p>
      </div>

      <button type="submit" class="w-full py-3 mt-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition">Guardar en base documental</button>
    </form>
  </div>
</template>
