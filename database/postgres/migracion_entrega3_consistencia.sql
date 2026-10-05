-- ============================================================================
-- MIGRACIÓN ENTREGA 3: consistencia del checkout distribuido
-- ============================================================================
-- Agrega dos tablas de apoyo al checkout (no modifica tablas ni datos
-- existentes, ni el procedimiento sp_procesar_checkout). Es idempotente
-- (IF NOT EXISTS): se puede correr más de una vez.
--
--   checkout_idempotencia   una fila por checkout CONFIRMADO, con la clave de
--                           idempotencia que manda el cliente. Se inserta en la
--                           MISMA transacción que el pedido: si el pedido se
--                           revierte, la clave también. Un reintento con la misma
--                           clave devuelve el pedido original en vez de crear otro.
--
--   eventos_sincronizacion  "outbox" transaccional: lo que hay que hacer en los
--                           otros motores (Redis, MongoDB, Elasticsearch) después
--                           de confirmar un pedido. Se inserta en la MISMA
--                           transacción que el pedido, así que un pedido
--                           confirmado SIEMPRE deja registrado su trabajo
--                           pendiente, aunque el proceso muera justo después del
--                           COMMIT. Un proceso de relevo lo ejecuta con reintentos
--                           idempotentes (ver backend/app/sincronizacion.py).
--
-- Detalle de la estrategia: docs/estrategia-consistencia-checkout.md
--
-- Uso: psql -U postgres -d tiendaya_db -f database/postgres/migracion_entrega3_consistencia.sql
-- La versión canónica de estas tablas también está en ddl_tiendaya.sql; mantener ambas iguales.

CREATE TABLE IF NOT EXISTS checkout_idempotencia (
    clave VARCHAR(64) PRIMARY KEY,
    id_comprador INT NOT NULL,
    id_pedido INT,
    referencia_pago VARCHAR(100),
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_idempotencia_comprador FOREIGN KEY (id_comprador)
        REFERENCES usuarios(id_usuario),
    CONSTRAINT fk_idempotencia_pedido FOREIGN KEY (id_pedido)
        REFERENCES pedidos(id_pedido)
);

CREATE TABLE IF NOT EXISTS eventos_sincronizacion (
    id_evento BIGSERIAL PRIMARY KEY,
    tipo VARCHAR(40) NOT NULL CHECK (tipo IN (
        'confirmar_reserva_oferta',  -- Redis: cerrar la reserva de oferta como vendida
        'limpiar_carrito',           -- Redis: quitar del carrito las líneas compradas
        'stock_mongo',               -- MongoDB: copiar el stock final de PostgreSQL
        'stock_elasticsearch',       -- Elasticsearch: copiar el stock final de PostgreSQL
        'indexar_producto'           -- Elasticsearch: reindexar un producto editado en el admin
    )),
    payload JSONB NOT NULL,
    id_pedido INT,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'procesado', 'fallido')),
    intentos INT NOT NULL DEFAULT 0,
    ultimo_error TEXT,
    proximo_intento TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    procesado_en TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_eventos_pedido FOREIGN KEY (id_pedido)
        REFERENCES pedidos(id_pedido)
);

-- El relevo solo busca eventos pendientes cuyo próximo intento ya llegó.
CREATE INDEX IF NOT EXISTS idx_eventos_pendientes
    ON eventos_sincronizacion (proximo_intento)
    WHERE estado = 'pendiente';
CREATE INDEX IF NOT EXISTS idx_eventos_pedido ON eventos_sincronizacion (id_pedido);
