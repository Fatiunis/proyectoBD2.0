let sesionActual = getSesion();

function actualizarInterfazAuth() {
  const authBtns = document.getElementById("auth-buttons");
  const userProf = document.getElementById("user-profile");
  const userInfo = document.getElementById("user-info");
  const userRol = document.getElementById("user-rol");
  const userAvatar = document.getElementById("user-avatar");
  const linkAdmin = document.getElementById("link-admin");

  if (sesionActual) {
    authBtns.classList.add("hidden");
    userProf.classList.remove("hidden");
    userProf.classList.add("flex");
    userInfo.textContent = sesionActual.nombre;
    userRol.textContent = sesionActual.rol;
    userAvatar.textContent = sesionActual.nombre.trim().charAt(0).toUpperCase();
    linkAdmin.classList.toggle("hidden", !["administrador", "vendedor"].includes(sesionActual.rol));
  } else {
    authBtns.classList.remove("hidden");
    userProf.classList.add("hidden");
    userProf.classList.remove("flex");
    linkAdmin.classList.add("hidden");
  }
}

function mostrarVista(vista) {
  document.getElementById("vista-catalogo").classList.add("hidden");
  document.getElementById("vista-login").classList.add("hidden");
  document.getElementById("vista-registro").classList.add("hidden");

  document.getElementById(`vista-${vista}`).classList.remove("hidden");
  if (vista === "catalogo") cargarProductos();
}

// Puebla las pestañas de categoría desde PostgreSQL (fuente de verdad de la taxonomía),
// no desde una lista fija en el frontend, así una categoría nueva del administrador
// aparece aquí sin tocar código. Se excluyen las categorías "contenedoras" (sin
// atributos propios, ej. "Tecnología") porque ningún producto se asigna a ellas
// directamente — solo a sus subcategorías (Laptops, Monitores, Zapatos, etc.).
let categoriasDisponibles = [];
let categoriaSeleccionada = "";

async function cargarOpcionesCategoria() {
  const { data: categorias } = await apiFetch("/categorias");
  categoriasDisponibles = (categorias || []).filter(c => (c.esquema_atributos || []).length > 0);
  renderTabsCategoria();
}

function renderTabsCategoria() {
  const cont = document.getElementById("tabs-categoria");
  const tabs = [{ id_categoria: "", nombre: "Todas" }, ...categoriasDisponibles];
  cont.innerHTML = tabs.map(c => {
    const activa = String(c.id_categoria) === String(categoriaSeleccionada);
    return `<button onclick="seleccionarCategoria('${c.id_categoria}')" class="px-4 py-3 text-sm font-semibold whitespace-nowrap border-b-2 transition ${activa ? "border-neutral-950 text-neutral-950" : "border-transparent text-neutral-400 hover:text-neutral-700"}">${c.nombre}</button>`;
  }).join("");
}

async function seleccionarCategoria(idCategoria) {
  categoriaSeleccionada = idCategoria;
  renderTabsCategoria();
  await cargarFiltrosAtributos(idCategoria);
  cargarProductos();
}

// --- BÚSQUEDA ---
let debounceBusqueda = null;
function onBuscarProductos() {
  clearTimeout(debounceBusqueda);
  debounceBusqueda = setTimeout(() => mostrarVista("catalogo"), 350);
}

// --- AUTENTICACIÓN (clientes) ---
async function iniciarSesion(e) {
  e.preventDefault();
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;

  const { ok, data } = await apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });

  if (ok) {
    sesionActual = data.usuario;
    setSesion(sesionActual);
    actualizarInterfazAuth();
    toast(`¡Bienvenido/a, ${sesionActual.nombre}!`, "success");
    mostrarVista("catalogo");
  } else {
    toast(data.error || "No se pudo iniciar sesión.", "error");
  }
}

async function registrarUsuario(e) {
  e.preventDefault();
  const payload = {
    nombre: document.getElementById("reg-nombre").value,
    email: document.getElementById("reg-email").value,
    password: document.getElementById("reg-password").value,
    telefono: document.getElementById("reg-tel").value
    // Sin selector de rol: el autorregistro público siempre crea cuentas de "comprador".
    // Los roles de vendedor/administrador se asignan desde el Panel Admin.
  };

  const { ok, data } = await apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload)
  });

  if (ok) {
    toast("Cuenta creada con éxito. Ahora puedes iniciar sesión.", "success");
    mostrarVista("login");
  } else {
    toast(data.error || "No se pudo crear la cuenta.", "error");
  }
}

function cerrarSesion() {
  sesionActual = null;
  limpiarSesion();
  actualizarInterfazAuth();
  mostrarVista("catalogo");
}

// --- CATÁLOGO ---

// Esquema de filtros por atributo de la categoría actualmente seleccionada
// (se descubre desde los documentos reales vía GET /categorias/<id>/filtros,
// no se mantiene una lista fija de atributos por categoría en el frontend).
let esquemaFiltrosActual = [];

async function cargarFiltrosAtributos(catId) {
  const contenedor = document.getElementById("filtros-atributos");
  const controles = document.getElementById("filtros-atributos-controles");

  if (!catId) {
    esquemaFiltrosActual = [];
    contenedor.classList.add("hidden");
    controles.innerHTML = "";
    return;
  }

  const { data: filtros } = await apiFetch(`/categorias/${catId}/filtros`);
  esquemaFiltrosActual = filtros || [];

  if (esquemaFiltrosActual.length === 0) {
    contenedor.classList.add("hidden");
    controles.innerHTML = "";
    return;
  }

  controles.innerHTML = esquemaFiltrosActual.map(f => {
    const etiqueta = f.clave.replaceAll("_", " ");
    if (f.tipo === "seleccion") {
      return `
        <div>
          <label class="block text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">${etiqueta}</label>
          <select id="filtro-attr-${f.clave}" onchange="cargarProductos()" class="appearance-none border-0 border-b border-neutral-300 hover:border-neutral-950 bg-transparent text-sm px-0 py-1 focus:ring-0 focus:border-neutral-950 outline-none transition cursor-pointer">
            <option value="">Todos</option>
            ${f.valores.map(v => `<option value="${v}">${v}</option>`).join("")}
          </select>
        </div>
      `;
    }
    return `
      <div>
        <label class="block text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-1.5">${etiqueta} (${f.min}–${f.max})</label>
        <div class="flex items-center gap-1.5">
          <input type="number" id="filtro-attr-${f.clave}-min" placeholder="${f.min}" step="any" onchange="cargarProductos()" class="w-16 border-0 border-b border-neutral-300 hover:border-neutral-950 bg-transparent text-sm px-0 py-1 focus:ring-0 focus:border-neutral-950 outline-none transition">
          <span class="text-neutral-300 text-xs">–</span>
          <input type="number" id="filtro-attr-${f.clave}-max" placeholder="${f.max}" step="any" onchange="cargarProductos()" class="w-16 border-0 border-b border-neutral-300 hover:border-neutral-950 bg-transparent text-sm px-0 py-1 focus:ring-0 focus:border-neutral-950 outline-none transition">
        </div>
      </div>
    `;
  }).join("");

  contenedor.classList.remove("hidden");
}

function limpiarFiltrosAtributos() {
  esquemaFiltrosActual.forEach(f => {
    if (f.tipo === "seleccion") {
      const el = document.getElementById(`filtro-attr-${f.clave}`);
      if (el) el.value = "";
    } else {
      const min = document.getElementById(`filtro-attr-${f.clave}-min`);
      const max = document.getElementById(`filtro-attr-${f.clave}-max`);
      if (min) min.value = "";
      if (max) max.value = "";
    }
  });
  cargarProductos();
}

async function cargarProductos() {
  const params = new URLSearchParams();
  if (categoriaSeleccionada) params.set("categoria_id", categoriaSeleccionada);

  const q = document.getElementById("buscador-productos")?.value.trim();
  if (q) params.set("q", q);

  esquemaFiltrosActual.forEach(f => {
    if (f.tipo === "seleccion") {
      const valor = document.getElementById(`filtro-attr-${f.clave}`)?.value;
      if (valor) params.set(`atributo_${f.clave}`, valor);
    } else {
      const min = document.getElementById(`filtro-attr-${f.clave}-min`)?.value;
      const max = document.getElementById(`filtro-attr-${f.clave}-max`)?.value;
      if (min) params.set(`atributo_${f.clave}_min`, min);
      if (max) params.set(`atributo_${f.clave}_max`, max);
    }
  });

  const qs = params.toString();
  const { data: productos } = await apiFetch(qs ? `/productos?${qs}` : "/productos");

  const grid = document.getElementById("grid-productos");
  const vacio = document.getElementById("catalogo-vacio");
  grid.innerHTML = "";

  if (!productos || productos.length === 0) {
    vacio.classList.remove("hidden");
    return;
  }
  vacio.classList.add("hidden");

  productos.forEach(p => {
    let atributosHtml = "";
    for (const [key, val] of Object.entries(p.atributos || {})) {
      atributosHtml += `<div class="text-xs text-neutral-500"><span class="font-medium text-neutral-700">${key.replaceAll("_", " ")}:</span> ${Array.isArray(val) ? val.join(", ") : val}</div>`;
    }

    grid.innerHTML += `
      <div onclick="verDetalleProducto('${p._id}')" class="cursor-pointer group">
        <div class="overflow-hidden rounded-2xl">
          <div class="transition-transform duration-500 group-hover:scale-[1.03]">${productoImagenHtml(p)}</div>
        </div>
        <div class="pt-4">
          <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-400">${p.categoria.nombre}</p>
          <h3 class="font-semibold text-neutral-950 text-[15px] mt-1 leading-snug">${p.nombre}</h3>
          <p class="text-accent-700 font-bold text-lg mt-1.5">Q${p.precio_base.toFixed(2)}</p>
          <div class="mt-2 space-y-0.5">
            ${atributosHtml}
          </div>
        </div>
      </div>
    `;
  });
}

async function verDetalleProducto(id) {
  const { ok, data: p } = await apiFetch(`/productos/${id}`);
  if (!ok) {
    toast("No se pudo cargar el detalle del producto.", "error");
    return;
  }

  let atributosHtml = "";
  for (const [key, val] of Object.entries(p.atributos || {})) {
    atributosHtml += `<div class="text-sm text-neutral-600"><span class="font-semibold text-neutral-800">${key.replaceAll("_", " ")}:</span> ${Array.isArray(val) ? val.join(", ") : val}</div>`;
  }

  document.getElementById("detalle-contenido").innerHTML = `
    <div class="p-1">${productoImagenHtml(p, "h-56")}</div>
    <div class="p-7">
      <p class="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-400">${p.categoria.nombre}</p>
      <h2 class="text-2xl font-extrabold text-neutral-950 tracking-tight mt-1.5">${p.nombre}</h2>
      <p class="text-accent-700 font-bold text-2xl mt-1.5 mb-3">Q${p.precio_base.toFixed(2)}</p>
      <p class="text-sm text-neutral-600 leading-relaxed mb-5">${p.descripcion}</p>
      <div class="border-t border-neutral-200 pt-4 mb-4">
        <h4 class="text-[10px] font-semibold uppercase tracking-wide text-neutral-400 mb-2">Atributos</h4>
        <div class="space-y-1">${atributosHtml || '<span class="text-xs text-neutral-400">Sin atributos registrados</span>'}</div>
      </div>
      <div class="text-xs text-neutral-400 space-y-1 border-t border-neutral-200 pt-4">
        <div><span class="font-medium text-neutral-600">SKU</span> · ${p.sku}</div>
        <div><span class="font-medium text-neutral-600">ID</span> · <span class="font-mono">${p._id}</span></div>
        <div><span class="font-medium text-neutral-600">Stock disponible</span> · ${p.stock_disponible ?? "N/D"}</div>
        <div><span class="font-medium text-neutral-600">Vendedor</span> · ${p.vendedor ? p.vendedor.nombre_comercial : "N/D"}</div>
      </div>
    </div>
  `;
  document.getElementById("modal-detalle").classList.remove("hidden");
  document.getElementById("modal-detalle").classList.add("flex");
}

function cerrarDetalle(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById("modal-detalle").classList.add("hidden");
  document.getElementById("modal-detalle").classList.remove("flex");
}

actualizarInterfazAuth();
cargarOpcionesCategoria();
mostrarVista("catalogo");
