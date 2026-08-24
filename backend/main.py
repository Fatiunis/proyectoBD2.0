from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient, ASCENDING
from pydantic import BaseModel

app = FastAPI(title="TiendaYa API - Catálogo & Historial")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client["tiendaya_nosql"]
col_productos = db["productos"]
col_historial = db["historial_cambios_productos"]

class ProductoInput(BaseModel):
    sku: str
    nombre: str
    descripcion: str
    precio_base: float
    id_categoria: int
    nombre_categoria: str
    id_vendedor: int
    nombre_vendedor: str
    stock_disponible: int
    atributos: Dict[str, Any]
    imagenes: Optional[List[Dict[str, Any]]] = []

@app.get("/api/categorias")
def get_categorias():
    categorias = col_productos.distinct("categoria")
    return categorias

@app.get("/api/productos")
def get_productos(categoria_id: Optional[int] = None):
    query = {"activo": True}
    if categoria_id is not None:
        query["categoria.id_categoria"] = categoria_id
    
    docs = list(col_productos.find(query, {"_id": 1, "sku": 1, "nombre": 1, "precio_base": 1, "categoria": 1, "atributos": 1, "imagenes": 1}).sort("precio_base", ASCENDING))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs

@app.get("/api/productos/{producto_id}")
def get_producto_detalle(producto_id: str):
    doc = col_productos.find_one({"_id": producto_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    doc["_id"] = str(doc["_id"])
    return doc

@app.post("/api/productos")
def crear_o_actualizar_producto(prod: ProductoInput):
    doc_id = f"PROD-{prod.sku.replace(' ', '-').upper()}"
    now = datetime.now(timezone.utc)
    
    nuevo_doc = {
        "_id": doc_id,
        "sku": prod.sku,
        "nombre": prod.nombre,
        "descripcion": prod.descripcion,
        "precio_base": prod.precio_base,
        "activo": True,
        "categoria": {
            "id_categoria": prod.id_categoria,
            "nombre": prod.nombre_categoria
        },
        "vendedor": {
            "id_vendedor": prod.id_vendedor,
            "nombre_comercial": prod.nombre_vendedor,
            "email_contacto": f"{prod.nombre_vendedor.lower().replace(' ', '')}@tiendaya.com"
        },
        "stock_disponible": prod.stock_disponible,
        "imagenes": prod.imagenes if prod.imagenes else [{"url": "https://via.placeholder.com/300", "es_portada": True, "orden": 1}],
        "atributos": prod.atributos,
        "ultima_actualizacion": now.isoformat()
    }
    
    # Upsert en la colección de productos
    col_productos.update_one({"_id": doc_id}, {"$set": nuevo_doc}, upsert=True)
    
    # Registro de evento inmutable en historial (Event Sourcing)
    evento = {
        "producto_id": doc_id,
        "tipo_evento": "ACTUALIZACION_PANEL_ADMIN",
        "fecha_evento": now,
        "usuario_responsable": {
            "id_usuario": prod.id_vendedor,
            "nombre": prod.nombre_vendedor,
            "rol": "administrador"
        },
        "estado_resultante": {
            "nombre": prod.nombre,
            "descripcion": prod.descripcion,
            "precio_base": prod.precio_base,
            "activo": True,
            "atributos": prod.atributos
        }
    }
    col_historial.insert_one(evento)
    
    return {"mensaje": "Producto guardado con éxito", "producto_id": doc_id}

@app.get("/api/historial/{producto_id}")
def reconstruir_historial(producto_id: str, fecha_corte: str = Query(...)):
    try:
        dt_corte = datetime.fromisoformat(fecha_corte.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usar ISO 8601 (YYYY-MM-DDTHH:MM:SS)")

    pipeline = [
        {"$match": {"producto_id": producto_id, "fecha_evento": {"$lte": dt_corte}}},
        {"$sort": {"fecha_evento": -1}},
        {"$limit": 1},
        {
            "$project": {
                "_id": 0,
                "producto_id": 1,
                "fecha_vigencia_evento": "$fecha_evento",
                "tipo_evento": 1,
                "responsable": "$usuario_responsable.nombre",
                "estado_en_esa_fecha": "$estado_resultante"
            }
        }
    ]
    
    res = list(col_historial.aggregate(pipeline))
    if not res:
        raise HTTPException(status_code=404, detail="No existe estado registrado previo a la fecha especificada.")
    return res[0]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)