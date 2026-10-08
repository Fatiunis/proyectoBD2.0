// Constraints e índices del grafo de detección de fraude AMPLIADA (después de la Entrega 3, 2026-10-07).
// Archivo aditivo: NO reemplaza a 01_constraints.cypher (Cuenta.id_usuario y
// Producto.id_producto siguen definidos allá y se aplican primero). Igual que aquel, no se
// ejecuta automáticamente desde el backend: se corre a mano (cypher-shell o Neo4j Browser).
// Como todas las sentencias usan IF NOT EXISTS, correrlo de nuevo no falla ni duplica nada.
// database/migrations/sincronizar_grafo_fraude.py también las asegura antes de sincronizar.
//
//   docker compose exec -T neo4j cypher-shell -u neo4j -p tiendaya123 < database/neo4j/02_fraude_ampliado.cypher
//
// Modelo del grafo (lo nuevo marcado con +):
//
//   (:Cuenta {id_usuario, nombre, rol})
//       -[:CALIFICO {calificacion, fecha (string ISO 8601), id_resena,
//                    + compra_verificada (bool),
//                    + semilla, escenario (solo en reseñas de sembrar_fraude_ampliado.py)}]->
//   (:Producto {id_producto, nombre, sku, + id_vendedor (int)})
//       + -[:VENDIDO_POR]-> (:Vendedor {id_vendedor (int), nombre})
//
//   (:Cuenta) + -[:ENVIA_A]-> (:Direccion {clave, ciudad, departamento})
//
// - Vendedor: el vendedor del producto (vendedor.id_vendedor / vendedor.nombre_comercial
//   del documento de Mongo). Permite el patrón "por vendedor": una cuenta que solo
//   califica en extremo (5 estrellas o 1-2) a los productos de un vendedor sin haberle
//   comprado (sesgo_vendedor_sin_compra). Producto.id_vendedor duplica el dato para
//   filtrar sin recorrer la relación.
// - CALIFICO.compra_verificada: true si el autor tiene en Postgres un pedido con una línea
//   de ese producto (pedidos + lineas_pedido, por id_sql_origen del producto). Es el MISMO
//   criterio que usa backend/app/blueprints/resenas.py para `verificada_compra` al listar
//   reseñas (que no filtra por estado del pedido: un pedido cancelado también cuenta).
// - Direccion: dirección de envío (Postgres `direcciones`) deduplicada por una clave
//   normalizada, para que dos cuentas que escriben la misma dirección con distinto uso de
//   mayúsculas/espacios lleguen al MISMO nodo (patrón cuentas_vinculadas):
//       clave = normalizar(direccion_linea1) + "|" + normalizar(ciudad) + "|" + normalizar(codigo_postal)
//       normalizar(s) = " ".join((s or "").lower().split())   -- sin quitar tildes
//   ciudad y departamento (departamento_estado) se guardan tal cual vienen de Postgres,
//   solo para mostrarlos en la evidencia de la alerta.
//
// Índice para CALIFICO.fecha: NO se crea. Las consultas de fraude no filtran por un rango
// absoluto de fechas (que es lo que un índice de rango aceleraría); comparan la diferencia
// entre pares de reseñas ya alcanzadas por el recorrido (datetime(r1.fecha) vs
// datetime(r2.fecha)), y además r.fecha es un string, así que datetime(r.fecha) tampoco
// podría usar un índice. Si en el futuro se agrega un filtro "reseñas de los últimos N
// días", ahí sí convendría: CREATE INDEX califico_fecha IF NOT EXISTS FOR ()-[r:CALIFICO]-() ON (r.fecha);

CREATE CONSTRAINT vendedor_id IF NOT EXISTS FOR (v:Vendedor) REQUIRE v.id_vendedor IS UNIQUE;
CREATE CONSTRAINT direccion_clave IF NOT EXISTS FOR (d:Direccion) REQUIRE d.clave IS UNIQUE;
