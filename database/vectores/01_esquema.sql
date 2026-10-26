-- ============================================================================
-- COMPONENTE VECTORIAL (ENTREGA FINAL): PostgreSQL + pgvector
-- ============================================================================
-- Base "tiendaya_vectores" del contenedor "vectores" (docker-compose.yml).
-- La imagen oficial ejecuta este archivo UNA sola vez, cuando el volumen
-- vectores_data se crea vacío. Para recrearlo desde cero:
--   docker compose rm -sf vectores && docker volume rm proyectobd20_vectores_data
--   docker compose up -d vectores
--
-- Qué guarda: un embedding (vector de 384 dimensiones) por producto, calculado
-- a partir de su nombre, categoría y descripción con el modelo multilingüe
-- sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2. Es una
-- PROYECCIÓN derivada del catálogo (fuente de verdad: MongoDB, colección
-- "productos"): si se pierde, se regenera con
--   python database/migrations/generar_embeddings_productos.py
--
-- Detalle de la decisión: docs/decisiones/ADR-008-componente-vectorial.md
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS producto_embedding (
    -- _id del producto en MongoDB (p. ej. "PROD-0001"). No hay llave foránea:
    -- el producto vive en otro motor, igual que en las líneas de pedido.
    producto_id     VARCHAR(64) PRIMARY KEY,
    -- Copias mínimas del catálogo para filtrar sin ir a Mongo.
    id_categoria    INT,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    -- SHA-256 del texto que se convirtió en vector y nombre del modelo: si
    -- ninguno de los dos cambió, el embedding vigente sigue sirviendo y no se
    -- recalcula (regenerar es idempotente y barato).
    texto_hash      CHAR(64) NOT NULL,
    modelo          VARCHAR(120) NOT NULL,
    embedding       vector(384) NOT NULL,
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índice aproximado de vecinos más cercanos (HNSW) con distancia coseno, el
-- operador <=> de las consultas. m / ef_construction son los valores por
-- defecto de pgvector, explícitos para documentarlos.
CREATE INDEX IF NOT EXISTS idx_producto_embedding_hnsw
    ON producto_embedding USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_producto_embedding_categoria
    ON producto_embedding (id_categoria);


-- ---------------------------------------------------------------------------
-- Roles con mínimo privilegio. "vectores_admin" (POSTGRES_USER del compose)
-- es el dueño de la base y el único que puede cambiar el esquema.
-- ---------------------------------------------------------------------------

-- Backend y script de embeddings: leen y escriben filas, pero no pueden crear,
-- alterar ni borrar tablas.
CREATE ROLE vectores_app LOGIN PASSWORD 'vectores_app_2026';
GRANT CONNECT ON DATABASE tiendaya_vectores TO vectores_app;
GRANT USAGE ON SCHEMA public TO vectores_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON producto_embedding TO vectores_app;

-- Visores y reportes: solo lectura.
CREATE ROLE vectores_lector LOGIN PASSWORD 'vectores_lector_2026';
GRANT CONNECT ON DATABASE tiendaya_vectores TO vectores_lector;
GRANT USAGE ON SCHEMA public TO vectores_lector;
GRANT SELECT ON producto_embedding TO vectores_lector;

-- Nadie más que el dueño crea objetos en el esquema público.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
