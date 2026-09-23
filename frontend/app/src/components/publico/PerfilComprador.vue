<script setup>
import { ref, reactive, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";

const { sesion, setSesion } = useSesion();
const { toast } = useToast();

const seccionActiva = ref("pedidos");

const ESTILO_ESTADO = {
  pendiente: "bg-amber-100 text-amber-800",
  pagado: "bg-emerald-100 text-emerald-800",
  enviado: "bg-sky-100 text-sky-800",
  entregado: "bg-emerald-100 text-emerald-800",
  cancelado: "bg-red-100 text-red-800",
};

function formatearFecha(iso) {
  return new Date(iso).toLocaleString("es-GT", { dateStyle: "long", timeZone: "America/Guatemala" });
}

// --- Mis pedidos ---
const pedidos = ref([]);
const resumenPedidos = ref({ total_gastado: 0, numero_pedidos: 0 });
const cargandoPedidos = ref(false);
const pedidoExpandido = ref(null);

async function cargarPedidos() {
  cargandoPedidos.value = true;
  const { ok, data } = await apiFetch(`/compradores/${sesion.value.id_usuario}/pedidos`);
  cargandoPedidos.value = false;
  if (!ok) {
    toast(data?.error || "No se pudieron cargar tus pedidos.", "error");
    return;
  }
  pedidos.value = data.pedidos || [];
  resumenPedidos.value = data.resumen;
}

function alternarPedido(idPedido) {
  pedidoExpandido.value = pedidoExpandido.value === idPedido ? null : idPedido;
}

// --- Editar perfil ---
const formularioPerfil = reactive({
  nombre: sesion.value?.nombre || "",
  telefono: sesion.value?.telefono || "",
});
const guardandoPerfil = ref(false);

const mostrarCambioPassword = ref(false);
const passwordActual = ref("");
const passwordNueva = ref("");
const passwordConfirmar = ref("");

function cancelarCambioPassword() {
  mostrarCambioPassword.value = false;
  passwordActual.value = "";
  passwordNueva.value = "";
  passwordConfirmar.value = "";
}

async function guardarPerfil() {
  const cambiandoPassword = mostrarCambioPassword.value && (passwordActual.value || passwordNueva.value || passwordConfirmar.value);
  if (cambiandoPassword && passwordNueva.value !== passwordConfirmar.value) {
    toast("La contraseña nueva y su confirmación no coinciden.", "error");
    return;
  }

  const payload = { nombre: formularioPerfil.nombre, telefono: formularioPerfil.telefono };
  if (cambiandoPassword) {
    payload.password_actual = passwordActual.value;
    payload.password_nueva = passwordNueva.value;
  }

  guardandoPerfil.value = true;
  const { ok, data } = await apiFetch(`/usuarios/${sesion.value.id_usuario}/perfil`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  guardandoPerfil.value = false;

  if (!ok) {
    toast(data?.error || "No se pudo actualizar tu perfil.", "error");
    return;
  }

  setSesion({ ...sesion.value, nombre: data.usuario.nombre, telefono: data.usuario.telefono ?? formularioPerfil.telefono });
  cancelarCambioPassword();
  toast("Perfil actualizado.", "success");
}

// --- Mis direcciones ---
const direcciones = ref([]);
const cargandoDirecciones = ref(false);
const mostrarFormDireccion = ref(false);
const editandoId = ref(null);
const guardandoDireccion = ref(false);
const formDireccion = reactive({
  direccion_linea1: "",
  direccion_linea2: "",
  ciudad: "",
  departamento_estado: "",
  codigo_postal: "",
});

function limpiarFormDireccion() {
  Object.keys(formDireccion).forEach((k) => (formDireccion[k] = ""));
  editandoId.value = null;
}

async function cargarDirecciones() {
  cargandoDirecciones.value = true;
  const { ok, data } = await apiFetch(`/usuarios/${sesion.value.id_usuario}/direcciones`);
  cargandoDirecciones.value = false;
  if (!ok || !Array.isArray(data)) {
    toast(data?.error || "No se pudieron cargar tus direcciones.", "error");
    return;
  }
  direcciones.value = data;
}

function abrirNuevaDireccion() {
  limpiarFormDireccion();
  mostrarFormDireccion.value = true;
}

function editarDireccion(d) {
  editandoId.value = d.id_direccion;
  formDireccion.direccion_linea1 = d.direccion_linea1;
  formDireccion.direccion_linea2 = d.direccion_linea2 || "";
  formDireccion.ciudad = d.ciudad;
  formDireccion.departamento_estado = d.departamento_estado;
  formDireccion.codigo_postal = d.codigo_postal;
  mostrarFormDireccion.value = true;
}

function cancelarFormDireccion() {
  limpiarFormDireccion();
  mostrarFormDireccion.value = false;
}

async function guardarDireccion() {
  const payload = { ...formDireccion };
  if (!payload.direccion_linea2.trim()) delete payload.direccion_linea2;

  const ruta = editandoId.value
    ? `/usuarios/${sesion.value.id_usuario}/direcciones/${editandoId.value}`
    : `/usuarios/${sesion.value.id_usuario}/direcciones`;

  guardandoDireccion.value = true;
  const { ok, data } = await apiFetch(ruta, {
    method: editandoId.value ? "PUT" : "POST",
    body: JSON.stringify(payload),
  });
  guardandoDireccion.value = false;

  if (!ok) {
    toast(data?.error || "No se pudo guardar la dirección.", "error");
    return;
  }

  if (editandoId.value) {
    const idx = direcciones.value.findIndex((d) => d.id_direccion === editandoId.value);
    if (idx !== -1) direcciones.value[idx] = data;
    toast("Dirección actualizada.", "success");
  } else {
    direcciones.value.push(data);
    toast("Dirección agregada.", "success");
  }
  cancelarFormDireccion();
}

async function eliminarDireccion(d) {
  if (!confirm(`¿Eliminar la dirección "${d.direccion_linea1}"?`)) return;

  const { ok, data } = await apiFetch(`/usuarios/${sesion.value.id_usuario}/direcciones/${d.id_direccion}`, {
    method: "DELETE",
  });
  if (!ok) {
    toast(data?.error || "No se pudo eliminar la dirección.", "error");
    return;
  }
  direcciones.value = direcciones.value.filter((x) => x.id_direccion !== d.id_direccion);
  toast("Dirección eliminada.", "success");
}

function textoDireccion(d) {
  return [d.direccion_linea1, d.direccion_linea2, d.ciudad, d.departamento_estado].filter(Boolean).join(", ");
}

onMounted(() => {
  cargarPedidos();
  cargarDirecciones();
});
</script>

<template>
  <section class="pt-6 pb-16">
    <div class="pt-6 pb-8">
      <p class="text-xs font-semibold uppercase tracking-[0.2em] text-neutral-400 mb-3">Mi cuenta</p>
      <h2 class="text-5xl sm:text-6xl font-extrabold text-neutral-950 tracking-tighter leading-[0.95]">Hola, {{ sesion.nombre }}</h2>
    </div>

    <div class="flex gap-1 border-b border-neutral-200 mb-8">
      <button
        @click="seccionActiva = 'pedidos'"
        :class="['px-4 py-2.5 text-sm font-semibold tracking-tight transition border-b-2 -mb-px', seccionActiva === 'pedidos' ? 'border-accent text-neutral-950' : 'border-transparent text-neutral-400 hover:text-neutral-700']"
      >Mis pedidos</button>
      <button
        @click="seccionActiva = 'perfil'"
        :class="['px-4 py-2.5 text-sm font-semibold tracking-tight transition border-b-2 -mb-px', seccionActiva === 'perfil' ? 'border-accent text-neutral-950' : 'border-transparent text-neutral-400 hover:text-neutral-700']"
      >Editar perfil</button>
      <button
        @click="seccionActiva = 'direcciones'"
        :class="['px-4 py-2.5 text-sm font-semibold tracking-tight transition border-b-2 -mb-px', seccionActiva === 'direcciones' ? 'border-accent text-neutral-950' : 'border-transparent text-neutral-400 hover:text-neutral-700']"
      >Mis direcciones</button>
    </div>

    <!-- Mis pedidos -->
    <div v-if="seccionActiva === 'pedidos'">
      <div class="grid grid-cols-2 gap-4 mb-6 max-w-md">
        <div class="bg-white p-5 rounded-2xl border border-neutral-200">
          <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Total gastado</p>
          <p class="text-2xl font-extrabold text-neutral-950">Q{{ resumenPedidos.total_gastado.toFixed(2) }}</p>
        </div>
        <div class="bg-white p-5 rounded-2xl border border-neutral-200">
          <p class="text-[11px] uppercase tracking-wide text-neutral-400 font-bold mb-1">Pedidos realizados</p>
          <p class="text-2xl font-extrabold text-neutral-950">{{ resumenPedidos.numero_pedidos }}</p>
        </div>
      </div>

      <p v-if="cargandoPedidos" class="text-sm text-neutral-500 py-4">Cargando tus pedidos...</p>
      <p v-else-if="pedidos.length === 0" class="text-sm text-neutral-400 py-4">Aún no tienes pedidos.</p>

      <div v-else class="divide-y divide-neutral-200 border-t border-b border-neutral-200">
        <div v-for="p in pedidos" :key="p.id_pedido">
          <button @click="alternarPedido(p.id_pedido)" class="w-full py-4 flex items-center gap-4 text-left">
            <span class="text-neutral-400 font-mono text-xs w-16 shrink-0">#{{ p.id_pedido }}</span>
            <span class="text-sm text-neutral-500 flex-1 min-w-0">{{ formatearFecha(p.fecha_pedido) }}</span>
            <span :class="['text-[10px] font-bold uppercase px-2 py-0.5 rounded-full shrink-0', ESTILO_ESTADO[p.estado] || 'bg-neutral-100 text-neutral-700']">{{ p.estado }}</span>
            <span class="font-semibold text-neutral-950 text-sm w-24 text-right shrink-0">Q{{ p.total.toFixed(2) }}</span>
            <span class="text-neutral-400 text-xs w-4 shrink-0">{{ pedidoExpandido === p.id_pedido ? "▲" : "▼" }}</span>
          </button>

          <div v-if="pedidoExpandido === p.id_pedido" class="pb-4 pl-20 pr-4">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
                  <th class="py-1.5 pr-2">Producto</th>
                  <th class="py-1.5 px-2 text-right">Cantidad</th>
                  <th class="py-1.5 px-2 text-right">Precio</th>
                  <th class="py-1.5 pl-2 text-right">Subtotal</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(l, i) in p.lineas" :key="i" class="border-b border-neutral-50 last:border-0">
                  <td class="py-1.5 pr-2 text-neutral-950">{{ l.nombre_producto_historico }}</td>
                  <td class="py-1.5 px-2 text-right text-neutral-700">{{ l.cantidad }}</td>
                  <td class="py-1.5 px-2 text-right text-neutral-500">Q{{ l.precio_unitario_historico.toFixed(2) }}</td>
                  <td class="py-1.5 pl-2 text-right font-semibold text-neutral-950">Q{{ l.subtotal.toFixed(2) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Editar perfil -->
    <div v-else-if="seccionActiva === 'perfil'" class="max-w-sm">
      <form @submit.prevent="guardarPerfil" class="space-y-5">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Nombre</label>
          <input v-model="formularioPerfil.nombre" required class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Teléfono</label>
          <input v-model="formularioPerfil.telefono" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Correo electrónico</label>
          <input :value="sesion.email" disabled class="w-full border-0 border-b border-neutral-200 py-2 text-sm bg-transparent text-neutral-400 cursor-not-allowed">
        </div>

        <div class="border border-neutral-200 rounded-2xl p-4">
          <button type="button" @click="mostrarCambioPassword = !mostrarCambioPassword" class="text-xs font-semibold text-accent hover:underline">
            {{ mostrarCambioPassword ? "Cancelar cambio de contraseña" : "Cambiar contraseña" }}
          </button>

          <div v-if="mostrarCambioPassword" class="space-y-4 mt-4">
            <input v-model="passwordActual" type="password" placeholder="Contraseña actual" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
            <input v-model="passwordNueva" type="password" placeholder="Contraseña nueva (mínimo 8 caracteres)" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
            <input v-model="passwordConfirmar" type="password" placeholder="Confirmar contraseña nueva" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
          </div>
        </div>

        <button type="submit" :disabled="guardandoPerfil" class="w-full py-3 mt-2 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 text-white font-semibold rounded-full text-sm transition">
          {{ guardandoPerfil ? "Guardando..." : "Guardar cambios" }}
        </button>
      </form>
    </div>

    <!-- Mis direcciones -->
    <div v-else-if="seccionActiva === 'direcciones'" class="max-w-sm">
      <p v-if="cargandoDirecciones" class="text-sm text-neutral-500 py-2">Cargando direcciones...</p>

      <template v-else>
        <div v-if="direcciones.length === 0" class="text-sm text-neutral-400 py-2 mb-4">No tienes direcciones registradas.</div>

        <div v-else class="space-y-3 mb-6">
          <div v-for="d in direcciones" :key="d.id_direccion" class="border border-neutral-200 rounded-2xl p-4 flex items-start gap-3">
            <div class="flex-1 min-w-0">
              <p class="text-sm text-neutral-950">{{ textoDireccion(d) }}</p>
              <p class="text-xs text-neutral-400 mt-0.5">{{ d.codigo_postal }}{{ d.es_principal ? " · Principal" : "" }}</p>
            </div>
            <div class="flex gap-2 shrink-0">
              <button @click="editarDireccion(d)" class="text-xs font-semibold text-accent hover:underline">Editar</button>
              <button @click="eliminarDireccion(d)" class="text-xs font-semibold text-red-600 hover:underline">Eliminar</button>
            </div>
          </div>
        </div>

        <p v-if="direcciones.length >= 3 && !editandoId" class="text-sm text-neutral-400">Ya tienes el máximo de 3 direcciones.</p>

        <button
          v-if="!mostrarFormDireccion && direcciones.length < 3"
          type="button"
          @click="abrirNuevaDireccion"
          class="text-xs font-semibold text-accent hover:underline"
        >Agregar dirección</button>

        <form
          v-if="mostrarFormDireccion"
          @submit.prevent="guardarDireccion"
          class="space-y-4 border border-neutral-200 rounded-2xl p-4 mt-4"
        >
          <p class="text-xs font-semibold uppercase tracking-wide text-neutral-400">{{ editandoId ? "Editar dirección" : "Nueva dirección" }}</p>
          <input v-model="formDireccion.direccion_linea1" required placeholder="Dirección (línea 1)" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
          <input v-model="formDireccion.direccion_linea2" placeholder="Apartamento, piso, referencia (opcional)" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
          <div class="grid grid-cols-2 gap-4">
            <input v-model="formDireccion.ciudad" required placeholder="Ciudad" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
            <input v-model="formDireccion.departamento_estado" required placeholder="Departamento" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
          </div>
          <input v-model="formDireccion.codigo_postal" required placeholder="Código postal" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
          <div class="flex gap-2 pt-1">
            <button type="submit" :disabled="guardandoDireccion" class="flex-1 py-2 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 text-white font-semibold rounded-full text-xs transition">
              {{ guardandoDireccion ? "Guardando..." : "Guardar dirección" }}
            </button>
            <button type="button" @click="cancelarFormDireccion" class="px-4 py-2 border border-neutral-200 hover:bg-neutral-50 text-neutral-700 font-semibold rounded-full text-xs transition">
              Cancelar
            </button>
          </div>
        </form>
      </template>
    </div>
  </section>
</template>
