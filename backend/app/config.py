import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()

# Configuración de conexiones
PG_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")), #Este es el puerto que tiene que cambiar marcos al 5433
    "dbname": os.getenv("PG_DBNAME", "tiendaya_db"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "root") #Esta es la constraseña que tienen que cambiar
}

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

# URI de SQLAlchemy armada a partir de PG_CONFIG, para no duplicar la config de conexión.
# quote_plus escapa caracteres especiales que pudiera tener el usuario/contraseña.
SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{quote_plus(PG_CONFIG['user'])}:{quote_plus(PG_CONFIG['password'])}"
    f"@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}"
)
