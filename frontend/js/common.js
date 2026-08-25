const API_URL = "http://127.0.0.1:8000/api";

function getSesion() {
  try {
    return JSON.parse(localStorage.getItem("usuario_tiendaya"));
  } catch {
    return null;
  }
}

function setSesion(usuario) {
  localStorage.setItem("usuario_tiendaya", JSON.stringify(usuario));
}

function limpiarSesion() {
  localStorage.removeItem("usuario_tiendaya");
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

// --- Miniaturas ilustradas por categoría (las URLs de imagen de la semilla apuntan a un CDN ficticio) ---
const ICONOS_SVG = {
  laptop: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M2 18h20l-1.4 2.3a1 1 0 0 1-.86.7H4.26a1 1 0 0 1-.86-.7L2 18z"/></svg>',
  monitor: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4"/></svg>',
  camisa: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3 4 7l3 3v11h10V10l3-3-4-4-2 2h-4L8 3Z"/></svg>',
  generico: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="1.5"/><path d="m21 15-5-5L4 21"/></svg>'
};

const VISUAL_CATEGORIA = {
  2: { icono: "laptop", gradiente: "from-indigo-500 to-blue-600" },
  3: { icono: "monitor", gradiente: "from-sky-500 to-cyan-600" },
  5: { icono: "camisa", gradiente: "from-fuchsia-500 to-pink-600" }
};

function categoriaVisual(idCategoria) {
  const v = VISUAL_CATEGORIA[idCategoria] || { icono: "generico", gradiente: "from-slate-400 to-slate-600" };
  return { ...v, svg: ICONOS_SVG[v.icono] };
}

function miniaturaCategoriaHtml(idCategoria, alturaClase = "h-36") {
  const { svg, gradiente } = categoriaVisual(idCategoria);
  return `<div class="${alturaClase} w-full bg-gradient-to-br ${gradiente} flex items-center justify-center text-white/90">
    <div class="w-12 h-12">${svg}</div>
  </div>`;
}

// --- Notificaciones (toast) ---
function toast(mensaje, tipo = "info") {
  const contenedor = document.getElementById("toast-container");
  if (!contenedor) {
    alert(mensaje);
    return;
  }
  const estilos = {
    success: "bg-emerald-600",
    error: "bg-red-600",
    info: "bg-slate-800"
  };
  const el = document.createElement("div");
  el.className = `${estilos[tipo] || estilos.info} text-white text-sm font-medium px-4 py-3 rounded-lg shadow-lg max-w-xs transition-all duration-300 opacity-0 translate-y-2`;
  el.textContent = mensaje;
  contenedor.appendChild(el);

  requestAnimationFrame(() => el.classList.remove("opacity-0", "translate-y-2"));
  setTimeout(() => {
    el.classList.add("opacity-0", "translate-y-2");
    setTimeout(() => el.remove(), 300);
  }, 3800);
}
