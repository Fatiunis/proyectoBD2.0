from flask_sqlalchemy import SQLAlchemy
from pymongo import MongoClient

from .config import MONGO_URI

client = MongoClient(MONGO_URI)
mongo_db = client["tiendaya_nosql"]
col_productos = mongo_db["productos"]
col_historial = mongo_db["historial_cambios_productos"]

# ORM oficial para PostgreSQL (ver docs/STACK.md). Se inicializa aquí (patrón
# application factory) y se conecta a la app real con db.init_app(app) en
# app/__init__.py -> create_app(). El driver DBAPI subyacente sigue siendo
# psycopg2 (ver SQLALCHEMY_DATABASE_URI en config.py), pero ya no se importa
# ni se usa directamente desde los blueprints.
db = SQLAlchemy()
