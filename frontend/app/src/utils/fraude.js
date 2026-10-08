export const ESTILO_NIVEL = {
  alto: "bg-red-100 text-red-800 border-red-200",
  medio: "bg-amber-100 text-amber-800 border-amber-200",
  bajo: "bg-neutral-100 text-neutral-700 border-neutral-200",
};

export const ETIQUETA_NIVEL = { alto: "Alto", medio: "Medio", bajo: "Bajo" };

export const ANILLOS = "anillos_resenas";

export const FRASE_PATRON = {
  [ANILLOS]: "Tríos de cuentas que se ponen 5★ en los mismos productos en pocas horas.",
  cuenta_rafaga: "Muchas reseñas en muy poco tiempo, casi todas sin compra.",
  grupo_coordinado: "Varias cuentas califican igual los mismos productos casi a la vez.",
  sesgo_vendedor_sin_compra: "Solo 5★ o solo 1-2★ a una tienda a la que nunca le compró.",
  cuentas_vinculadas: "Cuentas con la misma dirección que califican igual.",
};

const ETIQUETAS_PARAMETRO = {
  min_resenas: "Mínimo de reseñas",
  ventana_segundos: "Ventana de tiempo (segundos)",
  min_pct_sin_compra: "Mínimo % de reseñas sin compra",
  min_cuentas: "Mínimo de cuentas en el grupo",
  min_productos_compartidos: "Mínimo de productos en común",
};

const ETIQUETAS_EVIDENCIA = {
  signo: "Tipo de reseñas",
  tamano: "Cuentas en el grupo",
  resenas: "Reseñas en la ráfaga",
  resenas_sin_compra: "Sin compra verificada",
  sin_compra_pct: "Porcentaje sin compra",
  distribucion_calificaciones: "Calificaciones dadas",
  inicio: "Primera reseña de la ráfaga",
  ventana_real_minutos: "Tiempo entre la primera y la última",
  ventana_maxima_minutos: "Ventana máxima buscada",
  enlaces: "Parejas que coinciden",
  densidad_pct: "Parejas que coinciden (de las posibles)",
  productos_en_comun: "Productos en común",
  resenas_sin_compra_pct: "Porcentaje sin compra",
  resenas_extremas_sin_compra: "Reseñas extremas sin compra",
  calificaciones: "Calificaciones dadas",
  resenas_al_vendedor: "Reseñas a esta tienda",
  resenas_totales_cuenta: "Reseñas totales de la cuenta",
  concentracion_pct: "De sus reseñas, a esta tienda",
  periodo_dias: "Período que cubren",
  ciudad: "Ciudad",
  departamento: "Departamento",
  cuentas_en_direccion: "Cuentas en la dirección",
  max_productos_en_comun: "Máximo de productos en común",
  calificaciones_coincidentes: "Calificaciones coincidentes",
  pares: "Coincidencias por pareja",
};

const ORDEN_EVIDENCIA = Object.keys(ETIQUETAS_EVIDENCIA);

export function ordenarEvidencia(evidencia) {
  const posicion = (clave) => (ORDEN_EVIDENCIA.includes(clave) ? ORDEN_EVIDENCIA.indexOf(clave) : ORDEN_EVIDENCIA.length);
  return Object.entries(evidencia || {}).sort(([a], [b]) => posicion(a) - posicion(b));
}

const SIGNOS = { positivo: "Reseñas buenas (5★)", negativo: "Reseñas malas (1-2★)" };

const FECHA_ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

function capitalizar(texto) {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function etiquetaParametro(clave) {
  return ETIQUETAS_PARAMETRO[clave] || capitalizar(clave.replace(/_/g, " "));
}

export function etiquetaEvidencia(clave) {
  return ETIQUETAS_EVIDENCIA[clave] || capitalizar(clave.replace(/_/g, " "));
}

function numero(n) {
  return Number(n).toLocaleString("es-GT", { maximumFractionDigits: 1 });
}

function valorLegible(valor) {
  if (valor === null || valor === undefined || valor === "") return "—";
  if (typeof valor === "boolean") return valor ? "Sí" : "No";
  if (typeof valor === "number") return numero(valor);
  if (typeof valor === "string" && FECHA_ISO.test(valor)) {
    const fecha = new Date(valor);
    if (!Number.isNaN(fecha.getTime())) return fecha.toLocaleString("es-GT", { dateStyle: "medium", timeStyle: "short" });
  }
  if (Array.isArray(valor)) return valor.map(valorLegible).join(", ") || "—";
  return String(valor);
}

function minutosLegibles(minutos) {
  const m = Number(minutos);
  if (!Number.isFinite(m)) return valorLegible(minutos);
  if (m === 0) return "0 min";
  if (m < 1) return `${numero(m * 60)} s`;
  if (m < 120) return `${numero(m)} min`;
  if (m < 2880) return `${numero(m / 60)} h`;
  return `${numero(m / 1440)} días`;
}

function conteoEstrellas(conteos) {
  return Object.entries(conteos)
    .filter(([, n]) => n > 0)
    .sort(([a], [b]) => Number(b) - Number(a))
    .map(([estrellas, n]) => `${estrellas}★ × ${n}`)
    .join(" · ") || "—";
}

export function valorEvidencia(clave, valor) {
  if (valor === null || valor === undefined) return "—";
  if (clave.endsWith("_minutos")) return minutosLegibles(valor);
  if (clave.endsWith("_pct")) return `${valorLegible(valor)}%`;
  if (clave === "periodo_dias") return `${numero(valor)} ${Number(valor) === 1 ? "día" : "días"}`;
  if (clave === "signo") return SIGNOS[valor] || valorLegible(valor);
  if (clave === "distribucion_calificaciones" && typeof valor === "object") return conteoEstrellas(valor);
  if (clave === "calificaciones" && Array.isArray(valor)) {
    const conteos = {};
    valor.forEach((c) => (conteos[c] = (conteos[c] || 0) + 1));
    return conteoEstrellas(conteos);
  }
  if (clave === "calificaciones_coincidentes" && Array.isArray(valor)) return valor.map((c) => `${c}★`).join(", ") || "—";
  return valorLegible(valor);
}

export function duracionLegible(segundos) {
  const s = Number(segundos);
  if (!Number.isFinite(s) || s <= 0) return "";
  if (s % 86400 === 0) return `${s / 86400} día(s)`;
  if (s >= 3600) return `${numero(s / 3600)} h`;
  if (s % 60 === 0) return `${s / 60} min`;
  return `${s} s`;
}

export function mensajeErrorFraude(status, data, porDefecto) {
  if (status === 503 || data?.codigo === "GRAFO_NO_DISPONIBLE") return "El grafo de fraude no está disponible (Neo4j no responde). Intenta de nuevo en unos segundos.";
  if (status === 0) return data?.error || "No se pudo conectar con el servidor.";
  return data?.error || porDefecto;
}
