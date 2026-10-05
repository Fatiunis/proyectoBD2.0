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

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CARRITO_TTL_SEGUNDOS = int(os.getenv("CARRITO_TTL_SEGUNDOS", "1800"))
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
