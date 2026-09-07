<script setup>
import { ref } from "vue";
import { apiFetch } from "../../services/api";
import { useToast } from "../../composables/useToast";

const emit = defineEmits(["exito"]);

const { toast } = useToast();

const nombre = ref("");
const email = ref("");
const password = ref("");
const telefono = ref("");

async function registrarUsuario() {
  const payload = {
    nombre: nombre.value,
    email: email.value,
    password: password.value,
    telefono: telefono.value,
    // Sin selector de rol: el autorregistro público siempre crea cuentas de "comprador".
    // Los roles de vendedor/administrador se asignan desde el Panel Admin.
  };

  const { ok, data } = await apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  if (ok) {
    toast("Cuenta creada con éxito. Ahora puedes iniciar sesión.", "success");
    emit("exito");
  } else {
    toast(data.error || "No se pudo crear la cuenta.", "error");
  }
}
</script>

<template>
  <section class="max-w-sm mx-auto mt-16">
    <h2 class="text-3xl font-extrabold text-neutral-950 tracking-tight mb-1">Crear cuenta</h2>
    <p class="text-sm text-neutral-500 mb-8">Alta de comprador con hash seguro en PostgreSQL</p>

    <form @submit.prevent="registrarUsuario" class="space-y-5">
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Nombre completo</label>
        <input type="text" v-model="nombre" required placeholder="Ej: Juan Pérez" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Correo electrónico</label>
        <input type="email" v-model="email" required placeholder="juan@ejemplo.com" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Contraseña</label>
        <input type="password" v-model="password" required placeholder="••••••••" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Teléfono</label>
        <input type="text" v-model="telefono" placeholder="+502..." class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>
      <button type="submit" class="w-full py-3 mt-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition">Crear cuenta</button>
    </form>
  </section>
</template>
