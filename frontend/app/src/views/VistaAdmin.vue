<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useSesion } from "../composables/useSesion";
import LoginAdmin from "../components/admin/LoginAdmin.vue";
import SidebarAdmin from "../components/admin/SidebarAdmin.vue";
import GestionProductos from "../components/admin/GestionProductos.vue";
import GestionVentas from "../components/admin/GestionVentas.vue";
import GestionCategorias from "../components/admin/GestionCategorias.vue";
import GestionUsuarios from "../components/admin/GestionUsuarios.vue";
import HistorialProducto from "../components/admin/HistorialProducto.vue";

const ROLES_CON_ACCESO = ["administrador", "vendedor"];
const TABS_VALIDOS = ["catalogo", "categorias", "usuarios", "ventas", "historial"];

const props = defineProps({ tab: { type: String, default: null } });

const router = useRouter();
const { sesion } = useSesion();

const tieneAcceso = computed(() => !!sesion.value && ROLES_CON_ACCESO.includes(sesion.value.rol));
const esVendedor = computed(() => sesion.value?.rol === "vendedor");

const tabActual = computed(() => {
  if (!TABS_VALIDOS.includes(props.tab)) return "catalogo";
  if (esVendedor.value && !["catalogo", "ventas", "historial"].includes(props.tab)) return "catalogo";
  if (!esVendedor.value && props.tab === "ventas") return "catalogo";
  return props.tab;
});

function cambiarTab(tab) {
  router.push(`/admin/${tab}`);
}
</script>

<template>
  <LoginAdmin v-if="!tieneAcceso" />
  <div v-else class="min-h-screen">
    <SidebarAdmin :tab-actual="tabActual" :es-vendedor="esVendedor" @cambiar-tab="cambiarTab" />
    <main class="ml-60 p-8 max-w-[1800px]">
      <GestionProductos v-if="tabActual === 'catalogo'" />
      <GestionVentas v-else-if="tabActual === 'ventas' && esVendedor" />
      <GestionCategorias v-else-if="tabActual === 'categorias' && !esVendedor" />
      <GestionUsuarios v-else-if="tabActual === 'usuarios' && !esVendedor" />
      <HistorialProducto v-else-if="tabActual === 'historial'" />
    </main>
  </div>
</template>
