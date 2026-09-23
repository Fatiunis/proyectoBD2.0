-- ============================================================================
-- MIGRACIÓN: sp_procesar_checkout con precio de oferta relámpago
-- ============================================================================
-- Aplicable a una base TiendaYa ya en uso (no toca tablas ni datos): solo reemplaza
-- el procedimiento sp_procesar_checkout por la versión que:
--   * acepta "precio_unitario" opcional por línea (oferta relámpago), validado
--     como > 0 y <= precio_base actual, y lo guarda como precio_unitario_historico;
--   * valida el stock contra la SUMA de cantidades de cada producto (un mismo
--     id_producto puede venir en una línea normal y otra de oferta).
-- La firma del procedimiento no cambia. Es idempotente (CREATE OR REPLACE).
--
-- Uso: psql -U postgres -d tiendaya_db -f database/postgres/migracion_sp_checkout_precio_oferta.sql
-- La versión canónica del procedimiento vive en ddl_tiendaya.sql; mantener ambas iguales.

-- ============================================================================
-- 3. PROCEDIMIENTO ALMACENADO TRANSACCIONAL ATÓMICO: CHECKOUT
-- ============================================================================
-- Este procedimiento ejecuta el flujo completo de compra:
-- 1. Valida el comprador, la dirección y el formato de cada línea del carrito.
-- 2. Agrupa las líneas por producto y bloquea las filas de inventario con SELECT ... FOR UPDATE
--    (en orden de id_producto), verificando existencias contra la SUMA de cantidades de ese producto.
-- 3. Determina el precio de cada línea: precio_base vigente (línea normal) o el precio_unitario
--    de oferta relámpago enviado por el backend, validado contra el precio_base (línea de oferta).
-- 4. Inserta la cabecera en pedidos.
-- 5. Descuenta el stock e inserta cada línea en lineas_pedido con su precio histórico.
-- 6. Registra el pago en pagos.
-- 7. Confirma (COMMIT) o ante cualquier error hace ROLLBACK automático.
--
-- Formato de p_items_json (array JSON; un mismo id_producto puede aparecer en varias líneas,
-- por ejemplo una línea normal y otra de oferta):
--   Línea normal (se cobra productos.precio_base):
--     {"id_producto": 1, "cantidad": 2}
--   Línea de oferta relámpago (se cobra precio_unitario; debe ser > 0 y <= precio_base actual):
--     {"id_producto": 1, "cantidad": 1, "precio_unitario": 9999.99}

CREATE OR REPLACE PROCEDURE sp_procesar_checkout(
    IN p_id_comprador INT,
    IN p_id_direccion INT,
    IN p_metodo_pago VARCHAR(50),
    IN p_referencia_pago VARCHAR(100),
    IN p_items_json JSONB, -- Formato: [{"id_producto": 1, "cantidad": 2}, {"id_producto": 2, "cantidad": 1, "precio_unitario": 199.99}]
    INOUT p_id_pedido_generado INT DEFAULT NULL,
    INOUT p_mensaje_resultado VARCHAR(255) DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_item JSONB;
    v_indice INT;
    v_id_producto INT;
    v_cantidad_solicitada INT;
    v_cantidad_total INT;
    v_stock_actual INT;
    v_precio_actual NUMERIC(12, 2);
    v_precio_linea NUMERIC(12, 2);
    v_nombre_producto VARCHAR(200);
    v_activo BOOLEAN;
    v_subtotal_item NUMERIC(12, 2);
    v_total_calculado NUMERIC(12, 2) := 0.00;
    v_precios_linea NUMERIC(12, 2)[] := '{}';
    v_nombres_linea VARCHAR(200)[] := '{}';
BEGIN
    -- 1. Validación de Comprador y Dirección
    IF NOT EXISTS (SELECT 1 FROM usuarios WHERE id_usuario = p_id_comprador AND rol = 'comprador') THEN
        RAISE EXCEPTION 'El usuario comprador % no existe o no tiene el rol correspondiente.', p_id_comprador;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM direcciones WHERE id_direccion = p_id_direccion AND id_usuario = p_id_comprador) THEN
        RAISE EXCEPTION 'La dirección % no pertenece al comprador %.', p_id_direccion, p_id_comprador;
    END IF;

    IF p_items_json IS NULL OR jsonb_typeof(p_items_json) <> 'array' OR jsonb_array_length(p_items_json) = 0 THEN
        RAISE EXCEPTION 'El carrito de compra no contiene productos.';
    END IF;

    -- 2. Validación de formato de cada línea (cantidad y, si viene, tipo del precio de oferta)
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items_json)
    LOOP
        v_id_producto := (v_item->>'id_producto')::INT;
        v_cantidad_solicitada := (v_item->>'cantidad')::INT;

        IF v_id_producto IS NULL THEN
            RAISE EXCEPTION 'Cada línea del carrito debe indicar id_producto.';
        END IF;

        IF v_cantidad_solicitada IS NULL OR v_cantidad_solicitada <= 0 THEN
            RAISE EXCEPTION 'La cantidad para el producto ID % debe ser mayor a 0.', v_id_producto;
        END IF;

        IF v_item ? 'precio_unitario' AND jsonb_typeof(v_item->'precio_unitario') <> 'number' THEN
            RAISE EXCEPTION 'El precio de oferta para el producto ID % debe ser un número.', v_id_producto;
        END IF;
    END LOOP;

    -- 3. Bloqueo pesimista (Pessimistic Locking) y validación de stock POR PRODUCTO.
    --    Se agrupan las líneas por id_producto para comparar el stock con la suma de todas sus
    --    cantidades (línea normal + línea de oferta), y se bloquea en orden de id_producto para
    --    reducir el riesgo de deadlocks entre checkouts concurrentes.
    FOR v_id_producto, v_cantidad_total IN
        SELECT (e->>'id_producto')::INT, SUM((e->>'cantidad')::INT)::INT
        FROM jsonb_array_elements(p_items_json) AS e
        GROUP BY (e->>'id_producto')::INT
        ORDER BY 1
    LOOP
        SELECT p.nombre, p.activo, i.stock_disponible
        INTO v_nombre_producto, v_activo, v_stock_actual
        FROM productos p
        JOIN inventario i ON p.id_producto = i.id_producto
        WHERE p.id_producto = v_id_producto
        FOR UPDATE OF i;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Producto con ID % o su inventario no existen en el sistema.', v_id_producto;
        END IF;

        IF NOT v_activo THEN
            RAISE EXCEPTION 'El producto % (ID: %) se encuentra inactivo para la venta.', v_nombre_producto, v_id_producto;
        END IF;

        IF v_stock_actual < v_cantidad_total THEN
            RAISE EXCEPTION 'Stock insuficiente para el producto "%". Disponible: %, Solicitado: %.',
                v_nombre_producto, v_stock_actual, v_cantidad_total;
        END IF;
    END LOOP;

    -- 4. Precio de cada línea y cálculo del Total.
    --    Los precios se guardan en arreglos (por posición de la línea) para que la inserción
    --    use exactamente los mismos valores con los que se calculó el total.
    FOR v_item, v_indice IN
        SELECT e, o::INT FROM jsonb_array_elements(p_items_json) WITH ORDINALITY AS t(e, o)
    LOOP
        v_id_producto := (v_item->>'id_producto')::INT;
        v_cantidad_solicitada := (v_item->>'cantidad')::INT;

        SELECT nombre, precio_base
        INTO v_nombre_producto, v_precio_actual
        FROM productos
        WHERE id_producto = v_id_producto;

        IF v_item ? 'precio_unitario' THEN
            -- Línea de oferta relámpago: el precio viene del backend (reserva validada en Redis)
            v_precio_linea := ROUND((v_item->>'precio_unitario')::NUMERIC, 2);

            IF v_precio_linea <= 0 THEN
                RAISE EXCEPTION 'El precio de oferta para el producto "%" (ID: %) debe ser mayor a 0. Recibido: %.',
                    v_nombre_producto, v_id_producto, v_item->>'precio_unitario';
            END IF;

            IF v_precio_linea > v_precio_actual THEN
                RAISE EXCEPTION 'El precio de oferta para el producto "%" (ID: %) no puede superar su precio base. Oferta: %, Precio base: %.',
                    v_nombre_producto, v_id_producto, v_precio_linea, v_precio_actual;
            END IF;
        ELSE
            -- Línea normal: se cobra el precio base vigente
            v_precio_linea := v_precio_actual;
        END IF;

        v_precios_linea[v_indice] := v_precio_linea;
        v_nombres_linea[v_indice] := v_nombre_producto;

        v_subtotal_item := v_precio_linea * v_cantidad_solicitada;
        v_total_calculado := v_total_calculado + v_subtotal_item;
    END LOOP;

    -- 5. Crear el Pedido (Cabecera)
    INSERT INTO pedidos (id_comprador, id_direccion_envio, estado, total)
    VALUES (p_id_comprador, p_id_direccion, 'pagado', v_total_calculado)
    RETURNING id_pedido INTO p_id_pedido_generado;

    -- 6. Descontar Inventario (también por las unidades de oferta) e Insertar Líneas de Pedido
    FOR v_item, v_indice IN
        SELECT e, o::INT FROM jsonb_array_elements(p_items_json) WITH ORDINALITY AS t(e, o)
    LOOP
        v_id_producto := (v_item->>'id_producto')::INT;
        v_cantidad_solicitada := (v_item->>'cantidad')::INT;
        v_precio_linea := v_precios_linea[v_indice];
        v_nombre_producto := v_nombres_linea[v_indice];

        v_subtotal_item := v_precio_linea * v_cantidad_solicitada;

        -- Descontar inventario disponible
        UPDATE inventario
        SET stock_disponible = stock_disponible - v_cantidad_solicitada,
            ultima_actualizacion = CURRENT_TIMESTAMP
        WHERE id_producto = v_id_producto;

        -- Insertar línea de pedido con foto histórica del precio (base u oferta)
        INSERT INTO lineas_pedido (id_pedido, id_producto, nombre_producto_historico, cantidad, precio_unitario_historico, subtotal)
        VALUES (p_id_pedido_generado, v_id_producto, v_nombre_producto, v_cantidad_solicitada, v_precio_linea, v_subtotal_item);
    END LOOP;

    -- 7. Registrar el Pago Exitoso
    INSERT INTO pagos (id_pedido, monto, metodo_pago, estado_pago, referencia_transaccion)
    VALUES (p_id_pedido_generado, v_total_calculado, p_metodo_pago, 'exitoso', p_referencia_pago);

    p_mensaje_resultado := 'Checkout completado exitosamente con transacción atómica.';

EXCEPTION
    WHEN OTHERS THEN
        -- Ante cualquier error de validación o concurrencia, PostgreSQL revierte automáticamente el bloque
        p_id_pedido_generado := NULL;
        p_mensaje_resultado := SQLERRM;
        RAISE NOTICE 'Error durante el checkout: %', SQLERRM;
        RAISE;
END;
$$;
