import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from pymongo import MongoClient, ASCENDING

# La consola de Windows no usa UTF-8 por defecto y falla al imprimir "✓"/"✗";
# forzamos la codificación de salida para que el script corra igual en todo el equipo.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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

# Guatemala usa UTC-6 fijo todo el año (sin horario de verano), consistente
# con backend/app/extensions.py.
ZONA_GUATEMALA = timezone(timedelta(hours=-6))

# ============================================================================
# FOTOS REALES POR SKU (Unsplash, licencia libre de uso comercial)
# ============================================================================
# Portada y detalle por SKU. Los SKU que no aparezcan aquí (ej. productos de
# prueba creados a mano) reciben una foto genérica según su categoría.
_UNSPLASH = "https://images.unsplash.com/{}?auto=format&fit=crop&w={}&q=80"

IMAGENES_POR_SKU = {
    "LAP-OMEN-16":       ("photo-1603302576837-37561b2e2302", "photo-1640955014216-75201056c829"),
    "LAP-LEN-LEGION5":   ("photo-1611078489935-0cb964de46d6", "photo-1630794180018-433d915c34ac"),
    "LAP-MAC-AIR-M3":    ("photo-1517336714731-489689fd1ca8", "photo-1629131726692-1accd0c53ce0"),
    "LAP-ACER-ASPIRE3":  ("photo-1637329428580-8fddec26fa67", "photo-1663354027456-ce6a7e07d212"),
    "LAP-ROG-STRIX18":   ("photo-1658262530868-f7460e2f071f", "photo-1684127987312-43455fd95925"),
    "MON-27-180HZ":      ("photo-1534423861386-85a16f5d13fd", "photo-1593305841991-05c297ba4575"),
    "MON-34-CURVO":      ("photo-1547658718-1cdaa0852790", "photo-1585792180666-f7347c490ee2"),
    "MON-24-BASICO":     ("photo-1484788984921-03950022c9ef", "photo-1527443224154-c4a3942d3acf"),
    "MON-32-OLED":       ("photo-1614179924047-e1ab49a0a0cf", "photo-1691480195680-144318cfa695"),
    "TSH-OVERSIZE-BLK":  ("photo-1571455786673-9d9d6c194f90", "photo-1726140872004-850c80900ae3"),
    "TSH-VINTAGE-WHT":   ("photo-1581655353564-df123a1eb820", "photo-1521572163474-6864f9cf17ab"),
    "TSH-MINIMAL-GRY":   ("photo-1564584217132-2271feaeb3c5", "photo-1706550632237-24b904d8097a"),
    "TSH-GRAPHIC-CYBER": ("photo-1775979654476-89575df179bd", "photo-1655141559812-42f8c1e8942d"),
    "TSH-CREW-BLU":      ("photo-1734249030515-9fdbaa7724aa", "photo-1739047599736-4e1699c7df56"),
    "TSH-POLO-RED":      ("photo-1760287363713-a864ca9b1b1f", "photo-1565562193381-576c27829023"),
}

# Foto genérica de respaldo por categoría, para SKU nuevos que no estén en el mapa de arriba.
IMAGEN_GENERICA_POR_CATEGORIA = {
    "Laptops":   ("photo-1603302576837-37561b2e2302", "photo-1640955014216-75201056c829"),
    "Monitores": ("photo-1534423861386-85a16f5d13fd", "photo-1593305841991-05c297ba4575"),
    "Playeras":  ("photo-1571455786673-9d9d6c194f90", "photo-1726140872004-850c80900ae3"),
    # Subcategorías agregadas por la semilla masiva (datos_semilla_masivos.sql)
    "Celulares":    ("photo-1511707171634-5f897ff02aa9", "photo-1598327105666-5b89351aff97"),
    "Audífonos":    ("photo-1505740420928-5e560c06d30e", "photo-1546435770-a3e426bf472b"),
    "Teclados":     ("photo-1587829741301-dc798b83add3", "photo-1595225476474-87563907a212"),
    "Mouse":        ("photo-1615663245857-ac93bb7c39e7", "photo-1527864550417-7fd91fc51a46"),
    "Tablets":      ("photo-1544244015-0df4b3ffc6b0", "photo-1585790050230-5dd28404ccb9"),
    "Smartwatches": ("photo-1546868871-7041f2a55e12", "photo-1579586337278-3befd40fd17a"),
    "Jeans":        ("photo-1542272604-787c3835535d", "photo-1604176354204-9268737828e4"),
    "Sudaderas":    ("photo-1556821840-3a63f95609a7", "photo-1620799140408-edc6dcb6d633"),
    "Tenis":        ("photo-1542291026-7eec264c27ff", "photo-1600185365483-26d7a4cc7519"),
    "Vestidos":     ("photo-1595777457583-95e059d581b8", "photo-1515372039744-b8f02a3ae446"),
    "Gorras":       ("photo-1588850561407-ed78c282e89b", "photo-1521369909029-2afed882baee"),
    "Electrodomésticos de Cocina": ("photo-1570222094114-d054a817e56b", "photo-1585515320310-259814833e62"),
    "Utensilios de Cocina":        ("photo-1590794056226-79ef3a8147e1", "photo-1584269600464-37b1b58a9fe7"),
    "Bicicletas":         ("photo-1485965120184-e220f721d03e", "photo-1571068316344-75bc76f77890"),
    "Pesas y Mancuernas": ("photo-1638536532686-d610adfc8e5c", "photo-1583454110551-21f2fa2afe61"),
    "Tapetes de Yoga":    ("photo-1601925260368-ae2f83cf8b7f", "photo-1592432678016-e910b452f9a2"),
    "Mochilas":           ("photo-1553062407-98eeb64c6a62", "photo-1622560480605-d83c853bc5c3"),
    "Perfumes":           ("photo-1541643600914-78b084683601", "photo-1523293182086-7651a899d37f"),
    "Cuidado de la Piel": ("photo-1556228578-8c89e6adf883", "photo-1571781926291-c477ebfd024b"),
}

# ============================================================================
# SEMILLA MASIVA (1000 productos): atributos e imágenes por SKU
# ============================================================================
# Generado junto con database/postgres/datos_semilla_masivos.sql por
# generar_semilla_masiva.py. Cada SKU trae sus atributos (según el esquema_atributos de
# su subcategoría, más atributos personalizados en ~20% de los casos) y de 1 a 3 photo-id
# de Unsplash (el primero es la portada). Si el archivo no existe, la migración sigue
# funcionando igual que antes para los 15 productos originales.
RUTA_CATALOGO_MASIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos_semilla_masivos_catalogo.json")
if os.path.exists(RUTA_CATALOGO_MASIVO):
    with open(RUTA_CATALOGO_MASIVO, encoding="utf-8") as _f:
        CATALOGO_SEMILLA_MASIVA = json.load(_f)
else:
    CATALOGO_SEMILLA_MASIVA = {}


def imagenes_para_producto(sku, nombre_categoria):
    """Devuelve el arreglo de imágenes embebidas (la primera es la portada) para un producto."""
    ids = (IMAGENES_POR_SKU.get(sku)
           or (CATALOGO_SEMILLA_MASIVA.get(sku) or {}).get("imagenes")
           or IMAGEN_GENERICA_POR_CATEGORIA.get(nombre_categoria))
    if not ids:
        return []
    return [
        {"id_imagen": i, "url": _UNSPLASH.format(id_foto, 1200), "es_portada": i == 1, "orden": i}
        for i, id_foto in enumerate(ids, start=1)
    ]


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
    if sku in CATALOGO_SEMILLA_MASIVA:
        return CATALOGO_SEMILLA_MASIVA[sku]["atributos"]

    # Cualquier producto fuera de la semilla (creado después, vía script) recibe
    # un atributo genérico de respaldo en lugar de fallar la migración.
    return {"descripcion_detallada": descripcion}


def ejecutar_migracion(incremental=False):
    """
    Modo completo (por defecto): borra y recrea `productos` e `historial_cambios_productos`
    desde PostgreSQL -- se pierden las ediciones hechas desde el panel admin.

    Modo incremental (--incremental): NO borra nada. Solo inserta los productos de
    PostgreSQL que todavía no tienen documento en Mongo (ni por id_sql_origen ni por sku),
    con su evento CREACION_PRODUCTO en el historial. Los documentos existentes, sus
    ediciones del admin y sus eventos quedan intactos. Es idempotente: correrlo de nuevo
    no inserta nada. Es el modo recomendado para cargar la semilla masiva sobre una base
    que ya está en uso.
    """
    print("==================================================================")
    print(" INICIANDO PROCESO DE MIGRACIÓN: PostgreSQL -> MongoDB"
          + (" (INCREMENTAL)" if incremental else ""))
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
    fecha_migracion = datetime.now(ZONA_GUATEMALA)

    # 3. Transformación y modelado documental
    for p in productos_pg:
        id_producto_str = f"PROD-{p['id_producto']:04d}"
        
        # Imágenes reales (Unsplash) embebidas, mapeadas por SKU/categoría
        imagenes_embebidas = imagenes_para_producto(p["sku"], p["nombre_categoria"])

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
    if incremental:
        # Se descartan los productos que ya tienen documento: por id_sql_origen (migrados o
        # creados desde el admin) o por sku (defensa extra, el sku es único en ambos lados).
        ids_existentes = set(col_productos.distinct("id_sql_origen"))
        skus_existentes = set(col_productos.distinct("sku"))
        nuevos = [
            i for i, doc in enumerate(documentos_productos)
            if doc["id_sql_origen"] not in ids_existentes and doc["sku"] not in skus_existentes
        ]
        documentos_productos = [documentos_productos[i] for i in nuevos]
        documentos_historial = [documentos_historial[i] for i in nuevos]
        print(f"[*] Modo incremental: {len(documentos_productos)} producto(s) nuevo(s) por insertar; "
              f"{len(productos_pg) - len(documentos_productos)} ya existían en Mongo y no se tocan")
    else:
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

    # Índice de texto para la búsqueda del catálogo (GET /api/productos?q=)
    col_productos.create_index(
        [("nombre", "text"), ("descripcion", "text"), ("sku", "text")],
        weights={"nombre": 5, "sku": 3, "descripcion": 1},
        default_language="spanish",
        name="idx_texto_busqueda"
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
    parser = argparse.ArgumentParser(description="Migra el catálogo de productos de PostgreSQL a MongoDB.")
    parser.add_argument(
        "--incremental", action="store_true",
        help="No borra las colecciones: solo inserta los productos de Postgres que aún no están en Mongo.",
    )
    ejecutar_migracion(incremental=parser.parse_args().incremental)