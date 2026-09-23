import { ref, computed, watch } from "vue";
import { apiFetch } from "../services/api";
import { useSesion } from "./useSesion";
import { useToast } from "./useToast";

const { sesion } = useSesion();
const { toast } = useToast();

const items = ref([]);

function itemDesdeApi(item) {
  return {
    idProducto: item.id_producto,
    idSqlOrigen: item.id_sql_origen,
    nombre: item.nombre,
    precioBase: item.precio_base,
    idCategoria: item.id_categoria,
    imagenUrl: item.imagen_url,
    stockDisponible: item.stock_disponible,
    cantidad: item.cantidad,
  };
}

function avisarError(data) {
  toast(data?.error || "No se pudo actualizar el carrito", "error");
}

async function cargarCarrito() {
  if (!sesion.value) return;
  const { ok, data } = await apiFetch(`/carrito/${sesion.value.id_usuario}`);
  if (ok) {
    items.value = (data.items || []).map(itemDesdeApi);
  } else {
    avisarError(data);
  }
}

watch(sesion, (actual, anterior) => {
  if (actual && !anterior) {
    cargarCarrito();
  } else if (!actual) {
    items.value = [];
  }
});

if (sesion.value) {
  cargarCarrito();
}

async function agregar(producto, cantidad = 1) {
  if (!sesion.value) {
    toast("Debes iniciar sesión para agregar productos al carrito", "error");
    return;
  }

  const stock = producto.stock_disponible ?? Infinity;
  const imagenes = producto.imagenes || [];
  const portada = imagenes.find((img) => img.es_portada) || imagenes[0];
  const imagenUrl = portada?.url || null;
  const existente = items.value.find((i) => i.idProducto === producto._id);

  if (existente) {
    existente.cantidad = Math.min(existente.cantidad + cantidad, stock);
  } else {
    items.value.push({
      idProducto: producto._id,
      idSqlOrigen: producto.id_sql_origen,
      nombre: producto.nombre,
      precioBase: producto.precio_base,
      idCategoria: producto.categoria?.id_categoria,
      imagenUrl,
      stockDisponible: stock,
      cantidad: Math.min(Math.max(cantidad, 1), stock),
    });
  }

  // Mutación optimista ya aplicada arriba; si la llamada al backend falla solo
  // avisamos con un toast, sin revertir el estado local (suficiente para esta entrega).
  const { ok, data } = await apiFetch(`/carrito/${sesion.value.id_usuario}/items`, {
    method: "POST",
    body: JSON.stringify({
      id_producto: producto._id,
      id_sql_origen: producto.id_sql_origen,
      nombre: producto.nombre,
      precio_base: producto.precio_base,
      id_categoria: producto.categoria?.id_categoria,
      imagen_url: imagenUrl,
      stock_disponible: stock,
      cantidad,
    }),
  });
  if (!ok) avisarError(data);
}

async function actualizarCantidad(idProducto, cantidad) {
  const item = items.value.find((i) => i.idProducto === idProducto);
  if (!item) return;
  const tope = item.stockDisponible ?? cantidad;
  item.cantidad = Math.max(1, Math.min(cantidad, tope));

  if (!sesion.value) return;
  const { ok, data } = await apiFetch(`/carrito/${sesion.value.id_usuario}/items/${idProducto}`, {
    method: "PUT",
    body: JSON.stringify({ cantidad }),
  });
  if (!ok) avisarError(data);
}

async function quitar(idProducto) {
  items.value = items.value.filter((i) => i.idProducto !== idProducto);

  if (!sesion.value) return;
  const { ok, data } = await apiFetch(`/carrito/${sesion.value.id_usuario}/items/${idProducto}`, {
    method: "DELETE",
  });
  if (!ok) avisarError(data);
}

async function vaciar() {
  items.value = [];

  if (!sesion.value) return;
  const { ok, data } = await apiFetch(`/carrito/${sesion.value.id_usuario}`, {
    method: "DELETE",
  });
  if (!ok) avisarError(data);
}

const cantidadTotal = computed(() => items.value.reduce((acc, i) => acc + i.cantidad, 0));
const totalPagar = computed(() => items.value.reduce((acc, i) => acc + i.cantidad * i.precioBase, 0));

export function useCarrito() {
  return { items, agregar, actualizarCantidad, quitar, vaciar, cantidadTotal, totalPagar };
}
