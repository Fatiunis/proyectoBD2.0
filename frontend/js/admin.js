let sesionAdmin = getSesion();

function actualizarAccesoAdmin() {
  const esAdmin = sesionAdmin && sesionAdmin.rol === "administrador";
  document.getElementById("admin-login-gate").classList.toggle("hidden", esAdmin);
  document.getElementById("admin-shell").classList.toggle("hidden", !esAdmin);

  if (esAdmin) {
    document.getElementById("admin-user-info").textContent = `${sesionAdmin.nombre} · administrador`;
    mostrarTabAdmin("catalogo");
  }
}

async function iniciarSesionAdmin(e) {
  e.preventDefault();
  const email = document.getElementById("admin-login-email").value;
  const password = document.getElementById("admin-login-password").value;

  const { ok, data } = await apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });

  if (!ok) {
    document.getElementById("admin-login-error").textContent = data.error || "No se pudo iniciar sesión.";
    document.getElementById("admin-login-error").classList.remove("hidden");
    return;
  }

  if (data.usuario.rol !== "administrador") {
    document.getElementById("admin-login-error").textContent = "Esta cuenta no tiene permisos de administrador.";
    document.getElementById("admin-login-error").classList.remove("hidden");
    return;
  }

  sesionAdmin = data.usuario;
  setSesion(sesionAdmin);
  document.getElementById("admin-login-error").classList.add("hidden");
  actualizarAccesoAdmin();
}

function cerrarSesionAdmin() {
  sesionAdmin = null;
  limpiarSesion();
  actualizarAccesoAdmin();
}

function mostrarTabAdmin(tab) {
  ["catalogo", "usuarios", "historial"].forEach(t => {
    document.getElementById(`admin-tab-${t}`).classList.toggle("hidden", t !== tab);
    const btn = document.getElementById(`admin-nav-${t}`);
    btn.classList.toggle("bg-indigo-600", t === tab);
    btn.classList.toggle("text-white", t === tab);
    btn.classList.toggle("text-slate-300", t !== tab);
  });
  if (tab === "catalogo") cargarTablaProductos();
  if (tab === "historial") cargarSelectorProductosHistorial();
}

// --- GESTIÓN DE CATÁLOGO ---
async function cargarTablaProductos() {
  const { data: productos } = await apiFetch("/productos");
  const tbody = document.getElementById("admin-tabla-productos");
  tbody.innerHTML = "";

  if (!productos || productos.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-sm text-slate-400">Aún no hay productos en el catálogo.</td></tr>`;
    return;
  }

  productos.forEach(p => {
    tbody.innerHTML += `
      <tr class="border-b border-slate-50 hover:bg-slate-50/80 transition">
        <td class="p-2.5 text-slate-400 font-mono text-xs">${p._id}</td>
        <td class="p-2.5 font-medium text-slate-800">${p.nombre}</td>
        <td class="p-2.5 text-slate-500 font-mono text-xs">${p.sku}</td>
        <td class="p-2.5"><span class="text-[10px] font-bold uppercase px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded-full">${p.categoria.nombre}</span></td>
        <td class="p-2.5 text-right font-semibold text-slate-800">Q${p.precio_base.toFixed(2)}</td>
        <td class="p-2.5 text-right">
          <button onclick="cargarProductoParaEditar('${p._id}')" class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg transition">Editar</button>
        </td>
      </tr>
    `;
  });
}

function nuevoProducto() {
  document.getElementById("form-producto").reset();
  document.getElementById("p-producto-id").value = "";
  document.getElementById("form-producto-titulo").textContent = "Nuevo Producto";
  renderAtributosDinamicos();
}

async function cargarProductoParaEditar(id) {
  const { ok, data: p } = await apiFetch(`/productos/${id}`);
  if (!ok) {
    toast("No se pudo cargar el producto.", "error");
    return;
  }

  document.getElementById("p-producto-id").value = p._id;
  document.getElementById("form-producto-titulo").textContent = `Editando: ${p.nombre}`;
  document.getElementById("p-sku").value = p.sku;
  document.getElementById("p-nombre").value = p.nombre;
  document.getElementById("p-desc").value = p.descripcion;
  document.getElementById("p-precio").value = p.precio_base;
  document.getElementById("p-stock").value = p.stock_disponible ?? 0;
  document.getElementById("p-categoria").value = idCategoriaAFormValue(p.categoria.id_categoria);
  renderAtributosDinamicos(p.atributos || {});

  document.getElementById("form-producto").scrollIntoView({ behavior: "smooth" });
}

function renderAtributosDinamicos(existentes = {}) {
  const cat = document.getElementById("p-categoria").value;
  const c = document.getElementById("contenedor-atributos-dinamicos");
  c.innerHTML = "";

  if (cat === "laptops") {
    c.innerHTML = `
      <div><label class="text-xs font-medium">Procesador</label><input type="text" id="attr-cpu" class="w-full border p-1 rounded text-sm" value="${existentes.procesador ?? "AMD Ryzen 9 8940HX"}"></div>
      <div><label class="text-xs font-medium">RAM (GB)</label><input type="number" id="attr-ram" class="w-full border p-1 rounded text-sm" value="${existentes.memoria_ram_gb ?? 32}"></div>
      <div><label class="text-xs font-medium">Almacenamiento (GB)</label><input type="number" id="attr-ssd" class="w-full border p-1 rounded text-sm" value="${existentes.almacenamiento_ssd_gb ?? 1000}"></div>
      <div><label class="text-xs font-medium">Pantalla (Hz)</label><input type="number" id="attr-hz" class="w-full border p-1 rounded text-sm" value="${existentes.tasa_refresco_hz ?? 180}"></div>
    `;
  } else if (cat === "monitores") {
    c.innerHTML = `
      <div><label class="text-xs font-medium">Pulgadas</label><input type="number" id="attr-pulgadas" class="w-full border p-1 rounded text-sm" value="${existentes.tamano_pulgadas ?? 27}"></div>
      <div><label class="text-xs font-medium">Panel</label><input type="text" id="attr-panel" class="w-full border p-1 rounded text-sm" value="${existentes.tipo_panel ?? "IPS"}"></div>
      <div><label class="text-xs font-medium">Resolución</label><input type="text" id="attr-res" class="w-full border p-1 rounded text-sm" value="${existentes.resolucion ?? "1920x1080"}"></div>
      <div><label class="text-xs font-medium">Tasa Refresco (Hz)</label><input type="number" id="attr-hz-mon" class="w-full border p-1 rounded text-sm" value="${existentes.tasa_refresco_hz ?? 180}"></div>
    `;
  } else if (cat === "ropa") {
    c.innerHTML = `
      <div><label class="text-xs font-medium">Talla</label><input type="text" id="attr-talla" class="w-full border p-1 rounded text-sm" value="${existentes.talla ?? "M"}"></div>
      <div><label class="text-xs font-medium">Color</label><input type="text" id="attr-color" class="w-full border p-1 rounded text-sm" value="${existentes.color ?? "Negro"}"></div>
      <div><label class="text-xs font-medium">Material</label><input type="text" id="attr-mat" class="w-full border p-1 rounded text-sm" value="${existentes.material ?? "100% Algodón"}"></div>
    `;
  }
}

async function guardarProducto(e) {
  e.preventDefault();
  const cat = document.getElementById("p-categoria").value;
  let atributos = {};

  if (cat === "laptops") {
    atributos = {
      procesador: document.getElementById("attr-cpu").value,
      memoria_ram_gb: parseInt(document.getElementById("attr-ram").value),
      almacenamiento_ssd_gb: parseInt(document.getElementById("attr-ssd").value),
      tasa_refresco_hz: parseInt(document.getElementById("attr-hz").value)
    };
  } else if (cat === "monitores") {
    atributos = {
      tamano_pulgadas: parseFloat(document.getElementById("attr-pulgadas").value),
      tipo_panel: document.getElementById("attr-panel").value,
      resolucion: document.getElementById("attr-res").value,
      tasa_refresco_hz: parseInt(document.getElementById("attr-hz-mon").value)
    };
  } else {
    atributos = {
      talla: document.getElementById("attr-talla").value,
      color: document.getElementById("attr-color").value,
      material: document.getElementById("attr-mat").value
    };
  }

  const info = CATEGORIAS_FORM[cat];
  const payload = {
    sku: document.getElementById("p-sku").value,
    nombre: document.getElementById("p-nombre").value,
    descripcion: document.getElementById("p-desc").value,
    precio_base: parseFloat(document.getElementById("p-precio").value),
    stock_disponible: parseInt(document.getElementById("p-stock").value),
    id_categoria: info.id_categoria,
    nombre_categoria: info.nombre_categoria,
    id_vendedor: sesionAdmin.id_usuario,
    nombre_vendedor: sesionAdmin.nombre,
    atributos
  };

  const { ok, data } = await apiFetch("/productos", {
    method: "POST",
    body: JSON.stringify(payload)
  });

  if (ok) {
    toast("Producto guardado y evento registrado en el historial.", "success");
    nuevoProducto();
    cargarTablaProductos();
  } else {
    toast(data.error || "No se pudo guardar el producto.", "error");
  }
}

// --- ALTA DE USUARIOS ---
async function altaUsuario(e) {
  e.preventDefault();
  const payload = {
    nombre: document.getElementById("u-nombre").value,
    email: document.getElementById("u-email").value,
    password: document.getElementById("u-password").value,
    rol: document.getElementById("u-rol").value,
    telefono: document.getElementById("u-tel").value
  };

  const { ok, data } = await apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload)
  });

  if (ok) {
    toast(`Usuario "${payload.nombre}" creado con rol ${payload.rol}.`, "success");
    document.getElementById("form-usuario").reset();
  } else {
    toast(data.error || "No se pudo crear el usuario.", "error");
  }
}

// --- HISTORIAL TEMPORAL ---
let mapaProductosHistorial = {};

async function cargarSelectorProductosHistorial() {
  const { data: productos } = await apiFetch("/productos");
  const ordenados = [...(productos || [])].sort((a, b) => a.nombre.localeCompare(b.nombre));

  mapaProductosHistorial = {};
  const datalist = document.getElementById("lista-productos-historial");
  datalist.innerHTML = ordenados
    .map(p => {
      const etiqueta = `${p.nombre} — ${p.sku}`;
      mapaProductosHistorial[etiqueta] = p._id;
      return `<option value="${etiqueta}">`;
    })
    .join("");

  actualizarProductoResuelto();
}

function actualizarProductoResuelto() {
  const texto = document.getElementById("h-prod-buscar").value;
  const id = mapaProductosHistorial[texto];
  const resultado = document.getElementById("h-prod-id-resuelto");
  resultado.textContent = id ? `ID: ${id}` : "Ningún producto seleccionado. Escribe el nombre y elige una opción de la lista.";
  return id || null;
}

async function consultarHistorial() {
  const prodId = actualizarProductoResuelto();
  if (!prodId) {
    toast("Selecciona un producto válido de la lista antes de consultar.", "error");
    return;
  }
  const fechaVal = document.getElementById("h-fecha").value;
  if (!fechaVal) {
    toast("Por favor selecciona una fecha de corte.", "error");
    return;
  }

  const isoFecha = new Date(fechaVal).toISOString();
  const { ok, data } = await apiFetch(`/historial/${prodId}?fecha_corte=${isoFecha}`);

  const divRes = document.getElementById("resultado-historial");

  if (!ok) {
    toast(data.error || data.detail || "No se encontró historial para esa fecha.", "error");
    divRes.classList.add("hidden");
    return;
  }

  renderResultadoHistorial(data);
  divRes.classList.remove("hidden");
}

const ETIQUETAS_TIPO_EVENTO = {
  CREACION_PRODUCTO: "Creación de producto",
  ACTUALIZACION_PANEL_ADMIN: "Actualización desde panel admin"
};

function etiquetaTipoEvento(tipo) {
  return ETIQUETAS_TIPO_EVENTO[tipo] || tipo.replaceAll("_", " ").toLowerCase()
    .replace(/(^|\s)\S/g, letra => letra.toUpperCase());
}

function formatearFecha(iso) {
  return new Date(iso).toLocaleString("es-GT", { dateStyle: "long", timeStyle: "short" });
}

function renderResultadoHistorial(data) {
  const estado = data.estado_en_esa_fecha;

  document.getElementById("h-tipo-evento").textContent = etiquetaTipoEvento(data.tipo_evento);
  document.getElementById("h-fecha-evento").textContent = formatearFecha(data.fecha_vigencia_evento);
  document.getElementById("h-nombre-producto").textContent = estado.nombre;
  document.getElementById("h-precio-producto").textContent = `Q${Number(estado.precio_base).toFixed(2)}`;
  document.getElementById("h-desc-producto").textContent = estado.descripcion;
  document.getElementById("h-producto-id-mostrado").textContent = data.producto_id;
  document.getElementById("h-responsable").textContent = data.responsable;

  const badge = document.getElementById("h-estado-badge");
  badge.textContent = estado.activo ? "Activo" : "Inactivo";
  badge.className = `shrink-0 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${estado.activo ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}`;

  const atributos = estado.atributos || {};
  const grid = document.getElementById("h-atributos-grid");
  const entradas = Object.entries(atributos);
  grid.innerHTML = entradas.length
    ? entradas.map(([clave, valor]) => `
        <div class="text-xs text-slate-500">${clave.replaceAll("_", " ")}</div>
        <div class="text-xs text-slate-800 font-medium">${Array.isArray(valor) ? valor.join(", ") : valor}</div>
      `).join("")
    : '<span class="text-xs text-slate-400 col-span-2">Sin atributos registrados en este evento</span>';

  document.getElementById("json-historial").innerText = JSON.stringify(data, null, 2);
}

actualizarAccesoAdmin();
