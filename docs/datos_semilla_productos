-- Insertar 5 productos adicionales (IDs del 5 al 9)
INSERT INTO productos (id_producto, id_vendedor, id_categoria, sku, nombre, descripcion, precio_base, activo) VALUES
(5, 2, 2, 'LAP-LEN-LEGION5', 'Laptop Lenovo Legion Pro 5', 'Intel Core i7-14700HX, 16GB RAM DDR5, SSD 1TB, RTX 4060', 10999.00, true),
(6, 2, 3, 'MON-34-CURVO', 'Monitor Curvo UltraWide 34 Pulgadas', 'Resolución WQHD 3440x1440, 165Hz, Panel VA 1500R', 3850.00, true),
(7, 2, 2, 'LAP-MAC-AIR-M3', 'MacBook Air 13 Pulgadas M3', 'Chip Apple M3 8-Core CPU / 10-Core GPU, 16GB RAM, SSD 512GB', 11200.00, true),
(8, 3, 5, 'TSH-MINIMAL-GRY', 'Playera Casual Gris Jaspe', '95% Algodón 5% Elastano, corte regular fit', 160.00, true),
(9, 3, 5, 'TSH-GRAPHIC-CYBER', 'Playera Estampada Cyberpunk', '100% Algodón, serigrafía tacto cero de alta durabilidad', 210.00, true);

-- Ajustar la secuencia para que futuros inserts sigan desde el ID 10
ALTER SEQUENCE productos_id_producto_seq RESTART WITH 10;

-- Insertar el stock correspondiente en la tabla inventario
INSERT INTO inventario (id_producto, stock_disponible, stock_reservado) VALUES
(5, 12, 0),  -- 12 Laptops Lenovo Legion
(6, 8, 0),   -- 8 Monitores UltraWide
(7, 10, 0),  -- 10 MacBooks Air M3
(8, 45, 0),  -- 45 Playeras Grises
(9, 35, 0);  -- 35 Playeras Cyberpunk