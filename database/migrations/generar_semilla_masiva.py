"""
Generador de la SEMILLA MASIVA de TiendaYa: 1000 productos + 40 tiendas (vendedores).

Qué produce (ambos archivos se versionan en el repo, igual que el resto de la semilla):
  1. database/postgres/datos_semilla_masivos.sql
       Subcategorías nuevas (con su esquema_atributos), 40 usuarios con rol 'vendedor'
       (las "tiendas"), 1000 productos y su inventario inicial. Idempotente: ON CONFLICT
       por nombre_categoria / email / sku / id_producto, sin asumir IDs fijos.
  2. database/migrations/datos_semilla_masivos_catalogo.json
       Por SKU: los atributos polimórficos (según el esquema de su subcategoría, más
       atributos personalizados en ~20% de los productos) y los photo-id de Unsplash
       (1 a 3 por producto). migracion_postgres_a_mongo.py lo lee para construir los
       documentos del catálogo, igual que ya hace con ATRIBUTOS_POR_SKU / IMAGENES_POR_SKU.

Es DETERMINÍSTICO (semilla fija del generador aleatorio): volver a correrlo produce
exactamente los mismos archivos, así que no hay riesgo de que dos integrantes del equipo
terminen con catálogos distintos. Solo hace falta correrlo si se cambia este script;
para cargar los datos basta con los archivos ya generados (ver README.md).

Todas las fotos usadas se verificaron (HTTP 200 contra images.unsplash.com y revisión
visual del contenido) antes de incluirlas en los pools de abajo.

Uso:
    venv\\Scripts\\python.exe database/migrations/generar_semilla_masiva.py
"""
import json
import os
import random
import sys
from collections import Counter, OrderedDict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUTA_SQL = os.path.join(RAIZ, "database", "postgres", "datos_semilla_masivos.sql")
RUTA_JSON = os.path.join(RAIZ, "database", "migrations", "datos_semilla_masivos_catalogo.json")

SEMILLA_ALEATORIA = 20260923
TOTAL_PRODUCTOS = 1000
PROPORCION_PERSONALIZADOS = 0.20

# Mismo hash scrypt de "Tiendaya123!" que usan el DDL y datos_semilla_usuarios.sql.
HASH_TIENDAYA123 = (
    "scrypt:32768:8:1$qMLuQMLHIv6hRGzg$835b1fe32b5e7269d49e2db4e990cd69648bbb8c641e7e0a3e013b"
    "8100263855f5bcb271dc9a3a16894391a3c7df349f69eee34d6df24de9ea0c41d42f16ca64"
)

# ============================================================================
# 1. TAXONOMÍA: CATEGORÍAS PADRE Y SUBCATEGORÍAS NUEVAS
# ============================================================================
# Las categorías existentes (Tecnología, Laptops, Monitores, Moda y Ropa, Playeras) NO se
# tocan: solo se reutilizan como padre/hoja buscándolas por nombre.
CATEGORIAS_PADRE_NUEVAS = [
    ("Hogar y Cocina", "Electrodomésticos, utensilios y artículos para el hogar"),
    ("Deportes y Fitness", "Ciclismo, entrenamiento, yoga y equipo para actividades al aire libre"),
    ("Belleza y Cuidado Personal", "Fragancias y productos para el cuidado de la piel"),
]


def _attr(clave, etiqueta, tipo):
    return {"clave": clave, "etiqueta": etiqueta, "tipo": tipo}


# (nombre, descripción, padre, esquema_atributos)
SUBCATEGORIAS_NUEVAS = [
    ("Celulares", "Smartphones de gama de entrada, media y alta", "Tecnología", [
        _attr("marca", "Marca", "texto"),
        _attr("almacenamiento_gb", "Almacenamiento (GB)", "numero"),
        _attr("memoria_ram_gb", "RAM (GB)", "numero"),
        _attr("tamano_pantalla_pulgadas", "Tamaño de pantalla (pulgadas)", "numero"),
        _attr("camara_principal_mp", "Cámara principal (MP)", "numero"),
        _attr("bateria_mah", "Batería (mAh)", "numero"),
        _attr("red", "Red móvil", "texto"),
        _attr("color", "Color", "texto"),
    ]),
    ("Audífonos", "Audífonos over-ear, in-ear y true wireless", "Tecnología", [
        _attr("marca", "Marca", "texto"),
        _attr("tipo", "Tipo", "texto"),
        _attr("conexion", "Conexión", "texto"),
        _attr("cancelacion_ruido", "Cancelación de ruido", "texto"),
        _attr("autonomia_horas", "Autonomía (horas)", "numero"),
        _attr("color", "Color", "texto"),
    ]),
    ("Teclados", "Teclados mecánicos, de membrana, gaming y de oficina", "Tecnología", [
        _attr("marca", "Marca", "texto"),
        _attr("tipo_switch", "Tipo de switch", "texto"),
        _attr("formato", "Formato", "texto"),
        _attr("conexion", "Conexión", "texto"),
        _attr("retroiluminacion", "Retroiluminación", "texto"),
        _attr("distribucion", "Distribución de teclas", "texto"),
    ]),
    ("Mouse", "Mouse gaming, ergonómicos e inalámbricos", "Tecnología", [
        _attr("marca", "Marca", "texto"),
        _attr("dpi_maximo", "DPI máximo", "numero"),
        _attr("conexion", "Conexión", "texto"),
        _attr("numero_botones", "Número de botones", "numero"),
        _attr("peso_gramos", "Peso (gramos)", "numero"),
        _attr("uso", "Uso recomendado", "texto"),
    ]),
    ("Tablets", "Tablets para estudio, trabajo y entretenimiento", "Tecnología", [
        _attr("marca", "Marca", "texto"),
        _attr("tamano_pantalla_pulgadas", "Tamaño de pantalla (pulgadas)", "numero"),
        _attr("almacenamiento_gb", "Almacenamiento (GB)", "numero"),
        _attr("memoria_ram_gb", "RAM (GB)", "numero"),
        _attr("conectividad", "Conectividad", "texto"),
        _attr("color", "Color", "texto"),
    ]),
    ("Smartwatches", "Relojes inteligentes y bandas de actividad", "Tecnología", [
        _attr("marca", "Marca", "texto"),
        _attr("tamano_caja_mm", "Tamaño de caja (mm)", "numero"),
        _attr("material_correa", "Material de la correa", "texto"),
        _attr("gps_integrado", "GPS integrado", "texto"),
        _attr("resistencia_agua", "Resistencia al agua", "texto"),
        _attr("autonomia_dias", "Autonomía (días)", "numero"),
        _attr("color", "Color", "texto"),
    ]),
    ("Jeans", "Pantalones de mezclilla para dama y caballero", "Moda y Ropa", [
        _attr("talla_cintura", "Talla de cintura", "numero"),
        _attr("largo_pierna", "Largo de pierna", "numero"),
        _attr("corte", "Corte", "texto"),
        _attr("color_lavado", "Color / lavado", "texto"),
        _attr("material", "Material", "texto"),
        _attr("genero", "Género", "texto"),
    ]),
    ("Sudaderas", "Sudaderas con capucha, cuello redondo y con cierre", "Moda y Ropa", [
        _attr("talla", "Talla", "texto"),
        _attr("color", "Color", "texto"),
        _attr("material", "Material", "texto"),
        _attr("estilo", "Estilo", "texto"),
        _attr("genero", "Género", "texto"),
    ]),
    ("Tenis", "Calzado deportivo y casual", "Moda y Ropa", [
        _attr("marca", "Marca", "texto"),
        _attr("talla_us", "Talla (US)", "numero"),
        _attr("color", "Color", "texto"),
        _attr("uso", "Uso", "texto"),
        _attr("material_exterior", "Material exterior", "texto"),
        _attr("genero", "Género", "texto"),
    ]),
    ("Vestidos", "Vestidos casuales, de fiesta y de playa", "Moda y Ropa", [
        _attr("talla", "Talla", "texto"),
        _attr("color", "Color", "texto"),
        _attr("largo", "Largo", "texto"),
        _attr("material", "Material", "texto"),
        _attr("ocasion", "Ocasión", "texto"),
        _attr("estampado", "Estampado", "texto"),
    ]),
    ("Gorras", "Gorras, snapbacks y sombreros tipo bucket", "Moda y Ropa", [
        _attr("estilo", "Estilo", "texto"),
        _attr("color", "Color", "texto"),
        _attr("material", "Material", "texto"),
        _attr("ajuste", "Ajuste", "texto"),
        _attr("bordado", "Bordado", "texto"),
    ]),
    ("Electrodomésticos de Cocina", "Cafeteras, licuadoras, batidoras y pequeños electrodomésticos", "Hogar y Cocina", [
        _attr("marca", "Marca", "texto"),
        _attr("tipo_electrodomestico", "Tipo de electrodoméstico", "texto"),
        _attr("potencia_w", "Potencia (W)", "numero"),
        _attr("capacidad_litros", "Capacidad (litros)", "numero"),
        _attr("color", "Color", "texto"),
        _attr("garantia_meses", "Garantía (meses)", "numero"),
    ]),
    ("Utensilios de Cocina", "Ollas, sartenes, cacerolas y cuchillería", "Hogar y Cocina", [
        _attr("tipo_utensilio", "Tipo de utensilio", "texto"),
        _attr("material", "Material", "texto"),
        _attr("diametro_cm", "Diámetro / largo (cm)", "numero"),
        _attr("piezas", "Número de piezas", "numero"),
        _attr("apto_induccion", "Apto para inducción", "texto"),
        _attr("color", "Color", "texto"),
    ]),
    ("Bicicletas", "Bicicletas de ruta, urbanas, fixie, híbridas y gravel", "Deportes y Fitness", [
        _attr("tipo_bicicleta", "Tipo de bicicleta", "texto"),
        _attr("tamano_aro", "Tamaño de aro (pulgadas)", "numero"),
        _attr("material_marco", "Material del marco", "texto"),
        _attr("numero_velocidades", "Número de velocidades", "numero"),
        _attr("talla_marco", "Talla del marco", "texto"),
        _attr("color", "Color", "texto"),
    ]),
    ("Pesas y Mancuernas", "Mancuernas, barras, discos y racks para entrenamiento", "Deportes y Fitness", [
        _attr("tipo_equipo", "Tipo de equipo", "texto"),
        _attr("peso_kg", "Peso (kg)", "numero"),
        _attr("material", "Material", "texto"),
        _attr("presentacion", "Presentación", "texto"),
        _attr("color", "Color", "texto"),
    ]),
    ("Tapetes de Yoga", "Tapetes para yoga, pilates y entrenamiento en casa", "Deportes y Fitness", [
        _attr("material", "Material", "texto"),
        _attr("grosor_mm", "Grosor (mm)", "numero"),
        _attr("largo_cm", "Largo (cm)", "numero"),
        _attr("antideslizante", "Superficie antideslizante", "texto"),
        _attr("color", "Color", "texto"),
    ]),
    ("Mochilas", "Mochilas urbanas, escolares, para laptop y de senderismo", "Deportes y Fitness", [
        _attr("capacidad_litros", "Capacidad (litros)", "numero"),
        _attr("material", "Material", "texto"),
        _attr("uso", "Uso", "texto"),
        _attr("compartimento_laptop", "Compartimento para laptop", "texto"),
        _attr("impermeable", "Impermeable", "texto"),
        _attr("color", "Color", "texto"),
    ]),
    ("Perfumes", "Fragancias para dama, caballero y unisex", "Belleza y Cuidado Personal", [
        _attr("marca", "Marca", "texto"),
        _attr("concentracion", "Concentración", "texto"),
        _attr("volumen_ml", "Volumen (ml)", "numero"),
        _attr("genero", "Género", "texto"),
        _attr("familia_olfativa", "Familia olfativa", "texto"),
    ]),
    ("Cuidado de la Piel", "Sérums, cremas, limpiadores y protectores solares", "Belleza y Cuidado Personal", [
        _attr("marca", "Marca", "texto"),
        _attr("tipo_producto", "Tipo de producto", "texto"),
        _attr("tipo_piel", "Tipo de piel", "texto"),
        _attr("contenido_ml", "Contenido (ml)", "numero"),
        _attr("ingrediente_principal", "Ingrediente principal", "texto"),
    ]),
]

# Claves del esquema de cada subcategoría (incluye las 3 hojas que ya existían en el DDL).
ESQUEMA_CLAVES = {
    "Laptops": ["procesador", "memoria_ram_gb", "almacenamiento_ssd_gb", "tarjeta_grafica",
                "tasa_refresco_hz", "tamano_pantalla_pulgadas"],
    "Monitores": ["tamano_pantalla_pulgadas", "tipo_panel", "resolucion", "tasa_refresco_hz",
                  "tiempo_respuesta_ms"],
    "Playeras": ["talla", "color", "material", "corte", "instrucciones_lavado"],
}
for _nombre, _desc, _padre, _esquema in SUBCATEGORIAS_NUEVAS:
    ESQUEMA_CLAVES[_nombre] = [a["clave"] for a in _esquema]

# ============================================================================
# 2. FOTOS DE UNSPLASH POR SUBCATEGORÍA (verificadas: HTTP 200 + contenido revisado)
# ============================================================================
# "fotos": pool general. "por_tipo": la portada se elige según el tipo concreto del
# producto (p. ej. una licuadora lleva foto de licuadora) y las fotos extra salen de
# "ambiente" (fotos de cocina/uso) para no mostrar otro electrodoméstico distinto.
FOTOS = {
    "Laptops": {"fotos": [
        "photo-1496181133206-80ce9b88a853", "photo-1525547719571-a2d4ac8945e2",
        "photo-1588872657578-7efd1f1555ed", "photo-1593642702821-c8da6771f0c6",
        "photo-1541807084-5c52b6b3adef", "photo-1611186871348-b1ce696e52c9",
        "photo-1531297484001-80022131f5a1", "photo-1602080858428-57174f9431cf",
        "photo-1603302576837-37561b2e2302", "photo-1640955014216-75201056c829",
        "photo-1611078489935-0cb964de46d6", "photo-1517336714731-489689fd1ca8"]},
    "Monitores": {"fotos": [
        "photo-1527443224154-c4a3942d3acf", "photo-1585792180666-f7347c490ee2",
        "photo-1547658718-1cdaa0852790", "photo-1616763355548-1b606f439f86",
        "photo-1593640408182-31c70c8268f5", "photo-1534423861386-85a16f5d13fd",
        "photo-1593305841991-05c297ba4575", "photo-1614179924047-e1ab49a0a0cf"]},
    "Playeras": {"fotos": [
        "photo-1521572163474-6864f9cf17ab", "photo-1583743814966-8936f5b7be1a",
        "photo-1576566588028-4147f3842f27", "photo-1562157873-818bc0726f68",
        "photo-1618354691373-d851c5c3a990", "photo-1622445275463-afa2ab738c34",
        "photo-1571455786673-9d9d6c194f90", "photo-1581655353564-df123a1eb820",
        "photo-1564584217132-2271feaeb3c5"]},
    "Celulares": {"fotos": [
        "photo-1511707171634-5f897ff02aa9", "photo-1592899677977-9c10ca588bbd",
        "photo-1598327105666-5b89351aff97", "photo-1510557880182-3d4d3cba35a5",
        "photo-1580910051074-3eb694886505", "photo-1565849904461-04a58ad377e0",
        "photo-1610945265064-0e34e5519bbf", "photo-1601784551446-20c9e07cdbdb",
        "photo-1512941937669-90a1b58e7e9c"]},
    "Audífonos": {
        "por_tipo": {
            "Over-ear": ["photo-1505740420928-5e560c06d30e", "photo-1546435770-a3e426bf472b",
                         "photo-1484704849700-f032a568e944", "photo-1618366712010-f4ae9c647dcb"],
            "On-ear": ["photo-1583394838336-acd977736f90", "photo-1572536147248-ac59a8abfa4b"],
            "True Wireless": ["photo-1590658268037-6bf12165a8df", "photo-1606220588913-b3aacb4d2f46"],
        },
        "ambiente": []},
    "Teclados": {"fotos": [
        "photo-1587829741301-dc798b83add3", "photo-1618384887929-16ec33fab9ef",
        "photo-1595225476474-87563907a212", "photo-1541140532154-b024d705b90a",
        "photo-1511467687858-23d96c32e4ae", "photo-1601445638532-3c6f6c3aa1d6"]},
    "Mouse": {"fotos": [
        "photo-1527864550417-7fd91fc51a46", "photo-1615663245857-ac93bb7c39e7",
        "photo-1613141411244-0e4ac259d217", "photo-1605773527852-c546a8584ea3",
        "photo-1629429408209-1f912961dbd8"]},
    "Tablets": {"fotos": [
        "photo-1544244015-0df4b3ffc6b0", "photo-1561154464-82e9adf32764",
        "photo-1585790050230-5dd28404ccb9", "photo-1589739900243-4b52cd9b104e",
        "photo-1542751110-97427bbecf20", "photo-1623126908029-58cb08a2b272"]},
    "Smartwatches": {"fotos": [
        "photo-1523275335684-37898b6baf30", "photo-1546868871-7041f2a55e12",
        "photo-1579586337278-3befd40fd17a", "photo-1508685096489-7aacd43bd3b1",
        "photo-1434493789847-2f02dc6ca35d", "photo-1617043786394-f977fa12eddf",
        "photo-1551816230-ef5deaed4a26"]},
    "Jeans": {"fotos": [
        "photo-1542272604-787c3835535d", "photo-1541099649105-f69ad21f3246",
        "photo-1604176354204-9268737828e4", "photo-1475178626620-a4d074967452",
        "photo-1582552938357-32b906df40cb", "photo-1565084888279-aca607ecce0c"]},
    "Sudaderas": {"fotos": [
        "photo-1556821840-3a63f95609a7", "photo-1620799140408-edc6dcb6d633",
        "photo-1578587018452-892bacefd3f2", "photo-1509942774463-acf339cf87d5",
        "photo-1542406775-ade58c52d2e4"]},
    "Tenis": {"fotos": [
        "photo-1542291026-7eec264c27ff", "photo-1600185365483-26d7a4cc7519",
        "photo-1606107557195-0e29a4b5b4aa", "photo-1595950653106-6c9ebd614d3a",
        "photo-1549298916-b41d501d3772", "photo-1460353581641-37baddab0fa2",
        "photo-1491553895911-0055eca6402d", "photo-1608231387042-66d1773070a5"]},
    "Vestidos": {"fotos": [
        "photo-1595777457583-95e059d581b8", "photo-1572804013309-59a88b7e92f1",
        "photo-1515372039744-b8f02a3ae446", "photo-1496747611176-843222e1e57c",
        "photo-1539008835657-9e8e9680c956", "photo-1585487000160-6ebcfceb0d03"]},
    "Gorras": {"fotos": [
        "photo-1588850561407-ed78c282e89b", "photo-1521369909029-2afed882baee",
        "photo-1575428652377-a2d80e2277fc", "photo-1556306535-0f09a537f0a3",
        "photo-1534215754734-18e55d13e346"]},
    "Electrodomésticos de Cocina": {
        "por_tipo": {
            "Cafetera de goteo": ["photo-1570222094114-d054a817e56b"],
            "Batidora de pedestal": ["photo-1578643463396-0997cb5328c1"],
            "Licuadora": ["photo-1585515320310-259814833e62"],
            "Molino de café": ["photo-1611854779393-1b2da9d400fe"],
            "Horno tostador": ["photo-1574269909862-7e1d70bb8078"],
        },
        "ambiente": ["photo-1586208958839-06c17cacdf08", "photo-1565538810643-b5bdb714032a",
                     "photo-1556911220-bff31c812dba"]},
    "Utensilios de Cocina": {
        "por_tipo": {
            "Olla": ["photo-1590794056226-79ef3a8147e1", "photo-1583778176476-4a8b02a64c01"],
            "Cacerola": ["photo-1590794056226-79ef3a8147e1", "photo-1583778176476-4a8b02a64c01"],
            "Sartén": ["photo-1584269600464-37b1b58a9fe7", "photo-1604908176997-125f25cc6f3d"],
            "Juego de cuchillos": ["photo-1593618998160-e34014e67546"],
        },
        "ambiente": ["photo-1556909114-f6e7ad7d3136", "photo-1556910103-1c02745aae4d"]},
    "Bicicletas": {"fotos": [
        "photo-1485965120184-e220f721d03e", "photo-1532298229144-0ec0c57515c7",
        "photo-1576435728678-68d0fbf94e91", "photo-1571068316344-75bc76f77890",
        "photo-1507035895480-2b3156c31fc8"]},
    "Pesas y Mancuernas": {"fotos": [
        "photo-1638536532686-d610adfc8e5c", "photo-1586401100295-7a8096fd231a",
        "photo-1583454110551-21f2fa2afe61", "photo-1534438327276-14e5300c3a48",
        "photo-1517836357463-d25dfeac3438"]},
    "Tapetes de Yoga": {"fotos": [
        "photo-1601925260368-ae2f83cf8b7f", "photo-1592432678016-e910b452f9a2",
        "photo-1599447421416-3414500d18a5", "photo-1544367567-0f2fcb009e0b"]},
    "Mochilas": {"fotos": [
        "photo-1553062407-98eeb64c6a62", "photo-1622560480605-d83c853bc5c3",
        "photo-1581605405669-fcdf81165afa", "photo-1577733966973-d680bffd2e80"]},
    "Perfumes": {"fotos": [
        "photo-1541643600914-78b084683601", "photo-1523293182086-7651a899d37f",
        "photo-1592945403244-b3fbafd7f539", "photo-1587017539504-67cfbddac569",
        "photo-1594035910387-fea47794261f"]},
    "Cuidado de la Piel": {"fotos": [
        "photo-1556228578-8c89e6adf883", "photo-1598440947619-2c35fc9aa908",
        "photo-1571781926291-c477ebfd024b", "photo-1620916566398-39f1143ab7be"]},
}

# ============================================================================
# 3. TIENDAS (usuarios con rol 'vendedor') Y SU GIRO
# ============================================================================
# Cada tienda solo vende en las subcategorías de su giro. Las 2 tiendas semilla del DDL
# se referencian por email (nunca por ID) y también reciben productos.
# "peso" controla qué tan grande es su catálogo frente a otras tiendas del mismo giro.
TIENDAS_EXISTENTES = [
    ("TechStore Oficial", "ventas@techstore.com", ["Laptops", "Monitores", "Teclados", "Mouse"], 4),
    ("Moda Urbana GT", "contacto@modaurbana.com", ["Playeras", "Sudaderas", "Gorras"], 2),
]

TIENDAS_NUEVAS = [
    # --- Tecnología ---
    ("Compu Centro Zona 4", "ventas@compucentrozona4.com.gt", ["Laptops", "Monitores", "Teclados", "Mouse"]),
    ("Megatech Guatemala", "tienda@megatechgt.com", ["Laptops", "Monitores", "Tablets"]),
    ("Cel Express Guatemala", "ventas@celexpress.com.gt", ["Celulares", "Smartwatches", "Audífonos"]),
    ("Gamer Zone Xela", "contacto@gamerzonexela.com", ["Monitores", "Teclados", "Mouse", "Audífonos", "Laptops"]),
    ("iMundo Oakland", "hola@imundooakland.com.gt", ["Laptops", "Tablets", "Smartwatches", "Celulares", "Audífonos"]),
    ("Digital Plaza Miraflores", "ventas@digitalplazagt.com", ["Celulares", "Tablets", "Audífonos"]),
    ("SonidoPro GT", "info@sonidoprogt.com", ["Audífonos"]),
    ("Periféricos Chapines", "pedidos@perifericoschapines.com", ["Teclados", "Mouse"]),
    ("Tecno Antigua", "ventas@tecnoantigua.com.gt", ["Celulares", "Smartwatches", "Tablets"]),
    ("Byte Store Mixco", "contacto@bytestoremixco.com", ["Laptops", "Monitores", "Mouse", "Teclados"]),
    ("Smart Life Guatemala", "ventas@smartlifegt.com", ["Smartwatches", "Audífonos", "Celulares"]),
    ("Kompuservicios Quetzal", "ventas@kompuquetzal.com.gt", ["Laptops", "Monitores"]),
    # --- Moda ---
    ("Denim Chapín", "ventas@denimchapin.com", ["Jeans", "Playeras"]),
    ("Sneaker Hub Guatemala", "hola@sneakerhubgt.com", ["Tenis", "Gorras"]),
    ("Boutique Doña Lupita", "boutique@donalupita.com.gt", ["Vestidos"]),
    ("Urban Xela Streetwear", "contacto@urbanxela.com", ["Sudaderas", "Playeras", "Gorras"]),
    ("Estilo Antigüeño", "ventas@estiloantigueno.com", ["Vestidos", "Playeras"]),
    ("Pasos Firmes Calzado", "ventas@pasosfirmes.com.gt", ["Tenis"]),
    ("La Gorra Chapina", "pedidos@lagorrachapina.com", ["Gorras"]),
    ("Moda Maya Contemporánea", "tienda@modamayacontemporanea.com", ["Vestidos", "Playeras"]),
    ("Street Kings GT", "ventas@streetkingsgt.com", ["Sudaderas", "Tenis", "Gorras", "Playeras"]),
    ("Jeans & Co. Pradera", "ventas@jeansypradera.com.gt", ["Jeans"]),
    ("Casual Market Cayalá", "hola@casualmarketcayala.com", ["Playeras", "Jeans", "Sudaderas"]),
    # --- Hogar y Cocina ---
    ("Cocina Feliz GT", "ventas@cocinafelizgt.com", ["Electrodomésticos de Cocina", "Utensilios de Cocina"]),
    ("Hogar Práctico Quetzaltenango", "contacto@hogarpracticoxela.com", ["Electrodomésticos de Cocina", "Utensilios de Cocina"]),
    ("Casa Barista Guatemala", "tienda@casabaristagt.com", ["Electrodomésticos de Cocina"]),
    ("El Rincón del Chef", "ventas@rincondelchef.com.gt", ["Utensilios de Cocina"]),
    ("Electrohogar Petapa", "ventas@electrohogarpetapa.com", ["Electrodomésticos de Cocina"]),
    # --- Deportes y Fitness ---
    ("Ciclo Guate", "ventas@cicloguate.com", ["Bicicletas", "Mochilas"]),
    ("Pedal Libre Antigua", "hola@pedallibreantigua.com", ["Bicicletas"]),
    ("Fitness Store GT", "ventas@fitnessstoregt.com", ["Pesas y Mancuernas", "Tapetes de Yoga"]),
    ("Yoga Atitlán", "namaste@yogaatitlan.com", ["Tapetes de Yoga"]),
    ("Aventura Outdoor Guatemala", "ventas@aventuraoutdoorgt.com", ["Mochilas", "Bicicletas"]),
    ("Power Gym Supply", "pedidos@powergymsupply.com.gt", ["Pesas y Mancuernas"]),
    ("Mochilas Volcán", "ventas@mochilasvolcan.com", ["Mochilas"]),
    # --- Belleza ---
    ("Aromas de Guatemala", "ventas@aromasdeguatemala.com", ["Perfumes"]),
    ("Dermacuidado GT", "contacto@dermacuidadogt.com", ["Cuidado de la Piel"]),
    ("Belleza Natural Cobán", "ventas@bellezanaturalcoban.com", ["Cuidado de la Piel", "Perfumes"]),
    ("Perfumería Esencia Zona 14", "ventas@perfumeriaesencia.com.gt", ["Perfumes"]),
    ("Glow Beauty Store", "hola@glowbeautygt.com", ["Cuidado de la Piel", "Perfumes"]),
]

# Cuántos productos nuevos lleva cada subcategoría (suma = 1000).
CANTIDAD_POR_SUBCATEGORIA = OrderedDict([
    ("Laptops", 60), ("Monitores", 50), ("Playeras", 60), ("Celulares", 60),
    ("Audífonos", 50), ("Teclados", 40), ("Mouse", 40), ("Tablets", 40), ("Smartwatches", 40),
    ("Jeans", 50), ("Sudaderas", 45), ("Tenis", 60), ("Vestidos", 45), ("Gorras", 35),
    ("Electrodomésticos de Cocina", 50), ("Utensilios de Cocina", 45),
    ("Bicicletas", 35), ("Pesas y Mancuernas", 35), ("Tapetes de Yoga", 30), ("Mochilas", 40),
    ("Perfumes", 45), ("Cuidado de la Piel", 45),
])

PREFIJO_SKU = {
    "Laptops": "LAP", "Monitores": "MON", "Playeras": "TSH", "Celulares": "CEL",
    "Audífonos": "AUD", "Teclados": "TEC", "Mouse": "MOU", "Tablets": "TAB",
    "Smartwatches": "SMW", "Jeans": "JNS", "Sudaderas": "SUD", "Tenis": "TEN",
    "Vestidos": "VES", "Gorras": "GOR", "Electrodomésticos de Cocina": "ELC",
    "Utensilios de Cocina": "UTC", "Bicicletas": "BIC", "Pesas y Mancuernas": "PES",
    "Tapetes de Yoga": "YOG", "Mochilas": "MOC", "Perfumes": "PER", "Cuidado de la Piel": "PIE",
}

# ============================================================================
# 4. ATRIBUTOS PERSONALIZADOS (fuera del esquema de la categoría)
# ============================================================================
# Mismo mecanismo que ya existe en el catálogo: claves adicionales dentro de "atributos"
# con valor de texto (como "edicion_limitada": "Si" que el admin agregó a TSH-CREW-BLU
# desde FormularioProducto.vue). El formulario de edición las muestra como "atributos
# personalizados" porque no están en el esquema de la categoría.
EXTRAS_GENERALES = [
    ("edicion_limitada", ["Si"]),
    ("garantia_extendida", ["12 meses adicionales", "24 meses adicionales"]),
    ("envio_gratis", ["Si"]),
]
EXTRAS_POR_SUBCATEGORIA = {
    "Laptops": [("sistema_operativo", ["Windows 11 Home", "Windows 11 Pro", "macOS", "FreeDOS"]),
                ("teclado_retroiluminado", ["Si", "RGB por zonas"]),
                ("incluye_mochila", ["Si"])],
    "Monitores": [("incluye_soporte_vesa", ["Si"]), ("bocinas_integradas", ["Si", "No"]),
                  ("certificacion_hdr", ["HDR10", "DisplayHDR 400", "DisplayHDR 600"])],
    "Playeras": [("estampado_personalizado", ["Nombre o frase (Q35)", "Logo de empresa (Q60)"]),
                 ("bordado_personalizado", ["Iniciales bordadas (Q40)"])],
    "Celulares": [("incluye_cargador", ["Si", "No"]), ("dual_sim", ["Si"]),
                  ("grabado_personalizado", ["Grabado láser en carcasa (Q75)"])],
    "Audífonos": [("estuche_rigido", ["Si"]), ("microfono_desmontable", ["Si"]),
                  ("grabado_personalizado", ["Grabado en estuche (Q50)"])],
    "Teclados": [("keycaps_personalizados", ["Set PBT temático (Q150)", "Tecla con nombre (Q25)"]),
                 ("hot_swap", ["Si"])],
    "Mouse": [("pies_ptfe_repuesto", ["Si"]), ("software_macros", ["Si"])],
    "Tablets": [("incluye_lapiz", ["Si"]), ("incluye_funda_teclado", ["Si"]),
                ("grabado_personalizado", ["Grabado láser en la parte trasera (Q90)"])],
    "Smartwatches": [("correa_adicional", ["Silicón", "Nylon", "Cuero"]),
                     ("grabado_personalizado", ["Grabado en la caja (Q80)"])],
    "Jeans": [("ajuste_ruedo", ["Ruedo a la medida (Q30)"]), ("bordado_personalizado", ["Iniciales en bolsa trasera (Q45)"])],
    "Sudaderas": [("bordado_personalizado", ["Nombre en la manga (Q50)", "Logo en el pecho (Q70)"]),
                  ("forro_interno", ["Peluche", "Sherpa"])],
    "Tenis": [("plantilla_ortopedica", ["Si"]), ("agujetas_adicionales", ["Si"]),
              ("diseno_personalizado", ["Pintura a mano (Q250)"])],
    "Vestidos": [("ajuste_a_la_medida", ["Ajuste de largo y talle (Q75)"]),
                 ("bordado_tipico", ["Bordado a mano de San Antonio Aguas Calientes"])],
    "Gorras": [("bordado_personalizado", ["Nombre o iniciales (Q35)", "Logo de equipo (Q60)"]),
               ("proteccion_uv", ["UPF 50+"])],
    "Electrodomésticos de Cocina": [("voltaje", ["110 V"]), ("accesorios_incluidos", ["Recetario y jarra adicional"]),
                                    ("funcion_programable", ["Si"])],
    "Utensilios de Cocina": [("apto_lavavajillas", ["Si", "No"]), ("grabado_personalizado", ["Nombre en el mango (Q60)"]),
                             ("incluye_tapa", ["Si"])],
    "Bicicletas": [("armado_y_ajuste", ["Incluido en tienda"]), ("incluye_candado", ["Si"]),
                   ("frenos", ["Disco hidráulico", "Disco mecánico", "V-Brake"])],
    "Pesas y Mancuernas": [("agarre", ["Moleteado", "Ergonómico recubierto"]), ("incluye_rack", ["Si"])],
    "Tapetes de Yoga": [("incluye_correa", ["Si"]), ("grabado_personalizado", ["Nombre grabado (Q40)"])],
    "Mochilas": [("puerto_usb", ["Si"]), ("bordado_personalizado", ["Nombre bordado (Q40)"]),
                 ("antirrobo", ["Si"])],
    "Perfumes": [("presentacion_regalo", ["Estuche con loción corporal", "Set con miniatura"]),
                 ("grabado_personalizado", ["Grabado en frasco (Q65)"])],
    "Cuidado de la Piel": [("libre_de_crueldad", ["Si"]), ("vegano", ["Si"]),
                           ("dermatologicamente_probado", ["Si"])],
}

# ============================================================================
# 5. GENERADORES POR SUBCATEGORÍA
# ============================================================================
# Cada generador devuelve (nombre, descripcion, precio, atributos, tipo_foto, rango_stock).
# Los atributos llevan EXACTAMENTE las claves del esquema de la subcategoría, con el tipo
# correcto (int/float para "numero", str para "texto").


def _precio(valor):
    """Redondea a precios 'de tienda': ...9.00 para montos grandes, ...5/...9 para pequeños."""
    if valor >= 1000:
        return float(int(round(valor / 10.0)) * 10 - 1)
    if valor >= 100:
        return float(int(round(valor / 5.0)) * 5 - 1)
    return float(int(round(valor)))


def _ssd(gb):
    return f"{gb // 1000}TB" if gb >= 1000 else f"{gb}GB"


def gen_laptop(r):
    modelos = [
        # (modelo, [procesadores], [gpus], [pantallas], [hz], precio_base, uso)
        ("Lenovo IdeaPad Slim 3", ["Intel Core i5-1335U", "AMD Ryzen 5 7520U", "Intel Core i7-1355U"], ["Gráfica integrada"], [14.0, 15.6], [60], 4200, "oficina y estudio"),
        ("HP Pavilion 15", ["Intel Core i5-1335U", "Intel Core i7-1355U"], ["Gráfica integrada", "NVIDIA GeForce MX550"], [15.6], [60], 5200, "productividad diaria"),
        ("Dell Inspiron 15 3530", ["Intel Core i5-1334U", "Intel Core i7-1355U"], ["Gráfica integrada"], [15.6], [60, 120], 5400, "oficina y teletrabajo"),
        ("ASUS Vivobook 15", ["Intel Core i3-1215U", "Intel Core i5-1235U", "AMD Ryzen 7 7730U"], ["Gráfica integrada"], [15.6], [60], 3600, "estudiantes"),
        ("Acer Nitro V 15", ["Intel Core i5-13420H", "Intel Core i7-13620H"], ["NVIDIA RTX 3050", "NVIDIA RTX 4050"], [15.6], [144], 7400, "gaming de entrada"),
        ("ASUS TUF Gaming A15", ["AMD Ryzen 7 7735HS", "AMD Ryzen 7 7840HS"], ["NVIDIA RTX 4050", "NVIDIA RTX 4060"], [15.6], [144], 8900, "gaming"),
        ("Lenovo LOQ 15", ["Intel Core i5-12450HX", "Intel Core i7-13650HX"], ["NVIDIA RTX 3050", "NVIDIA RTX 4050", "NVIDIA RTX 4060"], [15.6], [144], 7900, "gaming"),
        ("HP Victus 16", ["Intel Core i5-13500H", "AMD Ryzen 7 7840HS"], ["NVIDIA RTX 4050", "NVIDIA RTX 4060"], [16.1], [144, 165], 8700, "gaming y creación de contenido"),
        ("MSI Katana 15", ["Intel Core i7-13620H", "Intel Core i9-13900H"], ["NVIDIA RTX 4060", "NVIDIA RTX 4070"], [15.6], [144, 165], 10900, "gaming exigente"),
        ("Dell XPS 13", ["Intel Core Ultra 7 155H", "Intel Core i7-1360P"], ["Gráfica integrada"], [13.4], [60, 120], 13900, "profesionales que viajan"),
        ("Apple MacBook Air 15", ["Apple M3 8-Core", "Apple M2 8-Core"], ["Gráfica integrada"], [15.3], [60], 12900, "creativos y estudiantes"),
        ("Apple MacBook Pro 14", ["Apple M3 Pro 11-Core", "Apple M3 Max 14-Core"], ["Gráfica integrada"], [14.2], [120], 19900, "edición de video y desarrollo"),
        ("Lenovo ThinkPad E14", ["Intel Core i5-1335U", "AMD Ryzen 7 7730U"], ["Gráfica integrada"], [14.0], [60], 6900, "empresas"),
        ("HP EliteBook 840 G10", ["Intel Core i5-1345U", "Intel Core i7-1365U"], ["Gráfica integrada"], [14.0], [60], 10900, "entornos corporativos"),
        ("ASUS ROG Zephyrus G14", ["AMD Ryzen 9 8945HS", "AMD Ryzen 9 7940HS"], ["NVIDIA RTX 4060", "NVIDIA RTX 4070"], [14.0], [120, 165], 15900, "gaming portátil premium"),
        ("Acer Swift Go 14", ["Intel Core Ultra 5 125H", "Intel Core Ultra 7 155H"], ["Gráfica integrada"], [14.0], [90], 7600, "movilidad y batería de larga duración"),
        ("Samsung Galaxy Book3", ["Intel Core i5-1335U", "Intel Core i7-1355U"], ["Gráfica integrada"], [15.6], [60], 6400, "integración con dispositivos Galaxy"),
        ("Gigabyte G5", ["Intel Core i5-12500H"], ["NVIDIA RTX 4050", "NVIDIA RTX 4060"], [15.6], [144], 7800, "gaming"),
    ]
    modelo, cpus, gpus, pantallas, hzs, base, uso = r.choice(modelos)
    cpu = r.choice(cpus)
    gpu = r.choice(gpus)
    ram = r.choice([8, 16, 16, 32]) if base < 12000 else r.choice([16, 18, 24, 36]) if "Apple" in modelo else r.choice([16, 32])
    ssd = r.choice([256, 512, 512, 1000]) if base < 7000 else r.choice([512, 1000, 1000, 2000])
    pantalla = r.choice(pantallas)
    hz = r.choice(hzs)
    precio = base + (ram - 8) * 90 + (ssd - 256) * 1.6 + (900 if "4060" in gpu else 1900 if "4070" in gpu else 0)
    precio *= r.uniform(0.95, 1.07)
    cpu_corto = cpu.replace("Intel ", "").replace("AMD ", "").replace("Apple ", "").split("-")[0]
    nombre = f"Laptop {modelo} {cpu_corto} {ram}GB {_ssd(ssd)} SSD"
    if gpu != "Gráfica integrada":
        nombre += f" {gpu.replace('NVIDIA ', '')}"
    desc = (f"{modelo} con procesador {cpu}, {ram}GB de RAM y SSD de {_ssd(ssd)}. "
            f"Pantalla de {pantalla} pulgadas a {hz}Hz y {gpu.lower() if gpu == 'Gráfica integrada' else 'tarjeta ' + gpu}. "
            f"Ideal para {uso}.")
    atributos = {
        "procesador": cpu, "memoria_ram_gb": ram, "almacenamiento_ssd_gb": ssd,
        "tarjeta_grafica": gpu, "tasa_refresco_hz": hz, "tamano_pantalla_pulgadas": pantalla,
    }
    return nombre, desc, _precio(precio), atributos, None, (3, 25)


def gen_monitor(r):
    configs = [
        # (tamaño, panel, resolución, hz, ms, precio_base, marca)
        (21.5, "VA", "1920x1080 Full HD", 75, 5, 750), (23.8, "IPS", "1920x1080 Full HD", 75, 5, 950),
        (23.8, "IPS", "1920x1080 Full HD", 165, 1, 1450), (24.5, "TN", "1920x1080 Full HD", 240, 0.5, 1990),
        (27.0, "IPS", "1920x1080 Full HD", 144, 1, 1750), (27.0, "IPS", "2560x1440 QHD", 165, 1, 2600),
        (27.0, "VA", "2560x1440 QHD", 180, 1, 2400), (27.0, "IPS", "3840x2160 4K UHD", 60, 5, 3300),
        (27.0, "OLED", "2560x1440 QHD", 240, 0.03, 6900), (31.5, "VA", "2560x1440 QHD", 165, 1, 3100),
        (31.5, "IPS", "3840x2160 4K UHD", 144, 1, 5900), (34.0, "VA", "3440x1440 WQHD", 165, 1, 3900),
        (34.0, "OLED", "3440x1440 WQHD", 175, 0.03, 8900), (49.0, "VA", "5120x1440 DQHD", 240, 1, 11500),
    ]
    marcas = ["Samsung Odyssey", "LG UltraGear", "LG UltraFine", "Dell", "ASUS TUF Gaming", "AOC", "MSI", "BenQ", "ViewSonic", "Gigabyte"]
    tam, panel, res, hz, ms, base, = r.choice(configs)
    marca = r.choice(marcas)
    curvo = panel == "VA" and tam >= 27 and r.random() < 0.6
    tam_txt = f"{tam:g}"
    nombre = f"Monitor {marca} {tam_txt}\" {panel} {res.split(' ', 1)[1]} {hz}Hz" + (" Curvo" if curvo else "")
    desc = (f"Monitor {marca} de {tam_txt} pulgadas con panel {panel}{' curvo' if curvo else ''}, resolución {res} "
            f"y {hz}Hz con tiempo de respuesta de {ms:g}ms. "
            + ("Pensado para gaming competitivo." if hz >= 144 else "Ideal para productividad y oficina."))
    atributos = {"tamano_pantalla_pulgadas": tam, "tipo_panel": panel, "resolucion": res,
                 "tasa_refresco_hz": hz, "tiempo_respuesta_ms": ms}
    return nombre, desc, _precio(base * r.uniform(0.92, 1.1)), atributos, None, (4, 40)


TALLAS_ROPA = ["XS", "S", "M", "L", "XL", "XXL"]
COLORES_ROPA = ["Negro", "Blanco", "Gris Jaspe", "Azul Marino", "Beige", "Verde Olivo", "Rojo", "Café",
                "Celeste", "Mostaza", "Vino", "Lila"]


def gen_playera(r):
    estilos = [
        ("Playera Básica Cuello Redondo", "Regular Fit", 95), ("Playera Oversize", "Oversize", 165),
        ("Playera Slim Fit", "Slim Fit", 120), ("Playera Polo Piqué", "Clásico", 195),
        ("Playera Cuello V", "Regular Fit", 110), ("Playera Estampada Volcanes de Guatemala", "Regular Fit", 175),
        ("Playera Deportiva Dry-Fit", "Atlético", 145), ("Playera Manga Larga Henley", "Regular Fit", 185),
        ("Playera Estampada Quetzal", "Oversize", 180), ("Playera Tie-Dye", "Oversize", 170),
        ("Playera Estampada Lago de Atitlán", "Regular Fit", 175), ("Playera Boxy Fit Heavyweight", "Boxy Fit", 210),
    ]
    materiales = ["100% Algodón", "100% Algodón Peinado", "95% Algodón 5% Elastano", "100% Poliéster",
                  "50% Algodón 50% Poliéster", "100% Algodón Orgánico"]
    lavados = ["Lavar con agua fría, no usar secadora", "Lavar a mano, secar a la sombra",
               "Lavar al revés con agua fría, no planchar el estampado", "Lavado en máquina ciclo delicado"]
    estilo, corte, base = r.choice(estilos)
    material = "100% Poliéster" if "Dry-Fit" in estilo else r.choice(materiales)
    color = r.choice(COLORES_ROPA)
    talla = r.choice(TALLAS_ROPA)
    nombre = f"{estilo} {color} Talla {talla}"
    desc = f"{estilo} en color {color.lower()}, {material.lower()}, corte {corte.lower()}. Talla {talla}."
    atributos = {"talla": talla, "color": color, "material": material, "corte": corte,
                 "instrucciones_lavado": r.choice(lavados)}
    return nombre, desc, _precio(base * r.uniform(0.9, 1.15)), atributos, None, (15, 120)


def gen_celular(r):
    modelos = [
        # (modelo, marca, [almacenamientos], ram, pantalla, cámara, batería, 5g, precio)
        ("Galaxy A15", "Samsung", [128, 256], 4, 6.5, 50, 5000, "4G LTE", 1600),
        ("Galaxy A35 5G", "Samsung", [128, 256], 8, 6.6, 50, 5000, "5G", 2900),
        ("Galaxy A55 5G", "Samsung", [128, 256], 8, 6.6, 50, 5000, "5G", 3600),
        ("Galaxy S24", "Samsung", [256, 512], 8, 6.2, 50, 4000, "5G", 7900),
        ("Galaxy S24 Ultra", "Samsung", [256, 512, 1024], 12, 6.8, 200, 5000, "5G", 10900),
        ("iPhone 13", "Apple", [128, 256], 4, 6.1, 12, 3240, "5G", 5400),
        ("iPhone 15", "Apple", [128, 256, 512], 6, 6.1, 48, 3349, "5G", 7600),
        ("iPhone 15 Pro Max", "Apple", [256, 512, 1024], 8, 6.7, 48, 4441, "5G", 11500),
        ("Redmi Note 13", "Xiaomi", [128, 256], 8, 6.67, 108, 5000, "4G LTE", 1800),
        ("Redmi Note 13 Pro+ 5G", "Xiaomi", [256, 512], 12, 6.67, 200, 5000, "5G", 3400),
        ("Xiaomi 14T", "Xiaomi", [256, 512], 12, 6.67, 50, 5000, "5G", 5200),
        ("Moto G54 5G", "Motorola", [128, 256], 8, 6.5, 50, 5000, "5G", 1700),
        ("Edge 50 Fusion", "Motorola", [256], 8, 6.7, 50, 5000, "5G", 2900),
        ("Honor X8b", "Honor", [256], 8, 6.7, 108, 4500, "4G LTE", 2100),
        ("Honor Magic6 Lite", "Honor", [256], 8, 6.78, 108, 5300, "5G", 2800),
        ("Pixel 8a", "Google", [128, 256], 8, 6.1, 64, 4492, "5G", 4400),
        ("Nord CE4", "OnePlus", [128, 256], 8, 6.7, 50, 5500, "5G", 2800),
        ("Tecno Spark 20 Pro", "Tecno", [256], 8, 6.78, 108, 5000, "4G LTE", 1500),
    ]
    colores = ["Negro", "Azul", "Verde Menta", "Lila", "Blanco", "Grafito", "Titanio Natural", "Plata", "Amarillo"]
    modelo, marca, almacenamientos, ram, pantalla, cam, bat, red, base = r.choice(modelos)
    alm = r.choice(almacenamientos)
    color = r.choice(colores)
    precio = base * (1 + 0.18 * almacenamientos.index(alm)) * r.uniform(0.95, 1.06)
    alm_txt = "1TB" if alm == 1024 else f"{alm}GB"
    nombre = f"{marca} {modelo} {alm_txt} {color}" if marca not in modelo else f"{modelo} {alm_txt} {color}"
    desc = (f"Smartphone {marca} {modelo} con pantalla de {pantalla} pulgadas, {ram}GB de RAM y {alm_txt} de almacenamiento. "
            f"Cámara principal de {cam}MP, batería de {bat}mAh y conectividad {red}. Liberado para cualquier operador en Guatemala.")
    atributos = {"marca": marca, "almacenamiento_gb": alm, "memoria_ram_gb": ram,
                 "tamano_pantalla_pulgadas": pantalla, "camara_principal_mp": cam, "bateria_mah": bat,
                 "red": red, "color": color}
    return nombre, desc, _precio(precio), atributos, None, (5, 45)


def gen_audifono(r):
    modelos = [
        ("Sony WH-1000XM5", "Sony", "Over-ear", "Bluetooth", "Sí", 30, 2900),
        ("Sony WH-CH520", "Sony", "On-ear", "Bluetooth", "No", 50, 450),
        ("Sony WF-1000XM5", "Sony", "True Wireless", "Bluetooth", "Sí", 8, 2400),
        ("JBL Tune 520BT", "JBL", "On-ear", "Bluetooth", "No", 57, 399),
        ("JBL Tune 770NC", "JBL", "Over-ear", "Bluetooth", "Sí", 44, 890),
        ("JBL Live Pro 2", "JBL", "True Wireless", "Bluetooth", "Sí", 10, 1150),
        ("Bose QuietComfort Ultra", "Bose", "Over-ear", "Bluetooth", "Sí", 24, 3400),
        ("Bose QuietComfort Earbuds II", "Bose", "True Wireless", "Bluetooth", "Sí", 6, 2300),
        ("Apple AirPods Pro 2", "Apple", "True Wireless", "Bluetooth", "Sí", 6, 2100),
        ("Apple AirPods Max", "Apple", "Over-ear", "Bluetooth", "Sí", 20, 4600),
        ("Samsung Galaxy Buds2 Pro", "Samsung", "True Wireless", "Bluetooth", "Sí", 5, 1400),
        ("HyperX Cloud II", "HyperX", "Over-ear", "USB", "No", 0, 690),
        ("HyperX Cloud Alpha Wireless", "HyperX", "Over-ear", "Inalámbrico 2.4GHz", "No", 300, 1490),
        ("Logitech G435", "Logitech", "Over-ear", "Inalámbrico 2.4GHz", "No", 18, 690),
        ("Razer BlackShark V2 X", "Razer", "Over-ear", "Cable 3.5mm", "No", 0, 490),
        ("Audio-Technica ATH-M50x", "Audio-Technica", "Over-ear", "Cable 3.5mm", "No", 0, 1390),
        ("Soundcore Life Q30", "Anker", "Over-ear", "Bluetooth", "Sí", 40, 690),
        ("Soundcore Liberty 4 NC", "Anker", "True Wireless", "Bluetooth", "Sí", 10, 790),
        ("Xiaomi Redmi Buds 5", "Xiaomi", "True Wireless", "Bluetooth", "Sí", 10, 320),
        ("Beats Solo 4", "Beats", "On-ear", "Bluetooth", "No", 50, 1600),
    ]
    modelo, marca, tipo, conexion, anc, horas, base = r.choice(modelos)
    color = r.choice(["Negro", "Blanco", "Azul", "Plata", "Beige", "Rosa"])
    nombre = f"Audífonos {modelo} {color}"
    detalle_bat = f"hasta {horas} horas de batería" if horas else "sin batería (conexión por cable)"
    desc = (f"Audífonos {tipo.lower()} {modelo} con conexión {conexion}"
            f"{' y cancelación activa de ruido' if anc == 'Sí' else ''}, {detalle_bat}. Color {color.lower()}.")
    atributos = {"marca": marca, "tipo": tipo, "conexion": conexion, "cancelacion_ruido": anc,
                 "autonomia_horas": horas, "color": color}
    return nombre, desc, _precio(base * r.uniform(0.93, 1.08)), atributos, tipo, (5, 60)


def gen_teclado(r):
    modelos = [
        ("Logitech G Pro X TKL", "Logitech", 1790), ("Logitech MX Keys S", "Logitech", 1090),
        ("Logitech K380", "Logitech", 320), ("Redragon Kumara K552", "Redragon", 340),
        ("Redragon Fizz K617", "Redragon", 290), ("Keychron K2 V2", "Keychron", 890),
        ("Keychron Q1 Pro", "Keychron", 1590), ("HyperX Alloy Origins Core", "HyperX", 790),
        ("Razer BlackWidow V4", "Razer", 1390), ("Corsair K70 RGB Pro", "Corsair", 1290),
        ("Royal Kludge RK61", "Royal Kludge", 390), ("Microsoft Ergonomic Keyboard", "Microsoft", 450),
        ("Genius KB-110X", "Genius", 75), ("Aula F75", "Aula", 560),
    ]
    modelo, marca, base = r.choice(modelos)
    if base < 400 and marca in ("Logitech", "Microsoft", "Genius"):
        switch = "Membrana"
    else:
        switch = r.choice(["Mecánico Red (lineal)", "Mecánico Brown (táctil)", "Mecánico Blue (clicky)", "Óptico"])
    formato = r.choice(["Full size", "TKL", "75%", "65%", "60%"]) if switch != "Membrana" else r.choice(["Full size", "Compacto"])
    conexion = r.choice(["USB-C con cable", "Bluetooth", "Inalámbrico 2.4GHz + Bluetooth", "USB con cable"])
    retro = r.choice(["RGB", "Blanca", "Sin retroiluminación"]) if switch != "Membrana" else r.choice(["Sin retroiluminación", "Blanca"])
    dist = r.choice(["Español Latinoamericano", "Español Latinoamericano", "Inglés US"])
    nombre = f"Teclado {modelo} {formato} {switch.split(' (')[0]} {dist.split(' ')[0]}"
    desc = (f"Teclado {modelo} formato {formato}, switches {switch.lower()}, conexión {conexion} y "
            f"{'retroiluminación ' + retro if retro != 'Sin retroiluminación' else 'sin retroiluminación'}. Distribución {dist}.")
    atributos = {"marca": marca, "tipo_switch": switch, "formato": formato, "conexion": conexion,
                 "retroiluminacion": retro, "distribucion": dist}
    return nombre, desc, _precio(base * r.uniform(0.93, 1.1)), atributos, None, (6, 60)


def gen_mouse(r):
    modelos = [
        ("Logitech G502 Hero", "Logitech", 25600, "USB con cable", 11, 121, "Gaming", 450),
        ("Logitech G305 Lightspeed", "Logitech", 12000, "Inalámbrico 2.4GHz", 6, 99, "Gaming", 350),
        ("Logitech G Pro X Superlight 2", "Logitech", 32000, "Inalámbrico 2.4GHz", 5, 60, "Gaming", 1290),
        ("Logitech MX Master 3S", "Logitech", 8000, "Bluetooth + 2.4GHz", 7, 141, "Oficina / productividad", 890),
        ("Logitech M170", "Logitech", 1000, "Inalámbrico 2.4GHz", 3, 70, "Oficina / productividad", 95),
        ("Logitech Lift Vertical", "Logitech", 4000, "Bluetooth + 2.4GHz", 6, 125, "Ergonómico", 590),
        ("Razer DeathAdder V3", "Razer", 30000, "USB con cable", 6, 59, "Gaming", 590),
        ("Razer Basilisk V3", "Razer", 26000, "USB con cable", 11, 101, "Gaming", 520),
        ("Redragon Cobra M711", "Redragon", 10000, "USB con cable", 7, 110, "Gaming", 150),
        ("HyperX Pulsefire Haste 2", "HyperX", 26000, "USB con cable", 6, 53, "Gaming", 420),
        ("Microsoft Arc Mouse", "Microsoft", 1800, "Bluetooth", 3, 83, "Viaje", 520),
        ("Apple Magic Mouse", "Apple", 1300, "Bluetooth", 1, 99, "Oficina / productividad", 790),
        ("Glorious Model O 2", "Glorious", 26000, "Inalámbrico 2.4GHz", 6, 68, "Gaming", 690),
        ("Genius DX-120", "Genius", 1000, "USB con cable", 3, 85, "Oficina / productividad", 45),
    ]
    modelo, marca, dpi, conexion, botones, peso, uso, base = r.choice(modelos)
    color = r.choice(["Negro", "Blanco", "Gris"])
    nombre = f"Mouse {modelo} {color}"
    desc = (f"Mouse {modelo} de uso {uso.lower()}, sensor de hasta {dpi} DPI, {botones} botones, "
            f"{peso} gramos y conexión {conexion}. Color {color.lower()}.")
    atributos = {"marca": marca, "dpi_maximo": dpi, "conexion": conexion, "numero_botones": botones,
                 "peso_gramos": peso, "uso": uso}
    return nombre, desc, _precio(base * r.uniform(0.93, 1.1)), atributos, None, (8, 80)


def gen_tablet(r):
    modelos = [
        ("iPad 10.ª generación", "Apple", 10.9, [64, 256], 4, 3900),
        ("iPad Air M2", "Apple", 11.0, [128, 256, 512], 8, 5900),
        ("iPad Pro M4", "Apple", 13.0, [256, 512, 1024], 8, 11900),
        ("iPad mini", "Apple", 8.3, [128, 256], 8, 4600),
        ("Galaxy Tab A9+", "Samsung", 11.0, [64, 128], 4, 1800),
        ("Galaxy Tab S9 FE", "Samsung", 10.9, [128, 256], 6, 3500),
        ("Galaxy Tab S9 Ultra", "Samsung", 14.6, [256, 512], 12, 8900),
        ("Redmi Pad SE", "Xiaomi", 11.0, [128, 256], 6, 1500),
        ("Xiaomi Pad 6", "Xiaomi", 11.0, [128, 256], 8, 2900),
        ("Lenovo Tab M11", "Lenovo", 11.0, [64, 128], 4, 1500),
        ("Lenovo Tab P12", "Lenovo", 12.7, [128, 256], 8, 3100),
        ("Amazon Fire HD 10", "Amazon", 10.1, [32, 64], 3, 1100),
    ]
    modelo, marca, pantalla, alms, ram, base = r.choice(modelos)
    alm = r.choice(alms)
    conect = r.choice(["Wi-Fi", "Wi-Fi", "Wi-Fi + Celular (5G)"])
    color = r.choice(["Gris Espacial", "Plata", "Azul", "Grafito", "Rosa", "Verde Menta"])
    precio = base * (1 + 0.2 * alms.index(alm)) * (1.2 if "Celular" in conect else 1) * r.uniform(0.95, 1.06)
    alm_txt = "1TB" if alm == 1024 else f"{alm}GB"
    marca_txt = "" if marca in modelo else f"{marca} "
    nombre = f"Tablet {marca_txt}{modelo} {pantalla:g}\" {alm_txt} {conect.split(' (')[0]} {color}"
    desc = (f"Tablet {marca_txt}{modelo} con pantalla de {pantalla:g} pulgadas, {ram}GB de RAM, {alm_txt} de almacenamiento "
            f"y conectividad {conect}. Color {color.lower()}.")
    atributos = {"marca": marca, "tamano_pantalla_pulgadas": pantalla, "almacenamiento_gb": alm,
                 "memoria_ram_gb": ram, "conectividad": conect, "color": color}
    return nombre, desc, _precio(precio), atributos, None, (4, 35)


def gen_smartwatch(r):
    modelos = [
        ("Apple Watch Series 9", "Apple", [41, 45], "Sí", "WR50 (5 ATM)", 1, 3600),
        ("Apple Watch SE", "Apple", [40, 44], "Sí", "WR50 (5 ATM)", 1, 2300),
        ("Apple Watch Ultra 2", "Apple", [49], "Sí", "WR100 (10 ATM)", 3, 6900),
        ("Galaxy Watch6", "Samsung", [40, 44], "Sí", "5 ATM + IP68", 2, 2100),
        ("Galaxy Watch6 Classic", "Samsung", [43, 47], "Sí", "5 ATM + IP68", 2, 2900),
        ("Garmin Forerunner 265", "Garmin", [42, 46], "Sí", "5 ATM", 13, 3500),
        ("Garmin Venu 3", "Garmin", [41, 45], "Sí", "5 ATM", 14, 3700),
        ("Garmin Fenix 7", "Garmin", [47], "Sí", "10 ATM", 18, 5500),
        ("Amazfit GTR 4", "Amazfit", [46], "Sí", "5 ATM", 14, 1400),
        ("Amazfit Bip 5", "Amazfit", [46], "Sí", "IP68", 10, 690),
        ("Huawei Watch GT 4", "Huawei", [41, 46], "Sí", "5 ATM", 14, 1900),
        ("Xiaomi Smart Band 8", "Xiaomi", [37], "No", "5 ATM", 16, 390),
        ("Redmi Watch 4", "Xiaomi", [47], "Sí", "5 ATM", 20, 790),
        ("Fitbit Versa 4", "Fitbit", [40], "Sí", "5 ATM", 6, 1590),
    ]
    modelo, marca, cajas, gps, agua, dias, base = r.choice(modelos)
    caja = r.choice(cajas)
    correa = r.choice(["Silicón deportivo", "Nylon trenzado", "Acero inoxidable", "Cuero", "Fluoroelastómero"])
    color = r.choice(["Negro Medianoche", "Plata", "Blanco Estelar", "Verde Oliva", "Rosa", "Azul Marino", "Titanio"])
    precio = base * (1 + 0.08 * cajas.index(caja)) * (1.12 if correa in ("Acero inoxidable", "Cuero") else 1) * r.uniform(0.95, 1.06)
    marca_txt = "" if marca in modelo else f"{marca} "
    nombre = f"Smartwatch {marca_txt}{modelo} {caja}mm {color} correa {correa.split(' ')[0]}"
    desc = (f"Reloj inteligente {marca_txt}{modelo} con caja de {caja}mm, correa de {correa.lower()}, resistencia al agua {agua} "
            f"{'y GPS integrado' if gps == 'Sí' else 'sin GPS integrado'}. Autonomía de hasta {dias} día(s).")
    atributos = {"marca": marca, "tamano_caja_mm": caja, "material_correa": correa, "gps_integrado": gps,
                 "resistencia_agua": agua, "autonomia_dias": dias, "color": color}
    return nombre, desc, _precio(precio), atributos, None, (4, 40)


def gen_jeans(r):
    lineas = [
        ("Jeans Levi's 501 Original", "Recto", "Caballero", 590), ("Jeans Levi's 511 Slim", "Slim", "Caballero", 560),
        ("Jeans Levi's 721 High Rise Skinny", "Skinny", "Dama", 560), ("Jeans Wrangler Texas", "Recto", "Caballero", 420),
        ("Jeans Lee Relaxed Fit", "Relaxed", "Caballero", 450), ("Jeans Mom Fit Tiro Alto", "Mom", "Dama", 360),
        ("Jeans Wide Leg Tiro Alto", "Wide Leg", "Dama", 390), ("Jeans Bootcut Clásico", "Bootcut", "Dama", 340),
        ("Jeans Skinny Stretch", "Skinny", "Dama", 290), ("Jeans Carpenter Workwear", "Relaxed", "Caballero", 380),
        ("Jeans Baggy 90s", "Baggy", "Unisex", 370), ("Jeans Slim Tapered", "Slim", "Caballero", 330),
    ]
    lavados = ["Azul índigo oscuro", "Azul medio stone wash", "Azul claro deslavado", "Negro", "Gris carbón", "Rotos azul medio"]
    materiales = ["100% Algodón (denim rígido)", "98% Algodón 2% Elastano", "92% Algodón 6% Poliéster 2% Elastano"]
    linea, corte, genero, base = r.choice(lineas)
    cintura = r.choice([24, 25, 26, 27, 28, 29, 30]) if genero == "Dama" else r.choice([28, 29, 30, 31, 32, 33, 34, 36, 38, 40])
    largo = r.choice([28, 30, 32]) if genero == "Dama" else r.choice([30, 32, 34])
    lavado = r.choice(lavados)
    material = r.choice(materiales) if corte not in ("Skinny",) else "92% Algodón 6% Poliéster 2% Elastano"
    nombre = f"{linea} {lavado} {cintura}x{largo}"
    para = "diseño unisex" if genero == "Unisex" else f"para {genero.lower()}"
    desc = f"{linea} corte {corte.lower()}, {para}, lavado {lavado.lower()}, {material.lower()}. Talla {cintura} x {largo}."
    atributos = {"talla_cintura": cintura, "largo_pierna": largo, "corte": corte, "color_lavado": lavado,
                 "material": material, "genero": genero}
    return nombre, desc, _precio(base * r.uniform(0.92, 1.1)), atributos, None, (10, 70)


def gen_sudadera(r):
    estilos = [
        ("Sudadera con Capucha Básica", "Con capucha", 260), ("Sudadera Cuello Redondo Crewneck", "Cuello redondo", 230),
        ("Sudadera con Cierre Completo", "Con cierre", 290), ("Sudadera Oversize Estampada Antigua Guatemala", "Con capucha", 320),
        ("Sudadera Universitaria Vintage", "Cuello redondo", 280), ("Hoodie Heavyweight Streetwear", "Con capucha", 390),
        ("Sudadera Media Cremallera Quarter-Zip", "Media cremallera", 310), ("Sudadera Deportiva Tech Fleece", "Con cierre", 450),
    ]
    materiales = ["80% Algodón 20% Poliéster (felpa)", "100% Algodón French Terry", "60% Algodón 40% Poliéster", "100% Poliéster técnico"]
    estilo, tipo, base = r.choice(estilos)
    color = r.choice(COLORES_ROPA)
    talla = r.choice(TALLAS_ROPA)
    genero = r.choice(["Unisex", "Unisex", "Dama", "Caballero"])
    material = "100% Poliéster técnico" if "Tech" in estilo else r.choice(materiales)
    nombre = f"{estilo} {color} Talla {talla}"
    desc = f"{estilo} {genero.lower()} en color {color.lower()}, {material.lower()}. Estilo {tipo.lower()}, talla {talla}."
    atributos = {"talla": talla, "color": color, "material": material, "estilo": tipo, "genero": genero}
    return nombre, desc, _precio(base * r.uniform(0.9, 1.12)), atributos, None, (10, 70)


def gen_tenis(r):
    modelos = [
        ("Nike Air Force 1 '07", "Nike", "Casual", "Cuero", 990), ("Nike Air Max 90", "Nike", "Casual", "Cuero y malla", 1190),
        ("Nike Pegasus 41", "Nike", "Running", "Malla", 1090), ("Nike Revolution 7", "Nike", "Running", "Malla", 540),
        ("Adidas Samba OG", "Adidas", "Casual", "Cuero y gamuza", 890), ("Adidas Ultraboost Light", "Adidas", "Running", "Primeknit", 1490),
        ("Adidas Duramo SL", "Adidas", "Running", "Malla", 520), ("Puma Suede Classic", "Puma", "Casual", "Gamuza", 640),
        ("Puma Velocity Nitro 3", "Puma", "Running", "Malla", 990), ("New Balance 574", "New Balance", "Casual", "Gamuza y malla", 790),
        ("New Balance Fresh Foam 1080", "New Balance", "Running", "Malla", 1390), ("Converse Chuck Taylor All Star", "Converse", "Casual", "Lona", 490),
        ("Vans Old Skool", "Vans", "Skate", "Lona y gamuza", 560), ("Reebok Nano X4", "Reebok", "Training", "Malla", 1090),
        ("Under Armour Curry 11", "Under Armour", "Básquetbol", "Malla", 1390), ("Skechers Go Walk 7", "Skechers", "Caminata", "Malla", 590),
        ("Asics Gel-Nimbus 26", "Asics", "Running", "Malla", 1290), ("Nike LeBron Witness 8", "Nike", "Básquetbol", "Malla sintética", 890),
    ]
    modelo, marca, uso, material, base = r.choice(modelos)
    genero = r.choice(["Caballero", "Dama", "Unisex"])
    talla = r.choice([5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0]) if genero == "Dama" else r.choice([7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 12.0])
    color = r.choice(["Blanco", "Negro", "Blanco/Negro", "Gris", "Azul Marino", "Rojo", "Beige", "Verde Neón"])
    nombre = f"Tenis {modelo} {color} Talla {talla:g} US"
    desc = f"Tenis {modelo} para {uso.lower()}, exterior de {material.lower()}, color {color.lower()}. Talla {talla:g} US ({genero.lower()})."
    atributos = {"marca": marca, "talla_us": talla, "color": color, "uso": uso, "material_exterior": material, "genero": genero}
    return nombre, desc, _precio(base * r.uniform(0.93, 1.08)), atributos, None, (4, 40)


def gen_vestido(r):
    estilos = [
        ("Vestido Midi Cruzado", "Midi", "Casual", 320), ("Vestido Maxi Playero", "Maxi", "Playa", 360),
        ("Vestido Mini de Fiesta con Lentejuelas", "Mini", "Fiesta", 520), ("Vestido Camisero", "Midi", "Oficina", 340),
        ("Vestido Slip Satinado", "Midi", "Fiesta", 450), ("Vestido Off-Shoulder", "Mini", "Casual", 290),
        ("Vestido con Detalle de Güipil", "Midi", "Casual", 580), ("Vestido Tubo Ejecutivo", "Midi", "Oficina", 390),
        ("Vestido Largo de Gala", "Maxi", "Fiesta", 890), ("Vestido Babydoll", "Mini", "Casual", 270),
    ]
    materiales = ["100% Algodón", "Lino", "Viscosa", "Satín de poliéster", "Chiffon", "Algodón con elastano"]
    estampados = ["Liso", "Floral", "Rayas", "Lunares", "Textil típico guatemalteco", "Animal print"]
    estilo, largo, ocasion, base = r.choice(estilos)
    estampado = "Textil típico guatemalteco" if "Güipil" in estilo else r.choice(estampados)
    color = r.choice(["Negro", "Rojo", "Blanco", "Azul Rey", "Verde Esmeralda", "Beige", "Rosa Palo", "Vino", "Amarillo"])
    talla = r.choice(["XS", "S", "M", "L", "XL"])
    material = r.choice(materiales)
    nombre = f"{estilo} {color}{'' if estampado == 'Liso' else ' ' + estampado} Talla {talla}"
    desc = f"{estilo} largo {largo.lower()} en {material.lower()}, color {color.lower()} con estampado {estampado.lower()}. Ideal para ocasión {ocasion.lower()}. Talla {talla}."
    atributos = {"talla": talla, "color": color, "largo": largo, "material": material, "ocasion": ocasion, "estampado": estampado}
    return nombre, desc, _precio(base * r.uniform(0.9, 1.12)), atributos, None, (5, 40)


def gen_gorra(r):
    estilos = [("Gorra Snapback", "Snapback", 160), ("Gorra Dad Hat", "Dad hat", 130), ("Gorra Trucker de Malla", "Trucker", 140),
               ("Gorra Fitted 59FIFTY", "Fitted", 290), ("Sombrero Bucket", "Bucket", 150), ("Gorra Deportiva Running", "Deportiva", 180)]
    temas = ["Guatemala", "Quetzal", "Volcán de Fuego", "Chapín", "Lisa", "Antigua", "Atitlán", "Xela", "Lisa"]
    estilo, tipo, base = r.choice(estilos)
    tema = r.choice(temas)
    color = r.choice(["Negro", "Blanco", "Azul Marino", "Beige", "Verde Olivo", "Gris", "Celeste", "Café"])
    material = "Poliéster Dry-Fit" if tipo == "Deportiva" else r.choice(["100% Algodón", "Gabardina de algodón", "Poliéster y malla", "Pana"])
    ajuste = "Talla fija" if tipo == "Fitted" else ("Talla única" if tipo == "Bucket" else r.choice(["Ajustable con broche", "Ajustable con hebilla", "Ajustable con velcro"]))
    bordado = "Sin bordado" if tema == "Lisa" else r.choice(["Bordado frontal", "Bordado 3D", "Parche bordado"])
    nombre = f"{estilo} {tema} {color}" if tema != "Lisa" else f"{estilo} Lisa {color}"
    desc = f"{estilo} color {color.lower()} en {material.lower()}, {ajuste.lower()}. " + (
        "Diseño liso, sin logos." if tema == "Lisa" else f"{bordado} con motivo {tema}.")
    atributos = {"estilo": tipo, "color": color, "material": material, "ajuste": ajuste, "bordado": bordado}
    return nombre, desc, _precio(base * r.uniform(0.9, 1.12)), atributos, None, (10, 80)


def gen_electrodomestico(r):
    modelos = [
        ("Cafetera de goteo", "Cafetera de Goteo Programable", ["Oster", "Hamilton Beach", "Black+Decker", "Cuisinart"], (900, 1100), (1.5, 1.8), 390),
        ("Cafetera de goteo", "Cafetera Térmica 10 Tazas", ["Cuisinart", "Hamilton Beach", "Mr. Coffee"], (1000, 1200), (1.5, 1.5), 690),
        ("Batidora de pedestal", "Batidora de Pedestal", ["KitchenAid", "Oster", "Hamilton Beach"], (300, 500), (3.5, 5.5), 1490),
        ("Licuadora", "Licuadora de Alto Rendimiento", ["Oster", "Ninja", "Vitamix", "Black+Decker"], (600, 1500), (1.25, 2.0), 590),
        ("Licuadora", "Licuadora Personal para Batidos", ["Nutribullet", "Oster", "Ninja"], (250, 900), (0.6, 0.9), 390),
        ("Molino de café", "Molino de Café de Muelas", ["Baratza", "Cuisinart", "Hamilton Beach"], (150, 250), (0.2, 0.25), 790),
        ("Horno tostador", "Horno Tostador Eléctrico", ["Black+Decker", "Oster", "Hamilton Beach", "Cuisinart"], (1200, 1500), (9.0, 25.0), 690),
    ]
    tipo, linea, marcas, (pmin, pmax), (cmin, cmax), base = r.choice(modelos)
    marca = r.choice(marcas)
    potencia = r.randrange(pmin, pmax + 1, 50)
    capacidad = round(r.uniform(cmin, cmax), 1) if cmin != cmax else cmin
    color = r.choice(["Negro", "Acero inoxidable", "Blanco", "Rojo", "Gris Pizarra"])
    garantia = r.choice([6, 12, 12, 24])
    precio = base * (3 if marca in ("KitchenAid", "Vitamix") else 1) * r.uniform(0.9, 1.15)
    nombre = f"{linea} {marca} {capacidad:g}L {color}"
    desc = f"{linea} marca {marca} de {potencia}W con capacidad de {capacidad:g} litros, acabado {color.lower()}. Garantía de {garantia} meses."
    atributos = {"marca": marca, "tipo_electrodomestico": tipo, "potencia_w": potencia, "capacidad_litros": capacidad,
                 "color": color, "garantia_meses": garantia}
    return nombre, desc, _precio(precio), atributos, tipo, (4, 40)


def gen_utensilio(r):
    modelos = [
        ("Olla", "Olla de Hierro Fundido Esmaltada", ["Hierro fundido esmaltado"], [24, 26, 28], [1], 590),
        ("Olla", "Olla de Presión", ["Acero inoxidable", "Aluminio"], [22, 24], [1], 450),
        ("Olla", "Batería de Cocina", ["Acero inoxidable", "Aluminio antiadherente", "Cerámica"], [16, 20, 24], [7, 10, 12], 890),
        ("Cacerola", "Cacerola con Tapa de Vidrio", ["Acero inoxidable", "Aluminio antiadherente", "Cerámica"], [18, 20, 24], [1], 260),
        ("Sartén", "Sartén Antiadherente", ["Aluminio antiadherente", "Cerámica"], [20, 24, 28, 30], [1], 190),
        ("Sartén", "Sartén de Hierro Fundido", ["Hierro fundido"], [20, 25, 30], [1], 290),
        ("Sartén", "Set de Sartenes", ["Aluminio antiadherente", "Cerámica", "Acero inoxidable"], [20, 24, 28], [3], 420),
        ("Juego de cuchillos", "Juego de Cuchillos con Base", ["Acero inoxidable alemán", "Acero al carbono"], [20, 23], [6, 8, 14], 690),
    ]
    tipo, linea, materiales, diametros, piezas_op, base = r.choice(modelos)
    marca = r.choice(["Tramontina", "T-fal", "Oster", "Lodge", "Imusa", "Le Creuset", "Cuisinart"] if tipo != "Juego de cuchillos" else ["Tramontina", "Victorinox", "Zwilling", "Cuisinart"])
    material = r.choice(materiales)
    diametro = r.choice(diametros)
    piezas = r.choice(piezas_op)
    induccion = "No" if material == "Aluminio" or tipo == "Juego de cuchillos" else r.choice(["Sí", "Sí", "No"])
    color = "Acero" if tipo == "Juego de cuchillos" else r.choice(["Negro", "Rojo", "Gris", "Crema", "Azul", "Acero"])
    precio = base * (3.5 if marca in ("Le Creuset", "Zwilling") else 1) * (1 + (piezas - 1) * 0.05) * r.uniform(0.9, 1.12)
    medida = f"{diametro}cm" if piezas == 1 else f"{piezas} piezas"
    nombre = f"{linea} {marca} {medida} {color}" if tipo != "Juego de cuchillos" else f"{linea} {marca} {piezas} Piezas"
    desc = (f"{linea} {marca} de {material.lower()}, {medida}"
            f"{', apto para estufa de inducción' if induccion == 'Sí' else ''}. Color {color.lower()}.")
    atributos = {"tipo_utensilio": tipo, "material": material, "diametro_cm": diametro, "piezas": piezas,
                 "apto_induccion": induccion, "color": color}
    return nombre, desc, _precio(precio), atributos, tipo, (6, 60)


def gen_bicicleta(r):
    modelos = [
        ("Ruta", "Specialized Allez", 28, "Aluminio", [16, 18, 22], 8900), ("Ruta", "Trek Domane AL 2", 28, "Aluminio", [16, 18], 9500),
        ("Ruta", "Giant TCR Advanced", 28, "Carbono", [22, 24], 21900), ("Urbana", "Trek FX 1", 28, "Aluminio", [8, 21, 24], 5200),
        ("Urbana", "Giant Escape 3", 28, "Aluminio", [21, 24], 4900), ("Fixie", "Fixie Urbana Chapina", 28, "Acero", [1], 2400),
        ("Fixie", "State Bicycle 4130", 28, "Cromoly", [1], 3600), ("Híbrida", "Cannondale Quick 6", 28, "Aluminio", [16, 21], 5600),
        ("Gravel", "Specialized Diverge E5", 28, "Aluminio", [18, 20, 22], 11900), ("Gravel", "Cannondale Topstone", 28, "Aluminio", [18, 22], 12900),
        ("Montaña", "Trek Marlin 5", 29, "Aluminio", [16, 18, 24], 6400), ("Montaña", "Giant Talon 3", 27.5, "Aluminio", [16, 18], 5600),
    ]
    tipo, modelo, aro, marco, velocidades, base = r.choice(modelos)
    vel = r.choice(velocidades)
    talla = r.choice(["S", "M", "M", "L", "XL"])
    color = r.choice(["Negro Mate", "Blanco", "Rojo", "Azul Petróleo", "Gris Titanio", "Verde Bosque", "Naranja"])
    nombre = f"Bicicleta {tipo} {modelo} {'Aro ' + format(aro, 'g') if tipo == 'Montaña' else '700c'} Talla {talla} {color}"
    tipo_txt = {"Ruta": "de ruta", "Montaña": "de montaña"}.get(tipo, tipo.lower())
    desc = (f"Bicicleta {tipo_txt} {modelo} con marco de {marco.lower()}, {vel} velocidad{'es' if vel > 1 else ''} "
            f"y aro de {aro:g} pulgadas. Talla de marco {talla}, color {color.lower()}.")
    atributos = {"tipo_bicicleta": tipo, "tamano_aro": aro, "material_marco": marco, "numero_velocidades": vel,
                 "talla_marco": talla, "color": color}
    return nombre, desc, _precio(base * r.uniform(0.93, 1.08)), atributos, None, (2, 15)


def gen_pesas(r):
    tipos = [
        ("Mancuerna hexagonal", [2.5, 5, 7.5, 10, 12.5, 15, 20, 25], "Hierro recubierto de caucho", ["Par", "Unidad"], 24),
        ("Mancuerna de neopreno", [1, 2, 3, 4, 5], "Neopreno", ["Par"], 30),
        ("Mancuerna ajustable", [20, 24, 32, 40], "Acero y plástico ABS", ["Unidad", "Par"], 38),
        ("Kettlebell", [4, 8, 12, 16, 20, 24], "Hierro fundido", ["Unidad"], 26),
        ("Disco olímpico", [5, 10, 15, 20, 25], "Hierro recubierto de caucho", ["Par"], 22),
        ("Barra olímpica", [15, 20], "Acero cromado", ["Unidad"], 60),
        ("Set de mancuernas con rack", [50, 75, 100], "Hierro recubierto de caucho", ["Set"], 20),
    ]
    tipo, pesos, material, presentaciones, q_por_kg = r.choice(tipos)
    peso = r.choice(pesos)
    pres = r.choice(presentaciones)
    color = "Plateado" if "Barra" in tipo else r.choice(["Negro", "Negro", "Gris", "Rosa", "Azul", "Verde"]) if "neopreno" in tipo else r.choice(["Negro", "Gris"])
    marca = r.choice(["Bowflex", "Everlast", "Rogue", "York Barbell", "CAP Barbell", "Sportfitness GT"])
    factor = 2 if pres == "Par" else 1
    precio = peso * q_por_kg * factor * r.uniform(0.9, 1.15) + (600 if "rack" in tipo else 0)
    nombre = f"{tipo} {marca} {peso:g}kg ({pres})"
    detalle_peso = f"{peso:g} kg por unidad" if pres == "Par" else (f"{peso:g} kg en total" if pres == "Set" else f"{peso:g} kg")
    desc = f"{tipo} {marca} de {detalle_peso}. Material: {material}. Se vende por {pres.lower()}."
    atributos = {"tipo_equipo": tipo, "peso_kg": peso, "material": material, "presentacion": pres, "color": color}
    return nombre, desc, _precio(max(precio, 60)), atributos, None, (3, 40)


def gen_yoga(r):
    materiales = [("TPE", 190), ("PVC", 120), ("Caucho natural", 390), ("Corcho y caucho", 450), ("NBR espuma", 150)]
    material, base = r.choice(materiales)
    grosor = r.choice([4, 5, 6, 8, 10]) if material != "Corcho y caucho" else r.choice([4, 5])
    largo = r.choice([173, 183, 185])
    antides = "Sí" if material != "NBR espuma" else r.choice(["Sí", "No"])
    color = r.choice(["Morado", "Verde Agua", "Negro", "Azul Marino", "Rosa", "Terracota", "Gris", "Natural"])
    marca = r.choice(["Manduka", "Gaiam", "Liforme", "Reebok", "Atitlán Yoga Co."])
    nombre = f"Tapete de Yoga {marca} {material} {grosor}mm {color}"
    desc = f"Tapete de yoga {marca} de {material.lower()}, {grosor}mm de grosor y {largo}cm de largo. {'Superficie antideslizante. ' if antides == 'Sí' else ''}Color {color.lower()}."
    atributos = {"material": material, "grosor_mm": grosor, "largo_cm": largo, "antideslizante": antides, "color": color}
    return nombre, desc, _precio(base * (1 + grosor / 20) * r.uniform(0.9, 1.15)), atributos, None, (8, 60)


def gen_mochila(r):
    modelos = [
        ("Mochila para Laptop", "Laptop", [20, 25, 30], ["Poliéster", "Nylon balístico"], 290),
        ("Mochila Escolar", "Escolar", [18, 22, 25], ["Poliéster", "Lona"], 190),
        ("Mochila de Senderismo", "Senderismo", [30, 40, 50, 65], ["Nylon ripstop"], 590),
        ("Mochila de Viaje Cabina", "Viaje", [35, 40, 45], ["Poliéster", "Nylon ripstop"], 490),
        ("Mochila Urbana Roll-Top", "Urbana", [20, 25], ["Lona encerada", "PVC laminado"], 390),
        ("Mochila de Cuero", "Urbana", [15, 20], ["Cuero genuino"], 890),
    ]
    linea, uso, capacidades, materiales, base = r.choice(modelos)
    marca = r.choice(["Totto", "Samsonite", "The North Face", "Jansport", "Osprey", "Deuter", "Xela Outdoor"])
    cap = r.choice(capacidades)
    material = r.choice(materiales)
    laptop = r.choice(["Hasta 14 pulgadas", "Hasta 15.6 pulgadas", "Hasta 17 pulgadas"]) if uso in ("Laptop", "Viaje", "Urbana") else r.choice(["No", "Hasta 14 pulgadas"])
    imper = "Sí" if material in ("Lona encerada", "PVC laminado", "Nylon ripstop") else r.choice(["No", "Resistente a salpicaduras"])
    color = r.choice(["Negro", "Gris Carbón", "Azul Marino", "Verde Olivo", "Café", "Rojo", "Mostaza"])
    precio = base * (1 + (cap - capacidades[0]) / 60) * (1.8 if marca in ("Samsonite", "Osprey", "The North Face") else 1) * r.uniform(0.9, 1.12)
    nombre = f"{linea} {marca} {cap}L {color}"
    desc = (f"{linea} {marca} de {cap} litros en {material.lower()}, color {color.lower()}. "
            f"Compartimento para laptop: {laptop.lower()}. Impermeable: {imper.lower()}.")
    atributos = {"capacidad_litros": cap, "material": material, "uso": uso, "compartimento_laptop": laptop,
                 "impermeable": imper, "color": color}
    return nombre, desc, _precio(precio), atributos, None, (6, 50)


def gen_perfume(r):
    fragancias = [
        ("Carolina Herrera", "Good Girl", "Dama", "Oriental"), ("Carolina Herrera", "212 VIP Men", "Caballero", "Amaderada"),
        ("Paco Rabanne", "1 Million", "Caballero", "Oriental"), ("Paco Rabanne", "Lady Million", "Dama", "Floral"),
        ("Dior", "Sauvage", "Caballero", "Fougère"), ("Dior", "J'adore", "Dama", "Floral"),
        ("Chanel", "Bleu de Chanel", "Caballero", "Amaderada"), ("Chanel", "Coco Mademoiselle", "Dama", "Oriental"),
        ("Versace", "Eros", "Caballero", "Fougère"), ("Versace", "Bright Crystal", "Dama", "Floral"),
        ("Calvin Klein", "CK One", "Unisex", "Cítrica"), ("Giorgio Armani", "Acqua di Giò", "Caballero", "Acuática"),
        ("Lancôme", "La Vie Est Belle", "Dama", "Floral"), ("Jean Paul Gaultier", "Le Male", "Caballero", "Oriental"),
        ("Hugo Boss", "Boss Bottled", "Caballero", "Amaderada"), ("Yves Saint Laurent", "Libre", "Dama", "Floral"),
        ("Montblanc", "Explorer", "Caballero", "Amaderada"), ("Tommy Hilfiger", "Tommy Girl", "Dama", "Cítrica"),
    ]
    marca, linea, genero, familia = r.choice(fragancias)
    conc = r.choice(["Eau de Toilette", "Eau de Parfum", "Eau de Parfum", "Parfum"]) if linea != "CK One" else "Eau de Toilette"
    volumen = r.choice([30, 50, 100, 100, 125, 200]) if conc != "Parfum" else r.choice([50, 100])
    base_ml = {"Eau de Toilette": 7.5, "Eau de Parfum": 9.5, "Parfum": 12.5}[conc]
    precio = (250 + volumen * base_ml) * r.uniform(0.9, 1.12)
    nombre = f"Perfume {marca} {linea} {conc} {volumen}ml"
    desc = f"Fragancia {linea} de {marca}, {conc} de {volumen}ml para {genero.lower()}. Familia olfativa {familia.lower()}. Producto original sellado."
    atributos = {"marca": marca, "concentracion": conc, "volumen_ml": volumen, "genero": genero, "familia_olfativa": familia}
    return nombre, desc, _precio(precio), atributos, None, (5, 40)


def gen_piel(r):
    productos = [
        ("Sérum", [30], 180), ("Crema hidratante", [50], 160), ("Protector solar SPF 50+", [50, 100], 170),
        ("Limpiador facial", [150, 250], 120), ("Tónico facial", [200], 110), ("Contorno de ojos", [15], 190),
    ]
    marcas = ["CeraVe", "La Roche-Posay", "The Ordinary", "Neutrogena", "Cetaphil", "Bioderma", "Eucerin", "Vichy", "Garnier", "Isdin"]
    ingredientes = ["Ácido hialurónico", "Niacinamida", "Vitamina C", "Retinol", "Centella asiática", "Ácido salicílico", "Ceramidas"]
    tipo, contenidos, base = r.choice(productos)
    marca = r.choice(marcas)
    ml = r.choice(contenidos)
    ing = r.choice(ingredientes)
    piel = r.choice(["Grasa", "Seca", "Mixta", "Sensible", "Todo tipo de piel"])
    precio = base * (ml / contenidos[0]) ** 0.6 * (0.6 if marca == "The Ordinary" else 1) * r.uniform(0.9, 1.15)
    nombre = f"{tipo} {marca} con {ing} {ml}ml Piel {piel if piel != 'Todo tipo de piel' else 'Todo Tipo'}"
    desc = f"{tipo} de {marca} formulado con {ing.lower()} para piel {piel.lower()}. Contenido: {ml}ml. Uso diario."
    atributos = {"marca": marca, "tipo_producto": tipo.replace(" SPF 50+", ""), "tipo_piel": piel,
                 "contenido_ml": ml, "ingrediente_principal": ing}
    return nombre, desc, _precio(precio), atributos, None, (10, 90)


GENERADORES = {
    "Laptops": gen_laptop, "Monitores": gen_monitor, "Playeras": gen_playera, "Celulares": gen_celular,
    "Audífonos": gen_audifono, "Teclados": gen_teclado, "Mouse": gen_mouse, "Tablets": gen_tablet,
    "Smartwatches": gen_smartwatch, "Jeans": gen_jeans, "Sudaderas": gen_sudadera, "Tenis": gen_tenis,
    "Vestidos": gen_vestido, "Gorras": gen_gorra, "Electrodomésticos de Cocina": gen_electrodomestico,
    "Utensilios de Cocina": gen_utensilio, "Bicicletas": gen_bicicleta, "Pesas y Mancuernas": gen_pesas,
    "Tapetes de Yoga": gen_yoga, "Mochilas": gen_mochila, "Perfumes": gen_perfume, "Cuidado de la Piel": gen_piel,
}

CIERRES_DESCRIPCION = [
    "Envío a todo Guatemala.", "Factura electrónica FEL incluida.", "Garantía directa con la tienda.",
    "Entrega en 24-48 horas en la ciudad capital.", "Producto nuevo y sellado.", "Pago contra entrega disponible en zona metropolitana.",
    "", "", "",
]


# ============================================================================
# 6. ARMADO DE LA SEMILLA
# ============================================================================
def elegir_imagenes(r, subcategoria, tipo_foto):
    cfg = FOTOS[subcategoria]
    if "por_tipo" in cfg:
        pool_portada = cfg["por_tipo"][tipo_foto]
        pool_extra = [f for f in pool_portada + cfg["ambiente"]]
    else:
        pool_portada = cfg["fotos"]
        pool_extra = cfg["fotos"]
    cantidad = r.choices([1, 2, 3], weights=[30, 40, 30])[0]
    portada = r.choice(pool_portada)
    restantes = [f for f in pool_extra if f != portada]
    extras = r.sample(restantes, min(cantidad - 1, len(restantes)))
    return [portada] + extras


def elegir_extras(r, subcategoria):
    candidatos = [c for c in EXTRAS_POR_SUBCATEGORIA.get(subcategoria, []) + EXTRAS_GENERALES
                  if c[0] not in ESQUEMA_CLAVES[subcategoria]]
    cantidad = r.choice([1, 1, 2])
    extras = {clave: r.choice(valores) for clave, valores in r.sample(candidatos, cantidad)}
    # Una "garantía extendida" no tiene sentido en ropa, belleza o tapetes: ahí se sustituye por
    # un extra equivalente de la categoría. Se hace DESPUÉS del sorteo, sin consumir números
    # aleatorios, para no alterar el resto de la semilla ya cargada en Postgres.
    if "garantia_extendida" in extras and subcategoria in SUSTITUTO_GARANTIA:
        clave_nueva, valores_nuevos = SUSTITUTO_GARANTIA[subcategoria]
        indice = EXTRAS_GENERALES[1][1].index(extras.pop("garantia_extendida"))
        extras[clave_nueva] = valores_nuevos[indice]
    return extras


_CAMBIO_TALLA = ("cambio_de_talla", ["30 días", "60 días"])
SUSTITUTO_GARANTIA = {
    "Playeras": _CAMBIO_TALLA, "Jeans": _CAMBIO_TALLA, "Sudaderas": _CAMBIO_TALLA,
    "Tenis": _CAMBIO_TALLA, "Vestidos": _CAMBIO_TALLA, "Gorras": _CAMBIO_TALLA,
    "Perfumes": ("muestra_de_regalo", ["Miniatura de 10ml", "Miniatura de 10ml y bolsa de regalo"]),
    "Cuidado de la Piel": ("muestra_de_regalo", ["Sachet de limpiador", "Sachet de limpiador y neceser"]),
    "Tapetes de Yoga": ("incluye_bolsa", ["Bolsa de tela", "Bolsa impermeable"]),
}


def generar():
    r = random.Random(SEMILLA_ALEATORIA)

    tiendas = [(n, e, g, p) for n, e, g, p in TIENDAS_EXISTENTES] + [(n, e, g, 1) for n, e, g in TIENDAS_NUEVAS]
    for _, _, giro, _ in tiendas:
        for s in giro:
            assert s in CANTIDAD_POR_SUBCATEGORIA, s
    assert sum(CANTIDAD_POR_SUBCATEGORIA.values()) == TOTAL_PRODUCTOS

    productos = []
    secuencia = 0
    for subcategoria, cantidad in CANTIDAD_POR_SUBCATEGORIA.items():
        vendedores = [(e, p) for _, e, g, p in tiendas if subcategoria in g]
        # Reparto base: primero 1 producto garantizado por tienda del giro, el resto ponderado.
        asignacion = [e for e, _ in vendedores]
        while len(asignacion) < cantidad:
            asignacion.append(r.choices([e for e, _ in vendedores], weights=[p for _, p in vendedores])[0])
        r.shuffle(asignacion)
        for email_vendedor in asignacion:
            secuencia += 1
            nombre, desc, precio, atributos, tipo_foto, (smin, smax) = GENERADORES[subcategoria](r)
            assert list(atributos.keys()) == ESQUEMA_CLAVES[subcategoria], (subcategoria, atributos.keys())
            cierre = r.choice(CIERRES_DESCRIPCION)
            if cierre:
                desc = f"{desc} {cierre}"
            if r.random() < PROPORCION_PERSONALIZADOS:
                atributos = {**atributos, **elegir_extras(r, subcategoria)}
            marca_sku = "".join(ch for ch in nombre.split(" ")[1 if nombre.split(" ")[0] in (
                "Laptop", "Monitor", "Audífonos", "Teclado", "Mouse", "Tablet", "Smartwatch", "Tenis", "Perfume", "Bicicleta") else 0].upper()
                if ch.isalnum() and ch.isascii())[:4] or "GEN"
            sku = f"{PREFIJO_SKU[subcategoria]}-{marca_sku}-{secuencia:04d}"
            productos.append({
                "sku": sku, "nombre": nombre[:200], "descripcion": desc, "precio": precio,
                "subcategoria": subcategoria, "email_vendedor": email_vendedor,
                "stock": r.randint(smin, smax), "dias": r.randint(1, 170), "minutos": r.randint(0, 1439),
                "atributos": atributos, "imagenes": elegir_imagenes(r, subcategoria, tipo_foto),
            })
    return tiendas, productos


def _sql(texto):
    return "'" + str(texto).replace("'", "''") + "'"


def escribir_sql(productos):
    L = []
    L.append("""-- ============================================================================
-- TIENDAYA - SEMILLA MASIVA: 40 TIENDAS (VENDEDORES) + 1000 PRODUCTOS + INVENTARIO
-- ============================================================================
-- ARCHIVO GENERADO por database/migrations/generar_semilla_masiva.py -- no lo edites a
-- mano: cambia el generador y vuelve a correrlo (es determinístico, semilla fija).
--
-- Propósito: dar al catálogo un volumen realista (1000 productos en 22 subcategorías
-- hoja, repartidos entre 40 tiendas nuevas + las 2 tiendas semilla del DDL) para que la
-- búsqueda, los filtros por atributo, los índices de Mongo y las agregaciones se
-- ejerciten con datos variados.
--
-- Idempotente y sin IDs fijos (mismo criterio que datos_semilla_usuarios.sql):
--   * categorías  -> ON CONFLICT (nombre_categoria) DO NOTHING; el padre se busca por nombre.
--   * vendedores  -> ON CONFLICT (email) DO NOTHING.
--   * productos   -> ON CONFLICT (sku) DO NOTHING; vendedor y categoría se buscan por
--                    email / nombre_categoria en tiempo de ejecución.
--   * inventario  -> ON CONFLICT (id_producto) DO NOTHING (no pisa el stock de una
--                    base en uso si el script se vuelve a correr).
-- Además cada INSERT filtra con NOT EXISTS antes de insertar: ON CONFLICT por sí solo
-- igual consume un valor de la secuencia SERIAL por cada fila repetida, y volver a correr
-- el script adelantaría 1000 posiciones los IDs de los productos que se creen después.
-- Las categorías existentes del DDL (Tecnología, Laptops, Monitores, Moda y Ropa,
-- Playeras) no se modifican: solo se usan como padre/hoja.
--
-- Contraseña de TODAS las tiendas nuevas: "Tiendaya123!" (mismo hash scrypt de los
-- usuarios semilla). Ver README.md para la lista de credenciales.
--
-- Después de correrlo, lleva los productos nuevos al catálogo de MongoDB con:
--   python database/migrations/migracion_postgres_a_mongo.py --incremental
-- (los atributos e imágenes de cada SKU salen de datos_semilla_masivos_catalogo.json).
--
-- Cómo correrlo (después del DDL y de datos_semilla_productos.sql):
-- psql -U postgres -d tiendaya_db -f database/postgres/datos_semilla_masivos.sql

-- El archivo está en UTF-8: se declara explícitamente porque psql en Windows puede tomar
-- la página de códigos de la consola (WIN1252) y fallar con las tildes/eñes.
SET client_encoding = 'UTF8';

BEGIN;
""")
    L.append("-- 1. Categorías padre nuevas")
    L.append("INSERT INTO categorias (nombre_categoria, descripcion, id_categoria_padre, esquema_atributos)")
    L.append("SELECT v.nombre, v.descripcion, NULL, '[]'::jsonb")
    L.append("FROM (VALUES")
    L.append(",\n".join(f"    ({_sql(n)}, {_sql(d)})" for n, d in CATEGORIAS_PADRE_NUEVAS))
    L.append(") AS v(nombre, descripcion)")
    L.append("WHERE NOT EXISTS (SELECT 1 FROM categorias c WHERE c.nombre_categoria = v.nombre)")
    L.append("ON CONFLICT (nombre_categoria) DO NOTHING;\n")

    L.append("-- 2. Subcategorías hoja nuevas, cada una con su esquema_atributos (clave, etiqueta, tipo)")
    L.append("INSERT INTO categorias (nombre_categoria, descripcion, id_categoria_padre, esquema_atributos)")
    L.append("SELECT v.nombre, v.descripcion, padre.id_categoria, v.esquema::jsonb")
    L.append("FROM (VALUES")
    filas = []
    for n, d, padre, esquema in SUBCATEGORIAS_NUEVAS:
        filas.append(f"    ({_sql(n)}, {_sql(d)}, {_sql(padre)}, {_sql(json.dumps(esquema, ensure_ascii=False))})")
    L.append(",\n".join(filas))
    L.append(") AS v(nombre, descripcion, nombre_padre, esquema)")
    L.append("JOIN categorias padre ON padre.nombre_categoria = v.nombre_padre")
    L.append("WHERE NOT EXISTS (SELECT 1 FROM categorias c WHERE c.nombre_categoria = v.nombre)")
    L.append("ON CONFLICT (nombre_categoria) DO NOTHING;\n")

    L.append("-- 3. Tiendas nuevas (usuarios con rol 'vendedor'), registradas hace entre 6 y 13 meses")
    L.append("INSERT INTO usuarios (nombre, email, password_hash, rol, telefono, fecha_registro)")
    L.append("SELECT v.nombre, v.email, v.password_hash, 'vendedor', v.telefono,")
    L.append("       CURRENT_TIMESTAMP - make_interval(days => v.dias)")
    L.append("FROM (VALUES")
    filas = []
    for i, (n, e, _) in enumerate(TIENDAS_NUEVAS, start=1):
        filas.append(f"    ({_sql(n)}, {_sql(e)}, {_sql(HASH_TIENDAYA123)}, '+5022331{i:04d}', {180 + (i * 5) % 220})")
    L.append(",\n".join(filas))
    L.append(") AS v(nombre, email, password_hash, telefono, dias)")
    L.append("WHERE NOT EXISTS (SELECT 1 FROM usuarios u WHERE u.email = v.email)")
    L.append("ON CONFLICT (email) DO NOTHING;\n")

    L.append("-- 4. Productos: se cargan en una tabla temporal y desde ahí se insertan productos + inventario")
    L.append("CREATE TEMP TABLE tmp_semilla_masiva (")
    L.append("    sku VARCHAR(60), email_vendedor VARCHAR(150), nombre_categoria VARCHAR(100), nombre VARCHAR(200),")
    L.append("    descripcion TEXT, precio_base NUMERIC(12, 2), stock INT, dias INT, minutos INT")
    L.append(") ON COMMIT DROP;\n")
    L.append("INSERT INTO tmp_semilla_masiva (sku, email_vendedor, nombre_categoria, nombre, descripcion, precio_base, stock, dias, minutos) VALUES")
    filas = []
    for p in productos:
        filas.append(f"({_sql(p['sku'])}, {_sql(p['email_vendedor'])}, {_sql(p['subcategoria'])}, {_sql(p['nombre'])}, "
                     f"{_sql(p['descripcion'])}, {p['precio']:.2f}, {p['stock']}, {p['dias']}, {p['minutos']})")
    L.append(",\n".join(filas) + ";\n")

    L.append("""INSERT INTO productos (id_vendedor, id_categoria, sku, nombre, descripcion, precio_base, activo, fecha_creacion)
SELECT u.id_usuario, c.id_categoria, t.sku, t.nombre, t.descripcion, t.precio_base, true,
       CURRENT_TIMESTAMP - make_interval(days => t.dias, mins => t.minutos)
FROM tmp_semilla_masiva t
JOIN usuarios u ON u.email = t.email_vendedor AND u.rol = 'vendedor'
JOIN categorias c ON c.nombre_categoria = t.nombre_categoria
WHERE NOT EXISTS (SELECT 1 FROM productos existente WHERE existente.sku = t.sku)
ORDER BY t.sku
ON CONFLICT (sku) DO NOTHING;

-- 5. Inventario inicial (stock > 0 para que todos los productos se puedan comprar)
INSERT INTO inventario (id_producto, stock_disponible, stock_reservado)
SELECT p.id_producto, t.stock, 0
FROM tmp_semilla_masiva t
JOIN productos p ON p.sku = t.sku
WHERE NOT EXISTS (SELECT 1 FROM inventario i WHERE i.id_producto = p.id_producto)
ON CONFLICT (id_producto) DO NOTHING;

COMMIT;
""")
    with open(RUTA_SQL, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


def escribir_json(productos):
    catalogo = OrderedDict()
    for p in productos:
        catalogo[p["sku"]] = {"atributos": p["atributos"], "imagenes": p["imagenes"]}
    with open(RUTA_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main():
    tiendas, productos = generar()
    skus = [p["sku"] for p in productos]
    assert len(set(skus)) == len(skus) == TOTAL_PRODUCTOS, "SKU duplicado"
    escribir_sql(productos)
    escribir_json(productos)

    por_tienda = Counter(p["email_vendedor"] for p in productos)
    personalizados = sum(1 for p in productos if len(p["atributos"]) > len(ESQUEMA_CLAVES[p["subcategoria"]]))
    imagenes = Counter(len(p["imagenes"]) for p in productos)
    print(f"[✓] {len(productos)} productos generados -> {os.path.relpath(RUTA_SQL, RAIZ)}")
    print(f"[✓] Atributos e imágenes por SKU -> {os.path.relpath(RUTA_JSON, RAIZ)}")
    print(f"[*] Tiendas con productos: {len(por_tienda)} | con atributos personalizados: {personalizados} "
          f"| imágenes por producto: {dict(sorted(imagenes.items()))}")
    print(f"[*] Tienda con más productos: {por_tienda.most_common(1)[0]}")


if __name__ == "__main__":
    main()
