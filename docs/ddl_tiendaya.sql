-- ============================================================================
-- PROYECTO TIENDAYA - FASE INICIAL: MODELO TRANSACCIONAL BASE (POSTGRESQL)
-- ============================================================================

-- 0. LIMPIEZA DE TABLAS Y PROCEDIMIENTOS PREVIOS
DROP PROCEDURE IF EXISTS sp_procesar_checkout;
DROP TABLE IF EXISTS pagos CASCADE;
DROP TABLE IF EXISTS lineas_pedido CASCADE;
DROP TABLE IF EXISTS pedidos CASCADE;
DROP TABLE IF EXISTS inventario CASCADE;
DROP TABLE IF EXISTS productos CASCADE;
DROP TABLE IF EXISTS categorias CASCADE;
DROP TABLE IF EXISTS direcciones CASCADE;
DROP TABLE IF EXISTS usuarios CASCADE;

-- ============================================================================
-- 1. DEFINICIÓN DE ESQUEMA (DDL EN 3FN)
-- ============================================================================

-- Tabla: usuarios
CREATE TABLE usuarios (
    id_usuario SERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL CHECK (rol IN ('comprador', 'vendedor', 'administrador')),
    telefono VARCHAR(20),
    fecha_registro TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Tabla: direcciones (1 a N con usuarios)
CREATE TABLE direcciones (
    id_direccion SERIAL PRIMARY KEY,
    id_usuario INT NOT NULL,
    direccion_linea1 VARCHAR(255) NOT NULL,
    direccion_linea2 VARCHAR(255),
    ciudad VARCHAR(100) NOT NULL,
    departamento_estado VARCHAR(100) NOT NULL,
    codigo_postal VARCHAR(20) NOT NULL,
    pais VARCHAR(100) DEFAULT 'Guatemala' NOT NULL,
    es_principal BOOLEAN DEFAULT false NOT NULL,
    CONSTRAINT fk_direcciones_usuario FOREIGN KEY (id_usuario) 
        REFERENCES usuarios(id_usuario) ON DELETE CASCADE
);

-- Tabla: categorias (Estructura jerárquica auto-referenciada)
CREATE TABLE categorias (
    id_categoria SERIAL PRIMARY KEY,
    nombre_categoria VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    id_categoria_padre INT,
    CONSTRAINT fk_categoria_padre FOREIGN KEY (id_categoria_padre) 
        REFERENCES categorias(id_categoria) ON DELETE SET NULL
);

-- Tabla: productos (Catálogo inicial en relacional)
CREATE TABLE productos (
    id_producto SERIAL PRIMARY KEY,
    id_vendedor INT NOT NULL,
    id_categoria INT NOT NULL,
    sku VARCHAR(60) NOT NULL UNIQUE,
    nombre VARCHAR(200) NOT NULL,
    descripcion TEXT NOT NULL,
    precio_base NUMERIC(12, 2) NOT NULL CHECK (precio_base >= 0),
    activo BOOLEAN DEFAULT true NOT NULL,
    fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_productos_vendedor FOREIGN KEY (id_vendedor) 
        REFERENCES usuarios(id_usuario),
    CONSTRAINT fk_productos_categoria FOREIGN KEY (id_categoria) 
        REFERENCES categorias(id_categoria)
);

-- Tabla: inventario (1 a 1 con productos)
CREATE TABLE inventario (
    id_inventario SERIAL PRIMARY KEY,
    id_producto INT NOT NULL UNIQUE,
    stock_disponible INT NOT NULL CHECK (stock_disponible >= 0),
    stock_reservado INT DEFAULT 0 NOT NULL CHECK (stock_reservado >= 0),
    ultima_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_inventario_producto FOREIGN KEY (id_producto) 
        REFERENCES productos(id_producto) ON DELETE CASCADE
);

-- Tabla: pedidos
CREATE TABLE pedidos (
    id_pedido SERIAL PRIMARY KEY,
    id_comprador INT NOT NULL,
    id_direccion_envio INT NOT NULL,
    fecha_pedido TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    estado VARCHAR(30) NOT NULL CHECK (estado IN ('pendiente', 'pagado', 'enviado', 'entregado', 'cancelado')),
    total NUMERIC(12, 2) NOT NULL CHECK (total >= 0),
    CONSTRAINT fk_pedidos_comprador FOREIGN KEY (id_comprador) 
        REFERENCES usuarios(id_usuario),
    CONSTRAINT fk_pedidos_direccion FOREIGN KEY (id_direccion_envio) 
        REFERENCES direcciones(id_direccion)
);

-- Tabla: lineas_pedido
CREATE TABLE lineas_pedido (
    id_linea SERIAL PRIMARY KEY,
    id_pedido INT NOT NULL,
    id_producto INT NOT NULL,
    nombre_producto_historico VARCHAR(200) NOT NULL,
    cantidad INT NOT NULL CHECK (cantidad > 0),
    precio_unitario_historico NUMERIC(12, 2) NOT NULL CHECK (precio_unitario_historico >= 0),
    subtotal NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0),
    CONSTRAINT fk_lineas_pedido FOREIGN KEY (id_pedido) 
        REFERENCES pedidos(id_pedido) ON DELETE CASCADE
);

-- Tabla: pagos
CREATE TABLE pagos (
    id_pago SERIAL PRIMARY KEY,
    id_pedido INT NOT NULL UNIQUE,
    monto NUMERIC(12, 2) NOT NULL CHECK (monto > 0),
    metodo_pago VARCHAR(50) NOT NULL CHECK (metodo_pago IN ('tarjeta_credito', 'tarjeta_debito', 'transferencia', 'paypal')),
    estado_pago VARCHAR(30) NOT NULL CHECK (estado_pago IN ('exitoso', 'fallido', 'reembolsado')),
    referencia_transaccion VARCHAR(100) NOT NULL UNIQUE,
    fecha_pago TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT fk_pagos_pedido FOREIGN KEY (id_pedido) 
        REFERENCES pedidos(id_pedido)
);

-- Creación de Índices para optimización de consultas operativas
CREATE INDEX idx_productos_categoria ON productos(id_categoria);
CREATE INDEX idx_productos_vendedor ON productos(id_vendedor);
CREATE INDEX idx_pedidos_comprador ON pedidos(id_comprador);
CREATE INDEX idx_lineas_pedido_pedido ON lineas_pedido(id_pedido);
CREATE INDEX idx_inventario_producto ON inventario(id_producto);


-- ============================================================================
-- 2. POBLADO DE DATOS SEMILLA (DML)
-- ============================================================================

-- Usuarios
INSERT INTO usuarios (id_usuario, nombre, email, password_hash, rol, telefono) VALUES
(1, 'Admin TiendaYa', 'admin@tiendaya.com', '$2b$12$e8x...hashAdmin', 'administrador', '+50255550000'),
(2, 'TechStore Oficial', 'ventas@techstore.com', '$2b$12$e8x...hashTech', 'vendedor', '+50255551111'),
(3, 'Moda Urbana GT', 'contacto@modaurbana.com', '$2b$12$e8x...hashModa', 'vendedor', '+50255552222'),
(4, 'Carlos Mendez', 'carlos.mendez@email.com', '$2b$12$e8x...hashCarlos', 'comprador', '+50255553333'),
(5, 'Sofia Lopez', 'sofia.lopez@email.com', '$2b$12$e8x...hashSofia', 'comprador', '+50255554444');

ALTER SEQUENCE usuarios_id_usuario_seq RESTART WITH 6;

-- Direcciones
INSERT INTO direcciones (id_direccion, id_usuario, direccion_linea1, ciudad, departamento_estado, codigo_postal, es_principal) VALUES
(1, 4, '15 Avenida 10-20 Zona 10', 'Guatemala', 'Guatemala', '01010', true),
(2, 5, '4a Calle 3-15 Zona 14', 'Guatemala', 'Guatemala', '01014', true);

ALTER SEQUENCE direcciones_id_direccion_seq RESTART WITH 3;

-- Categorías
INSERT INTO categorias (id_categoria, nombre_categoria, descripcion, id_categoria_padre) VALUES
(1, 'Tecnología', 'Equipos de computación, periféricos y electrónica', NULL),
(2, 'Laptops', 'Laptops gamers, de oficina y ultrabooks', 1),
(3, 'Monitores', 'Monitores de alta tasa de refresco y productividad', 1),
(4, 'Moda y Ropa', 'Vestuario para damas y caballeros', NULL),
(5, 'Playeras', 'Playeras casuales y de diseño', 4);

ALTER SEQUENCE categorias_id_categoria_seq RESTART WITH 6;

-- Productos
INSERT INTO productos (id_producto, id_vendedor, id_categoria, sku, nombre, descripcion, precio_base, activo) VALUES
(1, 2, 2, 'LAP-OMEN-16', 'Laptop Gamer 16 Pulgadas', 'Procesador Ryzen 9, 32GB RAM, Pantalla 180Hz', 12500.00, true),
(2, 2, 3, 'MON-27-180HZ', 'Monitor Gamer 27 Pulgadas IPS', 'Resolución Full HD, 180Hz, 1ms, soporte DisplayPort', 2200.00, true),
(3, 3, 5, 'TSH-OVERSIZE-BLK', 'Playera Oversize Negra', '100% Algodón peinado, corte relajado', 175.00, true),
(4, 3, 5, 'TSH-VINTAGE-WHT', 'Playera Vintage Estampada Blanca', 'Estampado serigráfico de alta duración', 190.00, true);

ALTER SEQUENCE productos_id_producto_seq RESTART WITH 5;

-- Inventario inicial
INSERT INTO inventario (id_producto, stock_disponible, stock_reservado) VALUES
(1, 15, 0), -- 15 Laptops
(2, 25, 0), -- 25 Monitores
(3, 50, 0), -- 50 Playeras negras
(4, 30, 0); -- 30 Playeras blancas


-- ============================================================================
-- 3. PROCEDIMIENTO ALMACENADO TRANSACCIONAL ATÓMICO: CHECKOUT
-- ============================================================================
-- Este procedimiento ejecuta el flujo completo de compra:
-- 1. Valida el comprador y la dirección.
-- 2. Itera sobre los ítems del carrito (enviados como array JSON) y bloquea filas con SELECT ... FOR UPDATE.
-- 3. Verifica existencias y descuenta el stock en inventario.
-- 4. Inserta la cabecera en pedidos.
-- 5. Inserta cada ítem en lineas_pedido con su precio histórico.
-- 6. Registra el pago en pagos.
-- 7. Confirma (COMMIT) o ante cualquier error hace ROLLBACK automático.

CREATE OR REPLACE PROCEDURE sp_procesar_checkout(
    IN p_id_comprador INT,
    IN p_id_direccion INT,
    IN p_metodo_pago VARCHAR(50),
    IN p_referencia_pago VARCHAR(100),
    IN p_items_json JSONB, -- Formato esperado: [{"id_producto": 1, "cantidad": 2}, {"id_producto": 2, "cantidad": 1}]
    OUT p_id_pedido_generado INT,
    OUT p_mensaje_resultado VARCHAR(255)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_item JSONB;
    v_id_producto INT;
    v_cantidad_solicitada INT;
    v_stock_actual INT;
    v_precio_actual NUMERIC(12, 2);
    v_nombre_producto VARCHAR(200);
    v_activo BOOLEAN;
    v_subtotal_item NUMERIC(12, 2);
    v_total_calculado NUMERIC(12, 2) := 0.00;
BEGIN
    -- 1. Validación de Comprador y Dirección
    IF NOT EXISTS (SELECT 1 FROM usuarios WHERE id_usuario = p_id_comprador AND rol = 'comprador') THEN
        RAISE EXCEPTION 'El usuario comprador % no existe o no tiene el rol correspondiente.', p_id_comprador;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM direcciones WHERE id_direccion = p_id_direccion AND id_usuario = p_id_comprador) THEN
        RAISE EXCEPTION 'La dirección % no pertenece al comprador %.', p_id_direccion, p_id_comprador;
    END IF;

    IF p_items_json IS NULL OR jsonb_array_length(p_items_json) = 0 THEN
        RAISE EXCEPTION 'El carrito de compra no contiene productos.';
    END IF;

    -- 2. Primera pasada: Bloqueo de filas (Pessimistic Locking), validación de Stock y cálculo del Total
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items_json)
    LOOP
        v_id_producto := (v_item->>'id_producto')::INT;
        v_cantidad_solicitada := (v_item->>'cantidad')::INT;

        IF v_cantidad_solicitada <= 0 THEN
            RAISE EXCEPTION 'La cantidad para el producto ID % debe ser mayor a 0.', v_id_producto;
        END IF;

        -- Bloqueo pesimista del producto e inventario para evitar condiciones de carrera (Race Conditions)
        SELECT p.nombre, p.precio_base, p.activo, i.stock_disponible
        INTO v_nombre_producto, v_precio_actual, v_activo, v_stock_actual
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

        IF v_stock_actual < v_cantidad_solicitada THEN
            RAISE EXCEPTION 'Stock insuficiente para el producto "%". Disponible: %, Solicitado: %.', 
                v_nombre_producto, v_stock_actual, v_cantidad_solicitada;
        END IF;

        v_subtotal_item := v_precio_actual * v_cantidad_solicitada;
        v_total_calculado := v_total_calculado + v_subtotal_item;
    END LOOP;

    -- 3. Crear el Pedido (Cabecera)
    INSERT INTO pedidos (id_comprador, id_direccion_envio, estado, total)
    VALUES (p_id_comprador, p_id_direccion, 'pagado', v_total_calculado)
    RETURNING id_pedido INTO p_id_pedido_generado;

    -- 4. Segunda pasada: Descontar Inventario e Insertar Líneas de Pedido
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items_json)
    LOOP
        v_id_producto := (v_item->>'id_producto')::INT;
        v_cantidad_solicitada := (v_item->>'cantidad')::INT;

        SELECT nombre, precio_base
        INTO v_nombre_producto, v_precio_actual
        FROM productos
        WHERE id_producto = v_id_producto;

        v_subtotal_item := v_precio_actual * v_cantidad_solicitada;

        -- Descontar inventario disponible
        UPDATE inventario
        SET stock_disponible = stock_disponible - v_cantidad_solicitada,
            ultima_actualizacion = CURRENT_TIMESTAMP
        WHERE id_producto = v_id_producto;

        -- Insertar línea de pedido con foto histórica del precio
        INSERT INTO lineas_pedido (id_pedido, id_producto, nombre_producto_historico, cantidad, precio_unitario_historico, subtotal)
        VALUES (p_id_pedido_generado, v_id_producto, v_nombre_producto, v_cantidad_solicitada, v_precio_actual, v_subtotal_item);
    END LOOP;

    -- 5. Registrar el Pago Exitoso
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