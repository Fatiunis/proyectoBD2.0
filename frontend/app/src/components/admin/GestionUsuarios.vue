<script setup>
import { ref, onMounted } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";
import ModalAdmin from "./ModalAdmin.vue";

const { sesion } = useSesion();
const { toast } = useToast();

const ROLES_DISPONIBLES = ["comprador", "vendedor", "administrador"];

const usuarios = ref([]);
const idEnEdicion = ref(null);
const rolSeleccionadoEdicion = ref("");

async function cargarUsuarios() {
  const { ok, data } = await apiFetch("/usuarios");
  if (!ok) {
    toast(data.error || "No se pudieron cargar los usuarios.", "error");
    return;
  }
  usuarios.value = data;
  idEnEdicion.value = null;
}

function editarRol(u) {
  idEnEdicion.value = u.id_usuario;
  rolSeleccionadoEdicion.value = u.rol;
}

function cancelarEdicion() {
  idEnEdicion.value = null;
}

async function guardarRol(id) {
  const { ok, data } = await apiFetch(`/usuarios/${id}`, {
    method: "PUT",
    body: JSON.stringify({ rol: rolSeleccionadoEdicion.value, rol_solicitante: sesion.value.rol }),
  });

  if (ok) {
    toast(`Rol actualizado a "${rolSeleccionadoEdicion.value}".`, "success");
    if (id === sesion.value.id_usuario && rolSeleccionadoEdicion.value !== sesion.value.rol) {
      toast("Cambiaste tu propio rol; vuelve a iniciar sesión para reflejarlo en el panel.", "info");
    }
    idEnEdicion.value = null;
    cargarUsuarios();
  } else {
    toast(data.error || "No se pudo actualizar el rol.", "error");
  }
}

const mostrarModalCrear = ref(false);
const nombreNuevo = ref("");
const emailNuevo = ref("");
const passwordNuevo = ref("");
const rolNuevo = ref("comprador");
const telefonoNuevo = ref("");

async function crearUsuario() {
  const payload = {
    nombre: nombreNuevo.value,
    email: emailNuevo.value,
    password: passwordNuevo.value,
    rol: rolNuevo.value,
    telefono: telefonoNuevo.value,
  };

  const { ok, data } = await apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  if (ok) {
    toast(`Usuario "${payload.nombre}" creado con rol ${payload.rol}.`, "success");
    nombreNuevo.value = "";
    emailNuevo.value = "";
    passwordNuevo.value = "";
    rolNuevo.value = "comprador";
    telefonoNuevo.value = "";
    mostrarModalCrear.value = false;
    cargarUsuarios();
  } else {
    toast(data.error || "No se pudo crear el usuario.", "error");
  }
}

function formatearFecha(iso) {
  return new Date(iso).toLocaleString("es-GT", { dateStyle: "long", timeStyle: "short" });
}

onMounted(cargarUsuarios);
</script>

<template>
  <div>
    <div class="flex justify-between items-start mb-6">
      <div>
        <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mb-1">Usuarios</h2>
        <p class="text-sm text-neutral-500">Gestión de cuentas y roles en PostgreSQL</p>
      </div>
      <button @click="mostrarModalCrear = true" class="px-4 py-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition">+ Nuevo usuario</button>
    </div>

    <div class="flex-1 min-w-0 bg-white p-5 rounded-2xl border border-neutral-200">
      <div class="overflow-x-auto lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto scrollbar-fina">
        <table class="w-full text-sm">
          <thead class="sticky top-0 bg-white z-10">
            <tr class="text-left text-[11px] uppercase tracking-wide text-neutral-400 border-b border-neutral-100">
              <th class="p-2.5">ID</th>
              <th class="p-2.5">Nombre</th>
              <th class="p-2.5">Correo</th>
              <th class="p-2.5">Teléfono</th>
              <th class="p-2.5">Rol</th>
              <th class="p-2.5">Registrado</th>
              <th class="p-2.5"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="usuarios.length === 0">
              <td colspan="7" class="p-6 text-center text-sm text-neutral-400">No hay usuarios registrados.</td>
            </tr>
            <tr v-for="u in usuarios" :key="u.id_usuario" class="border-b border-neutral-100 hover:bg-neutral-50/80 transition">
              <td class="p-2.5 text-neutral-400 font-mono text-xs">{{ u.id_usuario }}</td>
              <td class="p-2.5 font-medium text-neutral-950">{{ u.nombre }}</td>
              <td class="p-2.5 text-neutral-500 text-xs">{{ u.email }}</td>
              <td class="p-2.5 text-neutral-500 text-xs">{{ u.telefono || "—" }}</td>
              <td class="p-2.5">
                <select
                  v-if="idEnEdicion === u.id_usuario"
                  v-model="rolSeleccionadoEdicion"
                  class="border border-neutral-300 p-1.5 rounded-lg bg-white text-xs focus:ring-2 focus:ring-accent-600 focus:border-accent-600 outline-none transition"
                >
                  <option v-for="r in ROLES_DISPONIBLES" :key="r" :value="r">{{ r }}</option>
                </select>
                <span v-else class="text-[10px] font-bold uppercase px-2 py-0.5 bg-accent-50 text-accent-700 rounded-full">{{ u.rol }}</span>
              </td>
              <td class="p-2.5 text-xs text-neutral-500">{{ formatearFecha(u.fecha_registro) }}</td>
              <td class="p-2.5 text-right whitespace-nowrap">
                <template v-if="idEnEdicion === u.id_usuario">
                  <button @click="guardarRol(u.id_usuario)" class="px-2.5 py-1 bg-neutral-950 hover:bg-neutral-800 text-white text-xs font-semibold rounded-full transition mr-1.5">Guardar</button>
                  <button @click="cancelarEdicion" class="px-2.5 py-1 border border-neutral-300 hover:border-neutral-500 text-neutral-600 text-xs font-semibold rounded-full transition">Cancelar</button>
                </template>
                <button v-else @click="editarRol(u)" class="px-2.5 py-1 border border-neutral-300 hover:border-neutral-500 text-neutral-700 text-xs font-semibold rounded-full transition">Cambiar rol</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <ModalAdmin :abierto="mostrarModalCrear" titulo="Crear nuevo usuario" @cerrar="mostrarModalCrear = false">
      <form @submit.prevent="crearUsuario" class="space-y-5">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Nombre completo</label>
          <input type="text" v-model="nombreNuevo" required class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Correo electrónico</label>
          <input type="email" v-model="emailNuevo" required class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Contraseña</label>
          <input type="password" v-model="passwordNuevo" required class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Rol</label>
            <select v-model="rolNuevo" class="w-full border-0 border-b border-neutral-300 py-2 bg-transparent text-sm focus:ring-0 focus:border-accent outline-none transition">
              <option value="comprador">Comprador</option>
              <option value="vendedor">Vendedor</option>
              <option value="administrador">Administrador</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Teléfono</label>
            <input type="text" v-model="telefonoNuevo" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
          </div>
        </div>
        <button type="submit" class="w-full py-3 mt-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition">Crear usuario</button>
      </form>
    </ModalAdmin>
  </div>
</template>
