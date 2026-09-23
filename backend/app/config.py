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

# URI de SQLAlchemy armada a partir de PG_CONFIG, para no duplicar la config de conexión.
# quote_plus escapa caracteres especiales que pudiera tener el usuario/contraseña.
SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{quote_plus(PG_CONFIG['user'])}:{quote_plus(PG_CONFIG['password'])}"
    f"@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}"
)
