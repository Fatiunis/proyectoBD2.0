use tiendaya_nosql;

// Índice compuesto para consulta de catálogo (categoría + disponibilidad + orden por precio)
db.productos.createIndex(
  { "categoria.id_categoria": 1, "activo": 1, "precio_base": 1 },
  { name: "idx_categoria_activo_precio" }
);

// Índice de unicidad para SKU
db.productos.createIndex(
  { "sku": 1 },
  { unique: true, name: "idx_sku_unico" }
);

// Índice para reconstrucción cronológica en auditoría
db.historial_cambios_productos.createIndex(
  { "producto_id": 1, "fecha_evento": 1 },
  { name: "idx_historial_producto_fecha" }
);