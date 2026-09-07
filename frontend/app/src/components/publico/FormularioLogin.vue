<script setup>
import { ref } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";

const emit = defineEmits(["exito", "ir-a-registro"]);

const { setSesion } = useSesion();
const { toast } = useToast();

const email = ref("");
const password = ref("");

async function iniciarSesion() {
  const { ok, data } = await apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: email.value, password: password.value }),
  });

  if (ok) {
    setSesion(data.usuario);
    toast(`¡Bienvenido/a, ${data.usuario.nombre}!`, "success");
    emit("exito");
  } else {
    toast(data.error || "No se pudo iniciar sesión.", "error");
  }
}
</script>

<template>
  <section class="max-w-sm mx-auto mt-16">
    <h2 class="text-3xl font-extrabold text-neutral-950 tracking-tight mb-1">Iniciar sesión</h2>
    <p class="text-sm text-neutral-500 mb-8">Autenticación relacional sobre PostgreSQL</p>

    <form @submit.prevent="iniciarSesion" class="space-y-5">
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Correo electrónico</label>
        <input type="email" v-model="email" required placeholder="tu@correo.com" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Contraseña</label>
        <input type="password" v-model="password" required placeholder="••••••••" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
      </div>
      <button type="submit" class="w-full py-3 mt-2 bg-neutral-950 hover:bg-neutral-800 text-white font-semibold rounded-full text-sm transition">Entrar</button>
    </form>
    <p class="text-sm text-center text-neutral-500 mt-6">¿No tienes cuenta? <a href="#" @click.prevent="emit('ir-a-registro')" class="text-accent-700 font-semibold hover:underline">Regístrate aquí</a></p>
  </section>
</template>
