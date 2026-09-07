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

// Índice de texto para la búsqueda del catálogo (GET /api/productos?q=), con nombre
// pesando más que descripción/SKU en la relevancia. Usa el stemmer de MongoDB para
// español -- no reemplaza al motor de búsqueda dedicado de Entrega 3 (sin tolerancia
// a errores ortográficos ni autocompletado), pero ya facilita encontrar un producto
// por palabra suelta a medida que el catálogo crece.
db.productos.createIndex(
  { "nombre": "text", "descripcion": "text", "sku": "text" },
  { weights: { nombre: 5, sku: 3, descripcion: 1 }, default_language: "spanish", name: "idx_texto_busqueda" }
);