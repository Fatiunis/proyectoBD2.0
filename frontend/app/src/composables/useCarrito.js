import { ref, computed } from "vue";

const CLAVE_CARRITO = "carrito_tiendaya";

function leerCarritoInicial() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE_CARRITO)) || [];
  } catch {
    return [];
  }
}

const items = ref(leerCarritoInicial());

function persistir() {
  localStorage.setItem(CLAVE_CARRITO, JSON.stringify(items.value));
}

function agregar(producto, cantidad = 1) {
  const stock = producto.stock_disponible ?? Infinity;
  const existente = items.value.find((i) => i.idProducto === producto._id);

  if (existente) {
    existente.cantidad = Math.min(existente.cantidad + cantidad, stock);
  } else {
    const imagenes = producto.imagenes || [];
    const portada = imagenes.find((img) => img.es_portada) || imagenes[0];
    items.value.push({
      idProducto: producto._id,
      idSqlOrigen: producto.id_sql_origen,
      nombre: producto.nombre,
      precioBase: producto.precio_base,
      idCategoria: producto.categoria?.id_categoria,
      imagenUrl: portada?.url || null,
      stockDisponible: stock,
      cantidad: Math.min(Math.max(cantidad, 1), stock),
    });
  }
  persistir();
}

function actualizarCantidad(idProducto, cantidad) {
  const item = items.value.find((i) => i.idProducto === idProducto);
  if (!item) return;
  const tope = item.stockDisponible ?? cantidad;
  item.cantidad = Math.max(1, Math.min(cantidad, tope));
  persistir();
}

function quitar(idProducto) {
  items.value = items.value.filter((i) => i.idProducto !== idProducto);
  persistir();
}

function vaciar() {
  items.value = [];
  persistir();
}

const cantidadTotal = computed(() => items.value.reduce((acc, i) => acc + i.cantidad, 0));
const totalPagar = computed(() => items.value.reduce((acc, i) => acc + i.cantidad * i.precioBase, 0));

export function useCarrito() {
  return { items, agregar, actualizarCantidad, quitar, vaciar, cantidadTotal, totalPagar };
}
