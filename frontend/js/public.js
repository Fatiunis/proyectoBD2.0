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
async function cargarProductos() {
  const cat = document.getElementById("filtro-categoria").value;
  const { data: productos } = await apiFetch(cat ? `/productos?categoria_id=${cat}` : "/productos");

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
      atributosHtml += `<div class="text-xs text-slate-500"><span class="font-medium text-slate-700">${key.replaceAll("_", " ")}:</span> ${Array.isArray(val) ? val.join(", ") : val}</div>`;
    }

    grid.innerHTML += `
      <div onclick="verDetalleProducto('${p._id}')" class="cursor-pointer bg-white rounded-xl border border-slate-200 overflow-hidden flex flex-col justify-between hover:shadow-lg hover:-translate-y-0.5 hover:border-indigo-200 transition-all duration-200">
        ${miniaturaCategoriaHtml(p.categoria.id_categoria)}
        <div class="p-4 flex-grow">
          <span class="text-[10px] font-bold uppercase px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded-full">${p.categoria.nombre}</span>
          <h3 class="font-bold text-slate-900 text-base mt-2 leading-snug">${p.nombre}</h3>
          <p class="text-indigo-600 font-extrabold text-xl my-2">Q${p.precio_base.toFixed(2)}</p>
          <div class="space-y-1">
            ${atributosHtml}
          </div>
        </div>
        <div class="px-4 py-2.5 bg-slate-50 border-t border-slate-100 text-[11px] text-slate-400 font-mono">${p.sku} · ${p._id}</div>
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
    atributosHtml += `<div class="text-sm text-slate-600"><span class="font-semibold text-slate-800">${key.replaceAll("_", " ")}:</span> ${Array.isArray(val) ? val.join(", ") : val}</div>`;
  }

  document.getElementById("detalle-contenido").innerHTML = `
    ${miniaturaCategoriaHtml(p.categoria.id_categoria, "h-44")}
    <div class="p-6">
      <span class="text-[10px] font-bold uppercase px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded-full">${p.categoria.nombre}</span>
      <h2 class="text-2xl font-extrabold text-slate-900 mt-2">${p.nombre}</h2>
      <p class="text-indigo-600 font-extrabold text-2xl my-2">Q${p.precio_base.toFixed(2)}</p>
      <p class="text-sm text-slate-600 mb-4">${p.descripcion}</p>
      <div class="bg-slate-50 border border-slate-100 rounded-lg p-3.5 space-y-1 mb-4">
        <h4 class="text-xs font-bold uppercase text-slate-500 mb-1.5">Atributos</h4>
        ${atributosHtml || '<span class="text-xs text-slate-400">Sin atributos registrados</span>'}
      </div>
      <div class="text-xs text-slate-500 space-y-1 border-t border-slate-100 pt-3">
        <div><span class="font-semibold">SKU:</span> ${p.sku}</div>
        <div><span class="font-semibold">ID:</span> <span class="font-mono">${p._id}</span></div>
        <div><span class="font-semibold">Stock disponible:</span> ${p.stock_disponible ?? "N/D"}</div>
        <div><span class="font-semibold">Vendedor:</span> ${p.vendedor ? p.vendedor.nombre_comercial : "N/D"}</div>
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
mostrarVista("catalogo");
