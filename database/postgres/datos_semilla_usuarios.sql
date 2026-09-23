-- Insertar 10 usuarios compradores adicionales.
-- Propósito: ampliar la base de compradores para tener datos más realistas de cara a la
-- Entrega 2, donde se modela en Neo4j la detección de fraude en reseñas (nodos Cuenta que
-- CALIFICAN Productos). Con solo 2 compradores semilla no hay suficiente variedad de
-- cuentas para simular patrones de reseñas sospechosas ni analizar el grafo.
--
-- A propósito NO se fijan valores de id_usuario: una base de datos ya en uso (la de
-- cualquier integrante del equipo, o la del profesor tras varias entregas) acumula sus
-- propios usuarios reales encima de la semilla original, así que asumir IDs fijos (p. ej.
-- 6-15) puede chocar con cuentas que ya existen. Se deja que la columna SERIAL asigne los
-- IDs, y se usa ON CONFLICT (email) DO NOTHING para que correr este script más de una vez
-- (o sobre una base que ya tenga algunos de estos correos) sea seguro y no falle.
--
-- Cualquier script posterior que necesite referenciar a estos compradores (p. ej. la
-- siembra de reseñas para el grafo de fraude) debe buscarlos por email o por
-- `rol = 'comprador'` en tiempo de ejecución, nunca asumir un ID fijo.
--
-- Contraseña de TODOS los usuarios: "Tiendaya123!" (mismo hash scrypt que ya usan los
-- usuarios semilla del DDL, generado con werkzeug.security). Ver README.md para la tabla
-- de credenciales.
--
-- Cómo correrlo (después de cargar el DDL principal):
-- psql -U postgres -d tiendaya_db -f database/postgres/datos_semilla_usuarios.sql

INSERT INTO usuarios (nombre, email, password_hash, rol, telefono) VALUES
('Maria Torres', 'maria.torres@email.com', 'scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64', 'comprador', '+50255555001'),
('Jose Ramirez', 'jose.ramirez@email.com', 'scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64', 'comprador', '+50255555002'),
('Ana Gutierrez', 'ana.gutierrez@email.com', 'scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64', 'comprador', '+50255555003'),
('Luis Fernandez', 'luis.fernandez@email.com', 'scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64', 'comprador', '+50255555004'),
('Paola Morales', 'paola.morales@email.com', 'scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64', 'comprador', '+50255555005'),
('Roberto Castillo', 'roberto.castillo@email.com', 'scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64', 'comprador', '+50255555006'),
('Daniela Ortiz', 'daniela.ortiz@email.com', 'scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64', 'comprador', '+50255555007'),
('Fernando Aguilar', 'fernando.aguilar@email.com', 'scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64', 'comprador', '+50255555008'),
('Gabriela Ramos', 'gabriela.ramos@email.com', 'scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64', 'comprador', '+50255555009'),
('Andres Vasquez', 'andres.vasquez@email.com', 'scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64', 'comprador', '+50255555010')
ON CONFLICT (email) DO NOTHING;

-- Dirección de envío principal para cada comprador nuevo (por email, no por ID fijo,
-- mismo criterio que arriba). Sin esto, un checkout real con cualquiera de estos
-- compradores falla con "la dirección no pertenece al comprador" -- hallazgo real de QA
-- de la Entrega 2 (solo Sofia Lopez, semilla original, tenía dirección propia).
-- Idempotente: no inserta de nuevo si el comprador ya tiene una dirección marcada como
-- principal.
INSERT INTO direcciones (id_usuario, direccion_linea1, ciudad, departamento_estado, codigo_postal, es_principal)
SELECT u.id_usuario, d.direccion_linea1, d.ciudad, d.departamento_estado, d.codigo_postal, true
FROM usuarios u
JOIN (VALUES
    ('maria.torres@email.com', '3a Avenida 5-10 Zona 1', 'Guatemala', 'Guatemala', '01001'),
    ('jose.ramirez@email.com', '7a Calle 12-45 Zona 9', 'Guatemala', 'Guatemala', '01009'),
    ('ana.gutierrez@email.com', '12 Avenida 3-22 Zona 11', 'Guatemala', 'Guatemala', '01011'),
    ('luis.fernandez@email.com', '5a Calle 8-30 Zona 15', 'Guatemala', 'Guatemala', '01015'),
    ('paola.morales@email.com', '2a Avenida 4-18 Zona 4', 'Quetzaltenango', 'Quetzaltenango', '09001'),
    ('roberto.castillo@email.com', '9a Calle 6-25 Zona 7', 'Guatemala', 'Guatemala', '01007'),
    ('daniela.ortiz@email.com', '4a Avenida 2-14 Zona 2', 'Mixco', 'Guatemala', '01057'),
    ('fernando.aguilar@email.com', '10a Calle 15-50 Zona 13', 'Guatemala', 'Guatemala', '01013'),
    ('gabriela.ramos@email.com', '6a Avenida 9-40 Zona 12', 'Guatemala', 'Guatemala', '01012'),
    ('andres.vasquez@email.com', '1a Calle 3-12 Zona 3', 'Antigua Guatemala', 'Sacatepequez', '03001')
) AS d(email, direccion_linea1, ciudad, departamento_estado, codigo_postal)
    ON u.email = d.email
WHERE NOT EXISTS (
    SELECT 1 FROM direcciones existente
    WHERE existente.id_usuario = u.id_usuario AND existente.es_principal = true
);
