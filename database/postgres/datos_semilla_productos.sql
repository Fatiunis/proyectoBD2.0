-- Insertar 5 productos adicionales (IDs del 5 al 9)
INSERT INTO productos (id_producto, id_vendedor, id_categoria, sku, nombre, descripcion, precio_base, activo) VALUES
(5, 2, 2, 'LAP-LEN-LEGION5', 'Laptop Lenovo Legion Pro 5', 'Intel Core i7-14700HX, 16GB RAM DDR5, SSD 1TB, RTX 4060', 10999.00, true),
(6, 2, 3, 'MON-34-CURVO', 'Monitor Curvo UltraWide 34 Pulgadas', 'Resolución WQHD 3440x1440, 165Hz, Panel VA 1500R', 3850.00, true),
(7, 2, 2, 'LAP-MAC-AIR-M3', 'MacBook Air 13 Pulgadas M3', 'Chip Apple M3 8-Core CPU / 10-Core GPU, 16GB RAM, SSD 512GB', 11200.00, true),
(8, 3, 5, 'TSH-MINIMAL-GRY', 'Playera Casual Gris Jaspe', '95% Algodón 5% Elastano, corte regular fit', 160.00, true),
(9, 3, 5, 'TSH-GRAPHIC-CYBER', 'Playera Estampada Cyberpunk', '100% Algodón, serigrafía tacto cero de alta durabilidad', 210.00, true);

-- Productos adicionales para dar variedad real de atributos dentro de cada categoría
-- (necesarios para que los filtros por atributo del catálogo tengan más de un valor posible)
INSERT INTO productos (id_producto, id_vendedor, id_categoria, sku, nombre, descripcion, precio_base, activo) VALUES
(10, 2, 2, 'LAP-ACER-ASPIRE3', 'Laptop Acer Aspire 3 14 Pulgadas', 'Intel Core i5-1235U, 8GB RAM, SSD 512GB, gráfica integrada, ideal para oficina', 4299.00, true),
(11, 2, 2, 'LAP-ROG-STRIX18', 'Laptop ASUS ROG Strix 18 Extreme', 'Intel Core i9-14900HX, 64GB RAM DDR5, SSD 2TB, RTX 4090, pantalla 18 pulgadas 240Hz', 28999.00, true),
(12, 2, 3, 'MON-24-BASICO', 'Monitor Full HD 24 Pulgadas Oficina', 'Panel VA, resolución 1920x1080, 75Hz, ideal para productividad', 749.00, true),
(13, 2, 3, 'MON-32-OLED', 'Monitor OLED 32 Pulgadas Gaming Premium', 'Panel OLED, resolución 4K UHD 3840x2160, 240Hz, tiempo de respuesta 0.03ms', 9499.00, true),
(14, 3, 5, 'TSH-CREW-BLU', 'Playera Crewneck Azul Marino', '100% Poliéster técnico, corte slim fit', 145.00, true),
(15, 3, 5, 'TSH-POLO-RED', 'Playera Polo Roja Piqué', '100% Algodón Piqué, cuello tejido, corte clásico', 220.00, true);

-- Ajustar la secuencia para que futuros inserts sigan desde el ID 16
ALTER SEQUENCE productos_id_producto_seq RESTART WITH 16;

-- Insertar el stock correspondiente en la tabla inventario
INSERT INTO inventario (id_producto, stock_disponible, stock_reservado) VALUES
(5, 12, 0),  -- 12 Laptops Lenovo Legion
(6, 8, 0),   -- 8 Monitores UltraWide
(7, 10, 0),  -- 10 MacBooks Air M3
(8, 45, 0),  -- 45 Playeras Grises
(9, 35, 0),  -- 35 Playeras Cyberpunk
(10, 20, 0), -- 20 Laptops Acer Aspire 3
(11, 5, 0),  -- 5 Laptops ROG Strix 18
(12, 40, 0), -- 40 Monitores Full HD 24"
(13, 15, 0), -- 15 Monitores OLED 32"
(14, 60, 0), -- 60 Playeras Crewneck Azul
(15, 25, 0); -- 25 Playeras Polo Roja