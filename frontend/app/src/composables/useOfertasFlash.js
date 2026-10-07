import { ref, computed, onMounted, onUnmounted } from "vue";
import { apiFetch } from "../services/api";

const RECARGA_MS = 20000;

const ofertas = ref([]);
const total = ref(0);
const cargado = ref(false);
const fallo = ref(false);
const ahora = ref(Date.now());
const limiteCargado = ref(0);

// Cada componente montado pide un límite; la lista se pide una sola vez con
// el mayor de ellos, así la barra, la franja y la sección comparten la misma
// petición y los mismos intervalos.
const suscriptores = new Map();
let siguienteId = 0;
let reloj = null;
let recarga = null;
let cargaProgramada = null;
let consultaVigente = 0;

function limiteActual() {
  return Math.min(100, Math.max(1, ...suscriptores.values()));
}

async function cargarOfertas() {
  if (!suscriptores.size) return;
  const consulta = ++consultaVigente;
  const limite = limiteActual();
  const { ok, data } = await apiFetch(`/ofertas?limite=${limite}`);
  if (consulta !== consultaVigente) return;
  if (!ok || !Array.isArray(data?.ofertas)) {
    fallo.value = true;
    cargado.value = true;
    return;
  }
  // segundos_restantes se convierte a un instante absoluto al recibirlo para
  // que la cuenta regresiva avance con el reloj local entre recargas.
  const recibido = Date.now();
  ofertas.value = data.ofertas.map((o) => ({
    ...o,
    finMs: o.segundos_restantes == null ? Infinity : recibido + o.segundos_restantes * 1000,
  }));
  total.value = data.total ?? data.ofertas.length;
  limiteCargado.value = limite;
  fallo.value = false;
  cargado.value = true;
  ahora.value = recibido;
}

function programarCarga() {
  // Agrupa en una sola petición los componentes que se montan en el mismo tick.
  if (cargaProgramada) return;
  cargaProgramada = setTimeout(() => {
    cargaProgramada = null;
    cargarOfertas();
  }, 0);
}

function arrancar() {
  reloj = setInterval(() => (ahora.value = Date.now()), 1000);
  recarga = setInterval(() => {
    if (!document.hidden) cargarOfertas();
  }, RECARGA_MS);
}

function detener() {
  clearInterval(reloj);
  clearInterval(recarga);
  clearTimeout(cargaProgramada);
  reloj = recarga = cargaProgramada = null;
}

export function useOfertasFlash({ limite = 12 } = {}) {
  const id = ++siguienteId;

  onMounted(() => {
    suscriptores.set(id, limite);
    if (suscriptores.size === 1) arrancar();
    if (!cargado.value || fallo.value || limiteCargado.value < limiteActual()) programarCarga();
  });

  onUnmounted(() => {
    suscriptores.delete(id);
    if (!suscriptores.size) detener();
  });

  // Lista lista para este componente: no basta con que otro suscriptor haya
  // cargado antes con un límite menor.
  const listo = computed(
    () => cargado.value && (fallo.value || limiteCargado.value >= limite || ofertas.value.length >= total.value)
  );

  return { ofertas, total, cargado, listo, fallo, ahora, recargar: cargarOfertas };
}

export function ofertaDisponible(o, ahoraMs = ahora.value) {
  return (o.stock_restante ?? 0) > 0 && !(Number.isFinite(o.finMs) && o.finMs <= ahoraMs);
}

// Lectura del estado ya cargado por quien esté suscrito (la franja, la barra):
// las tarjetas del catálogo lo consultan sin suscribirse ni pedir nada más.
const ofertasPorProducto = computed(() => new Map(ofertas.value.map((o) => [String(o.producto_id), o])));

export function ofertaActivaDe(productoId) {
  const o = ofertasPorProducto.value.get(String(productoId));
  return o && ofertaDisponible(o) ? o : null;
}
