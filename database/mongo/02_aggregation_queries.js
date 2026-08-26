use tiendaya_nosql;

// 1. Marco de Agregación: Métricas del Catálogo por Categoría
// Nota: $round no es un acumulador válido dentro de $group -aunque envuelva a
// $avg-, Mongo exige que cada campo del $group sea directamente un acumulador
// ($avg, $sum, $min...). Por eso el promedio se calcula "en bruto" aquí y se
// redondea en una etapa $addFields posterior.
db.productos.aggregate([
  { $match: { activo: true } },
  {
    $group: {
      _id: "$categoria.nombre",
      id_categoria: { $first: "$categoria.id_categoria" },
      total_productos: { $sum: 1 },
      precio_promedio_bruto: { $avg: "$precio_base" },
      precio_minimo: { $min: "$precio_base" },
      precio_maximo: { $max: "$precio_base" },
      skus_disponibles: { $push: "$sku" }
    }
  },
  {
    $addFields: {
      precio_promedio: { $round: ["$precio_promedio_bruto", 2] }
    }
  },
  { $project: { precio_promedio_bruto: 0 } },
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