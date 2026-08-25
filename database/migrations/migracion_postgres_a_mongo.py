import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from pymongo import MongoClient, ASCENDING

load_dotenv()

# ============================================================================
# CONFIGURACIÓN DE CONEXIONES
# ============================================================================
PG_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DBNAME", "tiendaya_db"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "root")
}

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "tiendaya_nosql")


# ============================================================================
# MAPEO DE ATRIBUTOS POLIMÓRFICOS POR CATEGORÍA
# ============================================================================
# Cada SKU semilla tiene su propio conjunto de atributos reales (no una plantilla
# única por categoría), para que el catálogo documental refleje variación genuina
# entre productos y los filtros por atributo del catálogo tengan sentido.
ATRIBUTOS_POR_SKU = {
    # --- Laptops ---
    "LAP-OMEN-16": {
        "procesador": "AMD Ryzen 9 8940HX", "memoria_ram_gb": 32, "almacenamiento_ssd_gb": 1000,
        "tarjeta_grafica": "NVIDIA RTX 4070", "tasa_refresco_hz": 180, "tamano_pantalla_pulgadas": 16.1
    },
    "LAP-LEN-LEGION5": {
        "procesador": "Intel Core i7-14700HX", "memoria_ram_gb": 16, "almacenamiento_ssd_gb": 1000,
        "tarjeta_grafica": "NVIDIA RTX 4060", "tasa_refresco_hz": 165, "tamano_pantalla_pulgadas": 16.0
    },
    "LAP-MAC-AIR-M3": {
        "procesador": "Apple M3 8-Core CPU / 10-Core GPU", "memoria_ram_gb": 16, "almacenamiento_ssd_gb": 512,
        "tarjeta_grafica": "Gráfica integrada", "tasa_refresco_hz": 60, "tamano_pantalla_pulgadas": 13.6
    },
    "LAP-ACER-ASPIRE3": {
        "procesador": "Intel Core i5-1235U", "memoria_ram_gb": 8, "almacenamiento_ssd_gb": 512,
        "tarjeta_grafica": "Gráfica integrada", "tasa_refresco_hz": 60, "tamano_pantalla_pulgadas": 14.0
    },
    "LAP-ROG-STRIX18": {
        "procesador": "Intel Core i9-14900HX", "memoria_ram_gb": 64, "almacenamiento_ssd_gb": 2000,
        "tarjeta_grafica": "NVIDIA RTX 4090", "tasa_refresco_hz": 240, "tamano_pantalla_pulgadas": 18.0
    },
    # --- Monitores ---
    "MON-27-180HZ": {
        "tamano_pantalla_pulgadas": 27.0, "tipo_panel": "IPS", "resolucion": "1920x1080 Full HD",
        "tasa_refresco_hz": 180, "tiempo_respuesta_ms": 1
    },
    "MON-34-CURVO": {
        "tamano_pantalla_pulgadas": 34.0, "tipo_panel": "VA", "resolucion": "3440x1440 WQHD",
        "tasa_refresco_hz": 165, "tiempo_respuesta_ms": 1
    },
    "MON-24-BASICO": {
        "tamano_pantalla_pulgadas": 23.8, "tipo_panel": "VA", "resolucion": "1920x1080 Full HD",
        "tasa_refresco_hz": 75, "tiempo_respuesta_ms": 4
    },
    "MON-32-OLED": {
        "tamano_pantalla_pulgadas": 31.5, "tipo_panel": "OLED", "resolucion": "3840x2160 4K UHD",
        "tasa_refresco_hz": 240, "tiempo_respuesta_ms": 0.03
    },
    # --- Playeras ---
    "TSH-OVERSIZE-BLK": {
        "talla": "L", "color": "Negro", "material": "100% Algodón Peinado",
        "corte": "Oversize", "instrucciones_lavado": "Lavar con agua fría, no usar secadora"
    },
    "TSH-VINTAGE-WHT": {
        "talla": "M", "color": "Blanco", "material": "100% Algodón Peinado",
        "corte": "Oversize", "instrucciones_lavado": "Lavar con agua fría, no usar secadora"
    },
    "TSH-MINIMAL-GRY": {
        "talla": "M", "color": "Gris Jaspe", "material": "95% Algodón 5% Elastano",
        "corte": "Regular Fit", "instrucciones_lavado": "Lavar con agua fría, no usar secadora"
    },
    "TSH-GRAPHIC-CYBER": {
        "talla": "M", "color": "Negro", "material": "100% Algodón",
        "corte": "Regular Fit", "instrucciones_lavado": "Lavar con agua fría, no usar secadora"
    },
    "TSH-CREW-BLU": {
        "talla": "S", "color": "Azul Marino", "material": "100% Poliéster",
        "corte": "Slim Fit", "instrucciones_lavado": "Lavar con agua fría, no usar secadora"
    },
    "TSH-POLO-RED": {
        "talla": "XL", "color": "Rojo", "material": "100% Algodón Piqué",
        "corte": "Clásico", "instrucciones_lavado": "Lavar con agua fría, no usar secadora"
    },
}


def generar_atributos_heterogeneos(categoria_nombre: str, sku: str, descripcion: str) -> dict:
    if sku in ATRIBUTOS_POR_SKU:
        return ATRIBUTOS_POR_SKU[sku]

    # Cualquier producto fuera de la semilla (creado después, vía script) recibe
    # un atributo genérico de respaldo en lugar de fallar la migración.
    return {"descripcion_detallada": descripcion}


def ejecutar_migracion():
    print("==================================================================")
    print(" INICIANDO PROCESO DE MIGRACIÓN: PostgreSQL -> MongoDB")
    print("==================================================================")

    # 1. Conexión a las bases de datos
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        pg_cursor = pg_conn.cursor(cursor_factory=RealDictCursor)
        print("[✓] Conectado exitosamente a PostgreSQL")
        
        mongo_client = MongoClient(MONGO_URI)
        mongo_db = mongo_client[MONGO_DB_NAME]
        col_productos = mongo_db["productos"]
        col_historial = mongo_db["historial_cambios_productos"]
        print("[✓] Conectado exitosamente a MongoDB")
    except Exception as e:
        print(f"[X] Error de conexión: {e}")
        sys.exit(1)

    # 2. Extracción de datos de PostgreSQL
    query_sql = """
        SELECT 
            p.id_producto,
            p.sku,
            p.nombre,
            p.descripcion,
            p.precio_base,
            p.activo,
            p.fecha_creacion,
            c.id_categoria,
            c.nombre_categoria,
            u.id_usuario AS id_vendedor,
            u.nombre AS nombre_vendedor,
            u.email AS email_vendedor,
            COALESCE(i.stock_disponible, 0) AS stock_disponible
        FROM productos p
        INNER JOIN categorias c ON p.id_categoria = c.id_categoria
        INNER JOIN usuarios u ON p.id_vendedor = u.id_usuario
        LEFT JOIN inventario i ON p.id_producto = i.id_producto
        ORDER BY p.id_producto ASC;
    """

    pg_cursor.execute(query_sql)
    productos_pg = pg_cursor.fetchall()
    print(f"[*] Registros extraídos de PostgreSQL: {len(productos_pg)}")

    documentos_productos = []
    documentos_historial = []
    fecha_migracion = datetime.now(timezone.utc)

    # 3. Transformación y modelado documental
    for p in productos_pg:
        id_producto_str = f"PROD-{p['id_producto']:04d}"
        
        # Generación de URLs simuladas de imágenes embebidas
        imagenes_embebidas = [
            {
                "id_imagen": 1,
                "url": f"https://cdn.tiendaya.com/productos/{p['sku'].lower()}_portada.jpg",
                "es_portada": True,
                "orden": 1
            },
            {
                "id_imagen": 2,
                "url": f"https://cdn.tiendaya.com/productos/{p['sku'].lower()}_detalle.jpg",
                "es_portada": False,
                "orden": 2
            }
        ]

        atributos = generar_atributos_heterogeneos(
            p["nombre_categoria"], 
            p["sku"], 
            p["descripcion"]
        )

        # Documento del Catálogo de Producto
        doc_producto = {
            "_id": id_producto_str,
            "id_sql_origen": p["id_producto"],
            "sku": p["sku"],
            "nombre": p["nombre"],
            "descripcion": p["descripcion"],
            "precio_base": float(p["precio_base"]),
            "activo": p["activo"],
            "categoria": {
                "id_categoria": p["id_categoria"],
                "nombre": p["nombre_categoria"]
            },
            "vendedor": {
                "id_vendedor": p["id_vendedor"],
                "nombre_comercial": p["nombre_vendedor"],
                "email_contacto": p["email_vendedor"]
            },
            "stock_disponible": p["stock_disponible"],
            "imagenes": imagenes_embebidas,
            "atributos": atributos,
            "fecha_creacion": p["fecha_creacion"].isoformat() if p["fecha_creacion"] else fecha_migracion.isoformat(),
            "ultima_actualizacion": fecha_migracion.isoformat()
        }
        documentos_productos.append(doc_producto)

        # Evento inicial para el Historial de Cambios (Event Sourcing)
        doc_evento_creacion = {
            "producto_id": id_producto_str,
            "id_sql_origen": p["id_producto"],
            "tipo_evento": "CREACION_PRODUCTO",
            "fecha_evento": p["fecha_creacion"] if p["fecha_creacion"] else fecha_migracion,
            "usuario_responsable": {
                "id_usuario": p["id_vendedor"],
                "nombre": p["nombre_vendedor"],
                "rol": "vendedor"
            },
            "estado_resultante": {
                "nombre": p["nombre"],
                "descripcion": p["descripcion"],
                "precio_base": float(p["precio_base"]),
                "activo": p["activo"],
                "atributos": atributos
            }
        }
        documentos_historial.append(doc_evento_creacion)

    # 4. Carga de datos en MongoDB (Estrategia idempotente con bulk upsert o recreación)
    print("[*] Escribiendo documentos en MongoDB...")
    col_productos.drop()
    col_historial.drop()

    if documentos_productos:
        col_productos.insert_many(documentos_productos)
        print(f"[✓] {len(documentos_productos)} productos insertados en 'productos'")

    if documentos_historial:
        col_historial.insert_many(documentos_historial)
        print(f"[✓] {len(documentos_historial)} eventos insertados en 'historial_cambios_productos'")

    # 5. Creación de Índices Requeridos
    print("[*] Creando índices en MongoDB...")
    
    # Índice compuesto: Búsqueda por categoría, disponibilidad y ordenamiento por precio
    col_productos.create_index(
        [("categoria.id_categoria", ASCENDING), ("activo", ASCENDING), ("precio_base", ASCENDING)],
        name="idx_categoria_activo_precio"
    )

    # Índice de unicidad para SKU
    col_productos.create_index([("sku", ASCENDING)], unique=True, name="idx_sku_unico")

    # Índice para reconstrucción cronológica en historial
    col_historial.create_index(
        [("producto_id", ASCENDING), ("fecha_evento", ASCENDING)],
        name="idx_historial_producto_fecha"
    )

    print("[✓] Índices creados satisfactoriamente.")
    print("==================================================================")
    print(" MIGRACIÓN COMPLETADA CON ÉXITO")
    print("==================================================================")

    # Cierre de conexiones
    pg_cursor.close()
    pg_conn.close()
    mongo_client.close()


if __name__ == "__main__":
    ejecutar_migracion()