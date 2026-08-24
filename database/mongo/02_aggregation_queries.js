use tiendaya_nosql;

// 1. Marco de Agregación: Métricas del Catálogo por Categoría
db.productos.aggregate([
  { $match: { activo: true } },
  {
    $group: {
      _id: "$categoria.nombre",
      id_categoria: { $first: "$categoria.id_categoria" },
      total_productos: { $sum: 1 },
      precio_promedio: { $round: [{ $avg: "$precio_base" }, 2] },
      precio_minimo: { $min: "$precio_base" },
      precio_maximo: { $max: "$precio_base" },
      skus_disponibles: { $push: "$sku" }
    }
  },
  { $sort: { total_productos: -1 } }
]);

// 2. Consulta de Reconstrucción Temporal (Point-in-Time Point Query)
var fechaCorte = ISODate("2026-08-10T00:00:00Z");
var targetProductoId = "PROD-0001";

db.historial_cambios_productos.aggregate([
  {
    $match: {
      producto_id: targetProductoId,
      fecha_evento: { $lte: fechaCorte }
    }
  },
  { $sort: { fecha_evento: -1 } },
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      producto_id: 1,
      fecha_vigencia_evento: "$fecha_evento",
      tipo_evento: 1,
      responsable: "$usuario_responsable.nombre",
      estado_en_esa_fecha: "$estado_resultante"
    }
  }
]);