<script setup>
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";

const { setSesion } = useSesion();

const email = ref("");
const password = ref("");
const error = ref("");

async function iniciarSesion() {
  const { ok, data } = await apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: email.value, password: password.value }),
  });

  if (!ok) {
    error.value = data.error || "No se pudo iniciar sesión.";
    return;
  }

  if (!["administrador", "vendedor"].includes(data.usuario.rol)) {
    error.value = "Esta cuenta no tiene permisos de administrador ni de vendedor.";
    return;
  }

  error.value = "";
  setSesion(data.usuario);
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-4">
    <section class="max-w-sm w-full">
      <div class="flex items-center gap-2.5 mb-8">
        <div class="w-9 h-9 rounded-lg bg-neutral-950 text-white flex items-center justify-center font-extrabold text-sm">TY</div>
        <div>
          <h2 class="text-lg font-extrabold text-neutral-950 leading-none">Acceso administrativo</h2>
          <p class="text-xs text-neutral-400 mt-1">Cuentas con rol de administrador o vendedor</p>
        </div>
      </div>

      <p v-if="error" class="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3 mb-4">{{ error }}</p>

      <form @submit.prevent="iniciarSesion" class="space-y-5">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Correo electrónico</label>
          <input type="email" v-model="email" required placeholder="admin@tiendaya.com" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <div>
          <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Contraseña</label>
          <input type="password" v-model="password" required placeholder="••••••••" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
        </div>
        <button type="submit" class="w-full py-3 mt-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition">Entrar</button>
      </form>
      <RouterLink to="/" class="block text-center text-sm text-neutral-500 hover:text-neutral-700 mt-6">← Volver al sitio público</RouterLink>
    </section>
  </div>
</template>
