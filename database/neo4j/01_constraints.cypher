// Constraints de referencia para el grafo de detección de fraude en reseñas (Entrega 2).
// Este archivo no se ejecuta automáticamente desde el backend: documenta las constraints
// que se deben aplicar manualmente en Neo4j (vía cypher-shell o Neo4j Browser) al preparar
// la instancia, igual que database/mongo/01_indexes.js documenta los índices de Mongo.
//
// Modelo de grafo:
//   (:Cuenta {id_usuario, nombre, email, ...})
//       -[:CALIFICO {calificacion, fecha, id_resena}]->
//   (:Producto {id_producto, sku, nombre, ...})
//
// - Nodo Cuenta: representa a un usuario comprador de Postgres (id_usuario), espejado en
//   el grafo para poder analizar patrones de comportamiento entre cuentas (p. ej. cuentas
//   que solo califican productos de un mismo vendedor, o que califican en ráfagas cortas).
// - Nodo Producto: representa un producto del catálogo (id_producto), espejado desde Mongo,
//   para poder relacionarlo con las cuentas que lo calificaron.
// - Relación CALIFICO: una reseña puntual de una Cuenta hacia un Producto. Guarda la
//   calificación (1-5), la fecha del evento y el id_resena de origen (para poder rastrear
//   la reseña original en el sistema transaccional/documental si hace falta).
//
// Estas constraints garantizan unicidad de identidad de nodo y, como efecto colateral en
// Neo4j, crean un índice de búsqueda por esa propiedad (útil para las consultas de fraude
// que arrancan buscando una Cuenta o un Producto por su id).

CREATE CONSTRAINT cuenta_id IF NOT EXISTS FOR (c:Cuenta) REQUIRE c.id_usuario IS UNIQUE;
CREATE CONSTRAINT producto_id IF NOT EXISTS FOR (p:Producto) REQUIRE p.id_producto IS UNIQUE;
