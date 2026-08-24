from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGO_DB_NAME", "tiendaya_nosql")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Colecciones principales para la Entrega 1
col_productos = db["productos"]
col_historial = db["historial_cambios_productos"]

def get_db():
    return db