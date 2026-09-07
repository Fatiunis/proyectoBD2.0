from datetime import timezone, timedelta

from flask_sqlalchemy import SQLAlchemy
from pymongo import MongoClient

from .config import MONGO_URI

# Guatemala no tiene horario de verano: su offset es siempre UTC-6, así que un
# offset fijo alcanza (no hace falta zoneinfo/tzdata, que además no está
# instalado por defecto en Windows). Se pasa al MongoClient vía
# tz_aware=True/tzinfo para que CUALQUIER datetime nativo leído de
# col_productos/col_historial venga con este tzinfo en vez de naive-UTC -- así
# evitamos que .isoformat() genere strings sin offset que el frontend (new
# Date(iso)) interprete como hora local del navegador. El instante real
# almacenado no cambia; solo cómo se representa al leerlo.
ZONA_GUATEMALA = timezone(timedelta(hours=-6))

client = MongoClient(MONGO_URI, tz_aware=True, tzinfo=ZONA_GUATEMALA)
mongo_db = client["tiendaya_nosql"]
col_productos = mongo_db["productos"]
col_historial = mongo_db["historial_cambios_productos"]

# ORM oficial para PostgreSQL (ver docs/STACK.md). Se inicializa aquí (patrón
# application factory) y se conecta a la app real con db.init_app(app) en
# app/__init__.py -> create_app(). El driver DBAPI subyacente sigue siendo
# psycopg2 (ver SQLALCHEMY_DATABASE_URI en config.py), pero ya no se importa
# ni se usa directamente desde los blueprints.
db = SQLAlchemy()
