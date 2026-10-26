import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()

# Configuración de conexiones. Cada integrante ajusta sus valores locales en ".env"
# (ver .env.example); los defaults de aquí solo aplican si una variable no está definida.
PG_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DBNAME", "tiendaya_db"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "root")
}

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

# Redis tiene control de acceso (ACL, entrega final): cada servicio se conecta
# con su propio usuario (database/redis/users.acl). REDIS_URL es el de la API
# web (tiendaya_api); REDIS_URL_RELEVO el del relevo del outbox
# (tiendaya_relevo), que solo puede tocar carritos y reservas de oferta. Si
# REDIS_URL_RELEVO no está definida se usa REDIS_URL.
REDIS_URL = os.getenv("REDIS_URL", "redis://tiendaya_api:api_tiendaya_2026@localhost:6379/0")
REDIS_URL_RELEVO = os.getenv("REDIS_URL_RELEVO") or REDIS_URL
# Expiración del carrito por INACTIVIDAD, en segundos. 0 (o negativo) = el
# carrito NO expira (default): cada lectura/escritura le quita el TTL que
# pudiera tener (PERSIST). Un valor positivo reactiva la expiración: el TTL se
# renueva en cada operación y el carrito vence tras ese tiempo sin uso.
CARRITO_TTL_SEGUNDOS = int(os.getenv("CARRITO_TTL_SEGUNDOS", "0"))
# Cuánto dura apartada en el carrito una reserva de oferta relámpago antes de
# liberarse sola si no se completa la compra.
RESERVA_OFERTA_TTL_SEGUNDOS = int(os.getenv("RESERVA_OFERTA_TTL_SEGUNDOS", "60"))
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "tiendaya123")

# Motor de búsqueda del catálogo (Entrega 3). ES_ALIAS_PRODUCTOS es un alias que
# apunta al índice versionado vigente (productos_v<fecha>): reindexar crea un
# índice nuevo y mueve el alias, así el buscador nunca ve un índice a medias.
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ES_ALIAS_PRODUCTOS = os.getenv("ES_ALIAS_PRODUCTOS", "productos")

# Componente vectorial (entrega final): PostgreSQL + pgvector en el contenedor
# "vectores" (puerto 5433, aparte del PostgreSQL transaccional). El backend se
# conecta con el rol vectores_app, que solo puede leer y escribir filas de
# producto_embedding (no cambiar el esquema). MODELO_EMBEDDINGS es el modelo de
# sentence-transformers que convierte texto en vectores de 384 dimensiones; si
# se cambia, hay que regenerar todos los embeddings (el script lo detecta solo).
VECTORES_URI = os.getenv(
    "VECTORES_URL", "postgresql+psycopg2://vectores_app:vectores_app_2026@localhost:5433/tiendaya_vectores"
)
MODELO_EMBEDDINGS = os.getenv("MODELO_EMBEDDINGS", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# Eventos de sincronización (outbox) del checkout: cada cuántos segundos el
# proceso de relevo reintenta los pendientes, y cuántos intentos hace antes de
# dejar un evento marcado como "fallido" para revisión manual.
OUTBOX_INTERVALO_SEGUNDOS = int(os.getenv("OUTBOX_INTERVALO_SEGUNDOS", "15"))
OUTBOX_MAX_INTENTOS = int(os.getenv("OUTBOX_MAX_INTENTOS", "10"))

# Fallas simuladas del checkout (Entrega 3). SOLO para desarrollo y para la
# evidencia de la prueba de falla: con "1", POST /api/checkout acepta
# "simular_falla" en el cuerpo. Con cualquier otro valor ese campo se ignora.
PERMITIR_FALLAS_SIMULADAS = os.getenv("PERMITIR_FALLAS_SIMULADAS", "0") == "1"

# URI de SQLAlchemy armada a partir de PG_CONFIG, para no duplicar la config de conexión.
# quote_plus escapa caracteres especiales que pudiera tener el usuario/contraseña.
SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{quote_plus(PG_CONFIG['user'])}:{quote_plus(PG_CONFIG['password'])}"
    f"@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}"
)
