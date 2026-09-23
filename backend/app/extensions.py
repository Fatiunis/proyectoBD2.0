from datetime import timezone, timedelta

import redis
from flask_sqlalchemy import SQLAlchemy
from neo4j import GraphDatabase
from pymongo import MongoClient

from .config import MONGO_URI, REDIS_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

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
col_resenas = mongo_db["resenas"]

# ORM oficial para PostgreSQL (ver docs/STACK.md). Se inicializa aquí (patrón
# application factory) y se conecta a la app real con db.init_app(app) en
# app/__init__.py -> create_app(). El driver DBAPI subyacente sigue siendo
# psycopg2 (ver SQLALCHEMY_DATABASE_URI en config.py), pero ya no se importa
# ni se usa directamente desde los blueprints.
db = SQLAlchemy()

# Cliente de Redis para carrito de compras y ofertas de inventario limitado
# (Entrega 2). decode_responses=True para trabajar con strings en vez de bytes,
# consistente con el resto del código que no maneja bytes crudos.
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Driver de Neo4j para el grafo de detección de fraude en reseñas (Entrega 2).
neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
