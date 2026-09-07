<script setup>
import { ref, computed, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";
import { useCategorias } from "../../composables/useCategorias";
import FormularioProducto from "./FormularioProducto.vue";
import ModalAdmin from "./ModalAdmin.vue";

const { sesion } = useSesion();
const { toast } = useToast();
const { cargarCategorias } = useCategorias();

const esVendedor = computed(() => sesion.value?.rol === "vendedor");

const productos = ref([]);
const cargando = ref(true);
const productoParaEditar = ref(null);
const claveFormulario = ref(0);
const mostrarModal = ref(false);

const tituloModal = computed(() => (productoParaEditar.value ? "Editar producto" : "Nuevo producto"));

async function cargarProductos() {
  const path = esVendedor.value ? `/productos?vendedor_id=${sesion.value.id_usuario}` : "/productos";
  const { data } = await apiFetch(path);
  productos.value = data || [];
}

async function editarProducto(id) {
  const { ok, data } = await apiFetch(`/productos/${id}`);
  if (!ok) {
    toast("No se pudo cargar el producto.", "error");
    return;
  }
  productoParaEditar.value = data;
  claveFormulario.value++;
  mostrarModal.value = true;
}

function nuevoProducto() {
  productoParaEditar.value = null;
  claveFormulario.value++;
}

function abrirModalNuevo() {
  nuevoProducto();
  mostrarModal.value = true;
}

function onGuardado() {
  nuevoProducto();
  cargarProductos();
  mostrarModal.value = false;
}

onMounted(async () => {
  await cargarCategorias();
  await cargarProductos();
  cargando.value = false;
});
</script>

<template>
  <div>
    <div class="flex justify-between items-start mb-6">
      <div>
        <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mb-1">{{ esVendedor ? "Mi catálogo" : "Catálogo" }}</h2>
        <p class="text-sm text-neutral-500">Alta y edición de productos con atributos por categoría</p>
      </div>
      <button
        @click="abrirModalNuevo"
        :disabled="cargando"
        class="px-4 py-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition disabled:opacity-50 disabled:cursor-not-allowed"
      >
        + Nuevo producto
      </button>
    </div>

    <div class="bg-white p-5 rounded-2xl border border-neutral-200">
      <div class="overflow-x-auto lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto scrollbar-fina">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-white z-10">
            <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
              <th class="p-2.5">ID</th>
              <th class="p-2.5">Nombre</th>
              <th class="p-2.5">SKU</th>
              <th class="p-2.5">Categoría</th>
              <th v-if="!esVendedor" class="p-2.5">Vendedor</th>
              <th class="p-2.5 text-right">Precio</th>
              <th class="p-2.5"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="productos.length === 0">
              <td :colspan="esVendedor ? 6 : 7" class="p-6 text-center text-sm text-neutral-400">
                {{ esVendedor ? "Aún no tienes productos en tu catálogo." : "Aún no hay productos en el catálogo." }}
              </td>
            </tr>
            <tr v-for="p in productos" :key="p._id" class="border-b border-neutral-100 hover:bg-neutral-50/80 transition">
              <td class="p-2.5 text-neutral-400 font-mono text-xs">{{ p._id }}</td>
              <td class="p-2.5 font-medium text-neutral-950">{{ p.nombre }}</td>
              <td class="p-2.5 text-neutral-500 font-mono text-xs">{{ p.sku }}</td>
              <td class="p-2.5"><span class="text-[10px] font-bold uppercase px-2 py-0.5 bg-accent-50 text-accent-700 rounded-full">{{ p.categoria.nombre }}</span></td>
              <td v-if="!esVendedor" class="p-2.5 text-neutral-500 text-xs">{{ p.vendedor ? p.vendedor.nombre_comercial : "N/D" }}</td>
              <td class="p-2.5 text-right font-semibold text-neutral-950">Q{{ p.precio_base.toFixed(2) }}</td>
              <td class="p-2.5 text-right">
                <button @click="editarProducto(p._id)" class="px-2.5 py-1 bg-neutral-950 hover:bg-neutral-800 text-white text-xs font-semibold rounded-full transition">Editar</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <ModalAdmin :abierto="mostrarModal" :titulo="tituloModal" ancho-clase="max-w-3xl" @cerrar="mostrarModal = false">
      <FormularioProducto
        v-if="!cargando"
        :key="claveFormulario"
        :producto-para-editar="productoParaEditar"
        @guardado="onGuardado"
        @nuevo="nuevoProducto"
      />
    </ModalAdmin>
  </div>
</template>
