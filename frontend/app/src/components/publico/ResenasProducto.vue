<script setup>
import { ref, watch } from "vue";
import { apiFetch } from "../../services/api";
import { useSesion } from "../../composables/useSesion";
import { useToast } from "../../composables/useToast";

const props = defineProps({
  productoId: { type: String, required: true },
});

const { sesion } = useSesion();
const { toast } = useToast();

const resenas = ref([]);
const resumen = ref({ promedio: 0, total: 0 });
const cargando = ref(true);

const calificacionNueva = ref(5);
const textoNuevo = ref("");
const enviando = ref(false);

async function cargarResenas(id) {
  cargando.value = true;
  const { ok, data } = await apiFetch(`/resenas/${id}`);
  cargando.value = false;

  if (!ok) {
    toast(data?.error || "No se pudieron cargar las reseñas.", "error");
    return;
  }
  resenas.value = data.resenas || [];
  resumen.value = data.resumen || { promedio: 0, total: 0 };
}

watch(() => props.productoId, (id) => id && cargarResenas(id), { immediate: true });

function formatearFecha(iso) {
  return new Date(iso).toLocaleString("es-GT", { dateStyle: "long", timeStyle: "short", timeZone: "America/Guatemala" });
}

async function enviarResena() {
  if (!textoNuevo.value.trim()) return;
  enviando.value = true;
  const { ok, status, data } = await apiFetch("/resenas", {
    method: "POST",
    body: JSON.stringify({
      producto_id: props.productoId,
      id_usuario: sesion.value.id_usuario,
      nombre_autor: sesion.value.nombre,
      rol_solicitante: "comprador",
      calificacion: calificacionNueva.value,
      texto: textoNuevo.value.trim(),
    }),
  });
  enviando.value = false;

  if (ok) {
    toast("Reseña publicada", "success");
    calificacionNueva.value = 5;
    textoNuevo.value = "";
    await cargarResenas(props.productoId);
  } else if (status === 409) {
    toast("Ya reseñaste este producto", "error");
  } else {
    toast(data?.error || "No se pudo publicar la reseña.", "error");
  }
}
</script>

<template>
  <section id="resenas" class="pt-6 pb-16 scroll-mt-20">
    <p class="text-xs uppercase tracking-[0.2em] text-neutral-400">Opiniones</p>
    <h2 class="text-3xl font-extrabold tracking-tighter text-neutral-950 mt-1 mb-6">Reseñas de este producto</h2>

    <div v-if="!cargando" class="flex items-center gap-3 mb-8">
      <p class="text-2xl font-extrabold text-neutral-950">{{ resumen.promedio || 0 }} <span class="text-amber-500">★</span></p>
      <p class="text-sm text-neutral-500">{{ resumen.total }} {{ resumen.total === 1 ? "reseña" : "reseñas" }}</p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-10">
      <div class="lg:col-span-2 space-y-6">
        <p v-if="cargando" class="text-sm text-neutral-400">Cargando reseñas…</p>
        <p v-else-if="resenas.length === 0" class="text-sm text-neutral-400">Este producto todavía no tiene reseñas.</p>
        <div v-for="r in resenas" :key="r._id" class="border-b border-neutral-100 pb-6">
          <div class="flex items-center gap-2 mb-1 flex-wrap">
            <p class="text-sm font-semibold text-neutral-950">{{ r.autor.nombre }}</p>
            <span class="text-amber-500 text-sm">{{ "★".repeat(r.calificacion) }}<span class="text-neutral-200">{{ "★".repeat(5 - r.calificacion) }}</span></span>
            <span v-if="r.verificada_compra" class="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">Compra verificada</span>
          </div>
          <p class="text-sm text-neutral-600 leading-relaxed mb-1">{{ r.texto }}</p>
          <p class="text-xs text-neutral-400">{{ formatearFecha(r.fecha_creacion) }}</p>
        </div>
      </div>

      <div id="escribir-resena" class="scroll-mt-24">
        <div v-if="!sesion" class="text-sm text-neutral-500">
          Debes iniciar sesión como comprador para escribir una reseña.
        </div>
        <div v-else-if="sesion.rol !== 'comprador'" class="text-sm text-neutral-500">
          Solo una cuenta con rol "comprador" puede escribir una reseña.
        </div>
        <form v-else @submit.prevent="enviarResena" class="space-y-4">
          <h3 class="text-sm font-bold text-neutral-950">Escribe tu reseña</h3>
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Calificación</label>
            <select v-model.number="calificacionNueva" class="w-full border-0 border-b border-neutral-300 py-2 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent">
              <option v-for="n in [5, 4, 3, 2, 1]" :key="n" :value="n">{{ n }} estrella{{ n === 1 ? "" : "s" }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">Comentario</label>
            <textarea
              v-model="textoNuevo" maxlength="1000" rows="4" required
              placeholder="Cuéntanos tu experiencia con este producto"
              class="w-full border border-neutral-300 rounded-xl p-3 text-sm focus:ring-0 focus:border-accent outline-none transition bg-transparent resize-none"
            ></textarea>
            <p class="text-[11px] text-neutral-400 text-right mt-1">{{ textoNuevo.length }}/1000</p>
          </div>
          <button type="submit" :disabled="enviando" class="w-full py-3 bg-neutral-950 hover:bg-neutral-800 disabled:opacity-50 text-white font-semibold rounded-full text-sm transition">
            {{ enviando ? "Publicando..." : "Publicar reseña" }}
          </button>
        </form>
      </div>
    </div>
  </section>
</template>
