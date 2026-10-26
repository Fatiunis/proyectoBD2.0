-- ============================================================================
-- MIGRACIÓN ENTREGA FINAL: evento de outbox para el componente vectorial
-- ============================================================================
-- Agrega el tipo 'embedding_producto' a la tabla eventos_sincronizacion
-- (creada en migracion_entrega3_consistencia.sql). Cuando el admin guarda un
-- producto, el backend recalcula su embedding en pgvector; si el componente
-- vectorial no responde, el cambio queda como evento pendiente y lo reintenta
-- el relevo, igual que la reindexación en Elasticsearch.
--
-- Idempotente: se puede ejecutar varias veces.
--   psql -U postgres -d tiendaya_db -f database/postgres/migracion_entrega_final_vectores.sql
-- ============================================================================

ALTER TABLE eventos_sincronizacion DROP CONSTRAINT IF EXISTS eventos_sincronizacion_tipo_check;

ALTER TABLE eventos_sincronizacion ADD CONSTRAINT eventos_sincronizacion_tipo_check CHECK (tipo IN (
    'confirmar_reserva_oferta',  -- Redis: cerrar la reserva de oferta como vendida
    'limpiar_carrito',           -- Redis: quitar del carrito las líneas compradas
    'stock_mongo',               -- MongoDB: copiar el stock final de PostgreSQL
    'stock_elasticsearch',       -- Elasticsearch: copiar el stock final de PostgreSQL
    'indexar_producto',          -- Elasticsearch: reindexar un producto editado en el admin
    'embedding_producto'         -- pgvector: recalcular el embedding de un producto editado
));
