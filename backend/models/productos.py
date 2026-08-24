from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class ImagenProducto(BaseModel):
    id_imagen: Optional[int] = 1
    url: str
    es_portada: bool = False
    orden: int = 1

class CategoriaProducto(BaseModel):
    id_categoria: int
    nombre: str

class VendedorProducto(BaseModel):
    id_vendedor: int
    nombre_comercial: str
    email_contacto: Optional[str] = None

class ProductoBase(BaseModel):
    sku: str
    nombre: str
    descripcion: str
    precio_base: float = Field(..., ge=0)
    stock_disponible: int = Field(0, ge=0)
    activo: bool = True
    categoria: CategoriaProducto
    vendedor: VendedorProducto
    imagenes: List[ImagenProducto] = []
    atributos: Dict[str, Any] = {}

class ProductoCreate(BaseModel):
    sku: str
    nombre: str
    descripcion: str
    precio_base: float = Field(..., ge=0)
    stock_disponible: int = Field(0, ge=0)
    id_categoria: int
    nombre_categoria: str
    id_vendedor: int
    nombre_vendedor: str
    atributos: Dict[str, Any] = {}
    imagenes: Optional[List[Dict[str, Any]]] = []

class EventoHistorial(BaseModel):
    producto_id: str
    tipo_evento: str
    fecha_evento: datetime
    usuario_responsable: Dict[str, Any]
    estado_resultante: Dict[str, Any]