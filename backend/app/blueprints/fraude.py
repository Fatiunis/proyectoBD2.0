from flask import Blueprint, request, jsonify
from neo4j.exceptions import ServiceUnavailable, SessionExpired

from ..extensions import neo4j_driver

bp = Blueprint("fraude", __name__)

# ============================================================================
# MÓDULO DE DETECCIÓN DE FRAUDE EN RESEÑAS (NEO4J - ENTREGA 2)
# ============================================================================
# Detecta anillos de cuentas que se reseñan mutuamente de forma coordinada:
# tríos de cuentas (clique de 3 en el grafo Cuenta-CALIFICO->Producto) donde
# CADA PAR del trío comparte al menos `min_productos_compartidos` productos
# calificados con 5 estrellas por ambos lados, dentro de una ventana de tiempo
# corta entre sí. Combinar las tres señales (productos compartidos + 5
# estrellas mutuas + ventana temporal corta) es lo que evita falsos positivos
# del ruido legítimo disperso en 30 días: por azar es posible que dos cuentas
# no relacionadas compartan varios productos, pero es mucho más raro que
# además coincidan en calificación perfecta y en una ventana de pocas horas.
#
# `r.fecha` se guarda como STRING ISO 8601 (ver resenas.py / sembrar_resenas_
# fraude.py: se pasa `fecha.isoformat()`), no como tipo temporal nativo de
# Neo4j -- por eso la comparación de ventana convierte explícitamente con
# datetime(r.fecha) antes de usar duration.inSeconds(...).seconds.
#
# Un anillo de 4 cuentas mutuamente conectadas genera C(4,3) = 4 tríos
# distintos (todos superpuestos) -- es intencional que la consulta los
# devuelva todos, no es un bug de duplicación.

_QUERY_DETECCION_FRAUDE = """
    MATCH (a:Cuenta)-[r1:CALIFICO]->(p:Producto)<-[r2:CALIFICO]-(b:Cuenta)
    WHERE elementId(a) < elementId(b)
      AND r1.calificacion = 5 AND r2.calificacion = 5
      AND abs(duration.inSeconds(datetime(r1.fecha), datetime(r2.fecha)).seconds) <= $ventana_segundos
    WITH a, b, collect(DISTINCT p) AS productos_ab
    WHERE size(productos_ab) >= $min_productos_compartidos
    MATCH (b)-[r3:CALIFICO]->(p2:Producto)<-[r4:CALIFICO]-(c:Cuenta)
    WHERE elementId(b) < elementId(c) AND c <> a
      AND r3.calificacion = 5 AND r4.calificacion = 5
      AND abs(duration.inSeconds(datetime(r3.fecha), datetime(r4.fecha)).seconds) <= $ventana_segundos
    WITH a, b, c, productos_ab, collect(DISTINCT p2) AS productos_bc
    WHERE size(productos_bc) >= $min_productos_compartidos
    MATCH (a)-[r5:CALIFICO]->(p3:Producto)<-[r6:CALIFICO]-(c)
    WHERE r5.calificacion = 5 AND r6.calificacion = 5
      AND abs(duration.inSeconds(datetime(r5.fecha), datetime(r6.fecha)).seconds) <= $ventana_segundos
    WITH a, b, c, productos_ab, productos_bc, collect(DISTINCT p3) AS productos_ac
    WHERE size(productos_ac) >= $min_productos_compartidos
    RETURN
      [x IN [a, b, c] | {id_usuario: x.id_usuario, nombre: x.nombre}] AS cuentas_involucradas,
      [p IN productos_ab + productos_bc + productos_ac | p.id_producto] AS productos_compartidos,
      size(productos_ab) + size(productos_bc) + size(productos_ac) AS score_anomalia
    ORDER BY score_anomalia DESC
    LIMIT 20
"""

MIN_PRODUCTOS_COMPARTIDOS_DEFAULT = 3
VENTANA_SEGUNDOS_DEFAULT = 21600  # 6 horas


def _entero_o_default(valor, default):
    if valor is None:
        return default
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


@bp.route("/api/fraude/alertas", methods=["GET"])
def alertas_fraude():
    if request.args.get("rol_solicitante") != "administrador":
        return jsonify({"error": "Solo un administrador puede consultar alertas de fraude"}), 403

    min_productos_compartidos = _entero_o_default(
        request.args.get("min_productos_compartidos"), MIN_PRODUCTOS_COMPARTIDOS_DEFAULT
    )
    ventana_segundos = _entero_o_default(
        request.args.get("ventana_segundos"), VENTANA_SEGUNDOS_DEFAULT
    )

    if min_productos_compartidos is None or min_productos_compartidos < 1:
        return jsonify({"error": "min_productos_compartidos debe ser un entero positivo"}), 400
    if ventana_segundos is None or ventana_segundos < 1:
        return jsonify({"error": "ventana_segundos debe ser un entero positivo"}), 400

    try:
        with neo4j_driver.session() as session:
            resultado = session.run(
                _QUERY_DETECCION_FRAUDE,
                min_productos_compartidos=min_productos_compartidos,
                ventana_segundos=ventana_segundos,
            )
            alertas = [record.data() for record in resultado]

        return jsonify({
            "alertas": alertas,
            "total": len(alertas),
            "parametros": {
                "min_productos_compartidos": min_productos_compartidos,
                "ventana_segundos": ventana_segundos,
            },
        }), 200
    except Exception as e:
        return jsonify({"error": f"Error al consultar el grafo de fraude: {str(e)}"}), 500


# ============================================================================
# DETECCIÓN DE FRAUDE AMPLIADA (NEO4J) -- VARIOS PATRONES
# ============================================================================
# Además del anillo de la Entrega 2, se detectan patrones que usan el resto
# del grafo:
#   (:Cuenta)-[:CALIFICO {calificacion, fecha, compra_verificada}]->(:Producto)
#   (:Producto)-[:VENDIDO_POR]->(:Vendedor {id_vendedor, nombre})
#   (:Cuenta)-[:ENVIA_A]->(:Direccion {clave, ciudad, departamento})
# El grafo lo mantienen resenas.py y direcciones.py (mejor esfuerzo, vía
# app/grafo_fraude.py) y database/migrations/sincronizar_grafo_fraude.py
# (backfill idempotente).
#
# Convenciones comunes de todos los detectores nuevos:
# - "Sin compra" = NOT coalesce(r.compra_verificada, false). Una relación que
#   todavía no tiene la propiedad (reseña anterior al backfill) cuenta como
#   sin compra verificada: es lo único que se puede afirmar con lo que hay en
#   el grafo. Tras correr sincronizar_grafo_fraude.py todas la tienen.
# - Toda ventana de tiempo se mide con datetime(r.fecha): la fecha es un
#   string ISO (ver comentario de la consulta original).
# - Para buscar "N reseñas dentro de una ventana" se usa una ventana deslizante
#   anclada en cada reseña candidata: para cada reseña r0 se cuentan las que
#   caen en [r0.fecha, r0.fecha + ventana] y se queda la mejor ventana (la de
#   más reseñas). Toda ráfaga empieza en alguna reseña, así que no se pierde
#   ninguna.
# - Todos los valores llegan como parámetros de la consulta ($...): nunca se
#   interpola texto del usuario en el Cypher. (Lo único que se arma con
#   format() es el fragmento constante _SIN_COMPRA, al definir el módulo.)
# - El score (0-100) lo calcula cada detector en Python, a partir de los
#   números que devuelve la consulta, con la fórmula documentada en su
#   cabecera. nivel: alto >= 70, medio >= 40, bajo < 40.

MAX_ALERTAS_POR_TIPO = 50
# Tope de filas que se piden a Neo4j por detector, antes de calcular el score
# en Python y quedarse con las 50 mejores. Con el volumen del curso nunca se
# alcanza; evita traer resultados enormes si el grafo crece.
_LIMITE_CANDIDATOS = 500

_SIN_COMPRA = "NOT coalesce({r}.compra_verificada, false)"


def _nivel(score):
    if score >= 70:
        return "alto"
    if score >= 40:
        return "medio"
    return "bajo"


def _acotar(valor):
    return max(0, min(100, int(round(valor))))


def _alerta(tipo, *, cuentas, productos, vendedor, score, motivo, evidencia):
    score = _acotar(score)
    return {
        "tipo": tipo,
        "cuentas": cuentas,
        "productos": productos,
        "vendedor": vendedor,
        "score": score,
        "nivel": _nivel(score),
        "motivo": motivo,
        "evidencia": evidencia,
    }


def _vendedor_o_none(id_vendedor, nombre):
    if id_vendedor is None:
        return None
    return {"id_vendedor": id_vendedor, "nombre": nombre}


def _minutos(segundos):
    return round((segundos or 0) / 60, 1)


# ----------------------------------------------------------------------------
# 1) cuenta_rafaga
# ----------------------------------------------------------------------------
# Patrón: UNA cuenta con >= min_resenas reseñas (de cualquier calificación)
# dentro de ventana_segundos, de las cuales al menos min_pct_sin_compra % son
# sin compra verificada.
# Por qué es anómalo: una persona real reseña de a poco lo que va recibiendo;
# muchas reseñas de productos distintos en minutos, casi todas de cosas que
# nunca compró, es una cuenta automatizada o una "granja" de reseñas. Se mira
# cualquier calificación porque estas cuentas suelen variar las estrellas
# justamente para no parecer sospechosas.
# Cálculo: ventana deslizante por cuenta (ver convenciones); se queda por
# cuenta la ventana con más reseñas que cumple el porcentaje.
# Score: 50 + 5 por cada reseña sobre el mínimo + 30 * (1 - duración real /
# ventana) + 20 * (lo que el % sin compra supera al mínimo, sobre lo que le
# faltaba para llegar a 100).
# Defaults (5 reseñas, 1 h, 80 %): el ruido legítimo reparte las reseñas de
# cada cuenta en 30 días y los anillos de la semilla original hacen 4 por
# cuenta en ~2 h, así que ninguno llega a 5 en una hora. Bajando a 4 reseñas
# en 6 h ya aparecen las cuentas del anillo de la Entrega 2, y con 3 en 1 h
# aparece casi cualquier cuenta de un grupo (eso ya lo cubre grupo_coordinado).

_QUERY_CUENTA_RAFAGA = f"""
    MATCH (c:Cuenta)-[r0:CALIFICO]->(:Producto)
    WITH DISTINCT c, datetime(r0.fecha) AS inicio
    MATCH (c)-[r:CALIFICO]->(p:Producto)
    WHERE datetime(r.fecha) >= inicio
      AND datetime(r.fecha) <= inicio + duration({{seconds: $ventana_segundos}})
    WITH c, inicio, p, r
    ORDER BY datetime(r.fecha)
    WITH c, inicio,
         collect({{id_producto: p.id_producto, nombre: p.nombre, calificacion: r.calificacion}}) AS resenas,
         sum(CASE WHEN {_SIN_COMPRA.format(r="r")} THEN 1 ELSE 0 END) AS sin_compra,
         max(datetime(r.fecha)) AS fin
    WHERE size(resenas) >= $min_resenas
      AND 100.0 * sin_compra / size(resenas) >= $min_pct_sin_compra
    WITH c, inicio, resenas, sin_compra, duration.inSeconds(inicio, fin).seconds AS segundos_span
    ORDER BY size(resenas) DESC, segundos_span ASC, inicio ASC
    WITH c, collect({{resenas: resenas, sin_compra: sin_compra, segundos_span: segundos_span,
                     inicio: toString(inicio)}})[0] AS mejor
    RETURN c.id_usuario AS id_usuario, c.nombre AS nombre, mejor
    ORDER BY size(mejor.resenas) DESC, id_usuario ASC
    LIMIT $limite
"""


def _detectar_cuenta_rafaga(session, min_resenas, ventana_segundos, min_pct_sin_compra):
    filas = session.run(
        _QUERY_CUENTA_RAFAGA,
        min_resenas=min_resenas,
        ventana_segundos=ventana_segundos,
        min_pct_sin_compra=min_pct_sin_compra,
        limite=_LIMITE_CANDIDATOS,
    ).data()
    alertas = []
    for f in filas:
        mejor = f["mejor"]
        resenas = mejor["resenas"]
        n = len(resenas)
        span = mejor["segundos_span"] or 0
        pct = 100 * mejor["sin_compra"] / n
        margen = 1.0 if min_pct_sin_compra >= 100 else (pct - min_pct_sin_compra) / (100 - min_pct_sin_compra)
        score = (50 + 5 * (n - min_resenas) + 30 * max(0.0, 1 - span / ventana_segundos)
                 + 20 * max(0.0, margen))
        distribucion = {str(k): 0 for k in range(1, 6)}
        productos, vistos = [], set()
        for r in resenas:
            distribucion[str(r["calificacion"])] = distribucion.get(str(r["calificacion"]), 0) + 1
            if r["id_producto"] not in vistos:
                vistos.add(r["id_producto"])
                productos.append({"id_producto": r["id_producto"], "nombre": r["nombre"]})
        alertas.append(_alerta(
            "cuenta_rafaga",
            cuentas=[{"id_usuario": f["id_usuario"], "nombre": f["nombre"]}],
            productos=productos,
            vendedor=None,
            score=score,
            motivo=(
                f"{f['nombre']} publicó {n} reseñas en {_minutos(span)} minutos y el {round(pct)}% fueron de "
                f"productos que no compró (umbral: {min_resenas} reseñas en {_minutos(ventana_segundos)} minutos "
                f"con al menos {min_pct_sin_compra}% sin compra)."
            ),
            evidencia={
                "resenas": n,
                "resenas_sin_compra": mejor["sin_compra"],
                "sin_compra_pct": round(pct),
                "distribucion_calificaciones": distribucion,
                "inicio": mejor["inicio"],
                "ventana_real_minutos": _minutos(span),
                "ventana_maxima_minutos": _minutos(ventana_segundos),
            },
        ))
    return alertas


# ----------------------------------------------------------------------------
# 2) grupo_coordinado
# ----------------------------------------------------------------------------
# Patrón: un grupo de >= min_cuentas cuentas (de cualquier tamaño: 3, 5, 10...)
# conectadas entre sí. Dos cuentas quedan ENLAZADAS si calificaron >=
# min_productos_compartidos productos en común con el mismo signo extremo
# (ambas 5 estrellas o ambas 1-2) y con sus dos reseñas de cada producto a <=
# ventana_segundos entre sí. El grupo es la componente conexa de esos enlaces:
# A-B y B-C forman el grupo {A, B, C} aunque A y C no coincidan directamente.
# Positivo y negativo se calculan por separado (son alertas distintas).
# Por qué es anómalo: generaliza el anillo de la Entrega 2 (tríos fijos de 5
# estrellas) a grupos de cualquier tamaño y también a campañas negativas. Que
# varias cuentas opinen lo mismo, en extremo, sobre los mismos productos y
# casi a la misma hora es una acción concertada, no opiniones independientes.
# Cálculo: Cypher devuelve los pares enlazados (la parte de grafo); las
# componentes conexas se arman en Python con union-find (sencillo y sin
# depender del plugin GDS de Neo4j, que el docker del curso no trae).
# Score: 40 + 10 por cada cuenta sobre el mínimo + 30 * densidad + 20 *
# proporción sin compra. densidad = enlaces / pares posibles del grupo (1 =
# todos coinciden con todos; una cadena A-B-C tiene 2/3). Un grupo del tamaño
# mínimo, todos enlazados y sin compras, da 90.
# Defaults (3 cuentas, 2 productos, 6 h): 2 productos alcanzan para ver grupos
# que el anillo original (que pide 3 por par) no ve; exigir 3 cuentas evita
# marcar parejas sueltas (para parejas está cuentas_vinculadas, que además
# pide la misma dirección). La ventana es la misma del anillo original.

_QUERY_ENLACES_GRUPO = f"""
    MATCH (a:Cuenta)-[r1:CALIFICO]->(p:Producto)<-[r2:CALIFICO]-(b:Cuenta)
    WHERE a.id_usuario < b.id_usuario
      AND ((r1.calificacion = 5 AND r2.calificacion = 5)
           OR (r1.calificacion <= 2 AND r2.calificacion <= 2))
    WITH a, b, p, r1, r2,
         CASE WHEN r1.calificacion = 5 THEN 'positivo' ELSE 'negativo' END AS signo,
         abs(duration.inSeconds(datetime(r1.fecha), datetime(r2.fecha)).seconds) AS diferencia
    WHERE diferencia <= $ventana_segundos
    WITH a, b, signo, p, diferencia,
         (CASE WHEN {_SIN_COMPRA.format(r="r1")} THEN 1 ELSE 0 END)
         + (CASE WHEN {_SIN_COMPRA.format(r="r2")} THEN 1 ELSE 0 END) AS sin_compra
    ORDER BY p.id_producto
    WITH a, b, signo,
         collect({{id_producto: p.id_producto, nombre: p.nombre}}) AS productos,
         max(diferencia) AS diferencia_max,
         sum(sin_compra) AS sin_compra
    WHERE size(productos) >= $min_productos_compartidos
    RETURN a.id_usuario AS id_a, a.nombre AS nombre_a, b.id_usuario AS id_b, b.nombre AS nombre_b,
           signo, productos, diferencia_max, sin_compra
    ORDER BY id_a, id_b
    LIMIT $limite
"""


def _componentes(enlaces):
    """Union-find sobre los pares (id_a, id_b): devuelve los conjuntos conexos."""
    padre = {}

    def raiz(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for f in enlaces:
        padre.setdefault(f["id_a"], f["id_a"])
        padre.setdefault(f["id_b"], f["id_b"])
        ra, rb = raiz(f["id_a"]), raiz(f["id_b"])
        if ra != rb:
            padre[max(ra, rb)] = min(ra, rb)

    grupos = {}
    for x in padre:
        grupos.setdefault(raiz(x), set()).add(x)
    return list(grupos.values())


def _detectar_grupo_coordinado(session, min_cuentas, min_productos_compartidos, ventana_segundos):
    filas = session.run(
        _QUERY_ENLACES_GRUPO,
        min_productos_compartidos=min_productos_compartidos,
        ventana_segundos=ventana_segundos,
        limite=_LIMITE_CANDIDATOS * 10,
    ).data()

    alertas = []
    for signo in ("positivo", "negativo"):
        enlaces = [f for f in filas if f["signo"] == signo]
        nombres = {}
        for f in enlaces:
            nombres[f["id_a"]] = f["nombre_a"]
            nombres[f["id_b"]] = f["nombre_b"]

        for miembros in _componentes(enlaces):
            if len(miembros) < min_cuentas:
                continue
            propios = [f for f in enlaces if f["id_a"] in miembros]
            productos, vistos = [], set()
            for f in propios:
                for p in f["productos"]:
                    if p["id_producto"] not in vistos:
                        vistos.add(p["id_producto"])
                        productos.append(p)
            tam = len(miembros)
            posibles = tam * (tam - 1) // 2
            densidad = len(propios) / posibles if posibles else 0
            resenas_enlace = sum(2 * len(f["productos"]) for f in propios)
            prop_sin_compra = sum(f["sin_compra"] for f in propios) / resenas_enlace if resenas_enlace else 0
            ventana_real = max(f["diferencia_max"] for f in propios)
            score = 40 + 10 * (tam - min_cuentas) + 30 * densidad + 20 * prop_sin_compra
            texto_signo = "5 estrellas" if signo == "positivo" else "1-2 estrellas"
            alertas.append(_alerta(
                "grupo_coordinado",
                cuentas=[{"id_usuario": i, "nombre": nombres[i]} for i in sorted(miembros)],
                productos=sorted(productos, key=lambda p: p["id_producto"]),
                vendedor=None,
                score=score,
                motivo=(
                    f"Grupo de {tam} cuentas que dieron {texto_signo} a los mismos productos casi a la vez: "
                    f"{len(propios)} de {posibles} parejas posibles coinciden en al menos "
                    f"{min_productos_compartidos} productos, con a lo sumo {_minutos(ventana_real)} minutos "
                    f"entre reseñas."
                ),
                evidencia={
                    "tamano": tam,
                    "signo": signo,
                    "enlaces": len(propios),
                    "densidad_pct": round(densidad * 100),
                    "productos_en_comun": len(productos),
                    "pares": [
                        {"cuentas": [f["id_a"], f["id_b"]], "productos_en_comun": len(f["productos"])}
                        for f in propios
                    ],
                    "resenas_sin_compra_pct": round(prop_sin_compra * 100),
                    "ventana_real_minutos": _minutos(ventana_real),
                    "ventana_maxima_minutos": _minutos(ventana_segundos),
                },
            ))
    return alertas


# ----------------------------------------------------------------------------
# 3) sesgo_vendedor_sin_compra
# ----------------------------------------------------------------------------
# Patrón: una cuenta con >= min_resenas reseñas SIN compra verificada a
# productos de UN MISMO vendedor, todas del mismo signo extremo: todas de 5
# estrellas (promotor) o todas de 1-2 estrellas (detractor). Cada signo se
# cuenta por separado (evidencia.signo = "positivo" / "negativo"): una cuenta
# puede ser promotora de una tienda y detractora de otra, y son dos alertas.
# Por qué es anómalo: un comprador real reseña lo que compró y reparte sus
# opiniones entre tiendas; varias calificaciones extremas a la misma tienda sin
# haberle comprado nada es el perfil de una cuenta pagada para inflar (o
# hundir) la reputación de ese vendedor.
# Score: 40 + 10 por cada reseña sobre el mínimo + 40 * concentración, donde
# concentración = (reseñas extremas sin compra a ese vendedor) / (todas las
# reseñas de la cuenta). Justo en el umbral, con una cuenta que además reseña
# otras cosas, queda en "medio"; una cuenta dedicada casi solo a ese vendedor,
# o con muchas reseñas de más, sube a "alto".
# Default min_resenas = 3: verificado con la semilla. Con 2 ya aparecen los
# controles (`promotor_control`, `detractor_control`: 2 reseñas extremas a una
# tienda), cuentas de otros escenarios que no son de este patrón y cuentas
# del ruido legítimo que por azar dieron 5 (o 2) estrellas a 2 productos de la
# misma tienda (las tiendas grandes concentran reseñas); con 3 solo quedan los
# escenarios `promotor` y `detractor` y las 4 cuentas del anillo fuerte de la
# Entrega 2 (que también son promotoras sin compra de ese vendedor: es
# esperado, no un falso positivo).

_QUERY_SESGO_VENDEDOR = f"""
    MATCH (c:Cuenta)-[r:CALIFICO]->(p:Producto)-[:VENDIDO_POR]->(v:Vendedor)
    WHERE (r.calificacion = 5 OR r.calificacion <= 2) AND {_SIN_COMPRA.format(r="r")}
    WITH c, v, p, r, CASE WHEN r.calificacion = 5 THEN 'positivo' ELSE 'negativo' END AS signo
    ORDER BY p.id_producto
    WITH c, v, signo,
         collect({{id_producto: p.id_producto, nombre: p.nombre}}) AS productos,
         collect(r.calificacion) AS calificaciones,
         min(datetime(r.fecha)) AS desde, max(datetime(r.fecha)) AS hasta
    WHERE size(productos) >= $min_resenas
    MATCH (c)-[rt:CALIFICO]->(:Producto)
    WITH c, v, signo, productos, calificaciones, desde, hasta, count(rt) AS total_cuenta
    OPTIONAL MATCH (c)-[rv:CALIFICO]->(:Producto)-[:VENDIDO_POR]->(v)
    WITH c, v, signo, productos, calificaciones, desde, hasta, total_cuenta, count(rv) AS total_vendedor
    RETURN c.id_usuario AS id_usuario, c.nombre AS nombre, signo,
           v.id_vendedor AS id_vendedor, v.nombre AS nombre_vendedor,
           productos, calificaciones, total_cuenta, total_vendedor,
           duration.inSeconds(desde, hasta).seconds AS segundos_span
    ORDER BY size(productos) DESC, id_usuario ASC
    LIMIT $limite
"""


def _detectar_sesgo_vendedor_sin_compra(session, min_resenas):
    filas = session.run(_QUERY_SESGO_VENDEDOR, min_resenas=min_resenas, limite=_LIMITE_CANDIDATOS).data()
    alertas = []
    for f in filas:
        n = len(f["productos"])
        concentracion = n / f["total_cuenta"] if f["total_cuenta"] else 0
        score = 40 + 10 * (n - min_resenas) + 40 * concentracion
        positivo = f["signo"] == "positivo"
        alertas.append(_alerta(
            "sesgo_vendedor_sin_compra",
            cuentas=[{"id_usuario": f["id_usuario"], "nombre": f["nombre"]}],
            productos=f["productos"],
            vendedor=_vendedor_o_none(f["id_vendedor"], f["nombre_vendedor"]),
            score=score,
            motivo=(
                f"{f['nombre']} dio {'5 estrellas' if positivo else '1-2 estrellas'} a {n} productos de "
                f"{f['nombre_vendedor']} sin haberle comprado ninguno (umbral: {min_resenas}); "
                f"son el {round(concentracion * 100)}% de todas sus reseñas."
            ),
            evidencia={
                "signo": f["signo"],
                "resenas_extremas_sin_compra": n,
                "calificaciones": f["calificaciones"],
                "resenas_al_vendedor": f["total_vendedor"],
                "resenas_totales_cuenta": f["total_cuenta"],
                "concentracion_pct": round(concentracion * 100),
                # El tiempo no es parte de este patrón (una cuenta así puede ir
                # despacio); se informa el período que cubren sus reseñas.
                "periodo_dias": round((f["segundos_span"] or 0) / 86400, 1),
            },
        ))
    return alertas


# ----------------------------------------------------------------------------
# 4) cuentas_vinculadas
# ----------------------------------------------------------------------------
# Patrón: >= 2 cuentas que envían a la MISMA dirección (mismo nodo
# :Direccion, clave normalizada) y que calificaron >= min_productos_
# compartidos productos en común con la MISMA calificación (cualquiera: dos
# cuentas que coinciden en 1 estrella son tan sospechosas como dos que
# coinciden en 5).
# Por qué es anómalo: compartir dirección es normal (una familia) y por sí
# solo no se marca; lo sospechoso es que además opinen igual sobre los mismos
# productos: muy probablemente es la misma persona con varias cuentas. A
# diferencia del anillo de la Entrega 2, NO exige ventana de tiempo ni 5 estrellas: el
# vínculo físico reemplaza a la coincidencia temporal, así que detecta
# cuentas falsas que reseñan espaciadas para no levantar sospechas.
# Cálculo: se buscan los pares de cuentas de cada dirección con suficientes
# coincidencias y se agrupan en una alerta por dirección.
# Score: 50 + 10 por cada coincidencia sobre el mínimo (en el par con más) +
# 10 por cada cuenta vinculada además de 2 + 20 * proporción de esas
# reseñas coincidentes que son sin compra.

_QUERY_VINCULADAS = """
    MATCH (a:Cuenta)-[:ENVIA_A]->(d:Direccion)<-[:ENVIA_A]-(b:Cuenta)
    WHERE a.id_usuario < b.id_usuario
    MATCH (a)-[r1:CALIFICO]->(p:Producto)<-[r2:CALIFICO]-(b)
    WHERE r1.calificacion = r2.calificacion
    WITH d, a, b, p, r1, r2
    ORDER BY p.id_producto
    WITH d, a, b,
         collect({id_producto: p.id_producto, nombre: p.nombre, calificacion: r1.calificacion}) AS comunes,
         sum((CASE WHEN coalesce(r1.compra_verificada, false) THEN 0 ELSE 1 END)
             + (CASE WHEN coalesce(r2.compra_verificada, false) THEN 0 ELSE 1 END)) AS sin_compra
    WHERE size(comunes) >= $min_productos_compartidos
    WITH d, a, b, comunes, sin_compra
    ORDER BY a.id_usuario, b.id_usuario
    WITH d, collect({a: {id_usuario: a.id_usuario, nombre: a.nombre},
                     b: {id_usuario: b.id_usuario, nombre: b.nombre},
                     comunes: comunes, sin_compra: sin_compra}) AS pares
    RETURN d.clave AS clave, d.ciudad AS ciudad, d.departamento AS departamento, pares
    ORDER BY size(pares) DESC
    LIMIT $limite
"""


def _detectar_cuentas_vinculadas(session, min_productos_compartidos):
    filas = session.run(
        _QUERY_VINCULADAS, min_productos_compartidos=min_productos_compartidos, limite=_LIMITE_CANDIDATOS,
    ).data()
    alertas = []
    for f in filas:
        cuentas, productos, vistos_p, calificaciones, evid_pares = {}, [], set(), [], []
        max_comunes, total_resenas, sin_compra = 0, 0, 0
        for par in f["pares"]:
            cuentas[par["a"]["id_usuario"]] = par["a"]
            cuentas[par["b"]["id_usuario"]] = par["b"]
            max_comunes = max(max_comunes, len(par["comunes"]))
            total_resenas += 2 * len(par["comunes"])
            sin_compra += par["sin_compra"]
            evid_pares.append({
                "cuentas": [par["a"]["id_usuario"], par["b"]["id_usuario"]],
                "productos_en_comun": len(par["comunes"]),
            })
            for prod in par["comunes"]:
                calificaciones.append(prod["calificacion"])
                if prod["id_producto"] not in vistos_p:
                    vistos_p.add(prod["id_producto"])
                    productos.append({"id_producto": prod["id_producto"], "nombre": prod["nombre"]})
        cuentas_l = [cuentas[k] for k in sorted(cuentas)]
        prop_sin_compra = sin_compra / total_resenas if total_resenas else 0
        score = (50 + 10 * (max_comunes - min_productos_compartidos)
                 + 10 * (len(cuentas_l) - 2) + 20 * prop_sin_compra)
        lugar = ", ".join(x for x in (f["ciudad"], f["departamento"]) if x)
        alertas.append(_alerta(
            "cuentas_vinculadas",
            cuentas=cuentas_l,
            productos=productos,
            vendedor=None,
            score=score,
            motivo=(
                f"{len(cuentas_l)} cuentas envían a la misma dirección ({lugar}) y calificaron igual "
                f"hasta {max_comunes} productos en común (umbral: {min_productos_compartidos})."
            ),
            evidencia={
                "ciudad": f["ciudad"],
                "departamento": f["departamento"],
                "cuentas_en_direccion": len(cuentas_l),
                "pares": evid_pares,
                "max_productos_en_comun": max_comunes,
                "calificaciones_coincidentes": sorted(set(calificaciones)),
                "resenas_sin_compra_pct": round(prop_sin_compra * 100),
            },
        ))
    return alertas


# ----------------------------------------------------------------------------
# Catálogo de patrones (el orden es el de las pestañas del panel)
# ----------------------------------------------------------------------------
PATRONES = {
    "cuenta_rafaga": {
        "nombre": "Cuenta en ráfaga",
        "descripcion": (
            "Una sola cuenta que publica muchas reseñas en muy poco tiempo, casi todas "
            "de productos que nunca compró."
        ),
        "parametros": {"min_resenas": 5, "ventana_segundos": 3600, "min_pct_sin_compra": 80},
        "detector": _detectar_cuenta_rafaga,
    },
    "grupo_coordinado": {
        "nombre": "Grupo coordinado",
        "descripcion": (
            "Varias cuentas que califican igual los mismos productos casi al mismo "
            "tiempo, ya sea para subirles la nota (5 estrellas) o para hundirlos (1-2 estrellas)."
        ),
        "parametros": {"min_cuentas": 3, "min_productos_compartidos": 2, "ventana_segundos": 21600},
        "detector": _detectar_grupo_coordinado,
    },
    "sesgo_vendedor_sin_compra": {
        "nombre": "Cuenta sesgada hacia un vendedor",
        "descripcion": (
            "Una cuenta que califica varios productos de la misma tienda sin haberle "
            "comprado nada, siempre con 5 estrellas (para inflarla) o siempre con 1-2 "
            "(para hundirla)."
        ),
        "parametros": {"min_resenas": 3},
        "detector": _detectar_sesgo_vendedor_sin_compra,
    },
    "cuentas_vinculadas": {
        "nombre": "Cuentas vinculadas",
        "descripcion": (
            "Cuentas que envían a la misma dirección y califican igual los mismos "
            "productos: probablemente una sola persona con varias cuentas."
        ),
        "parametros": {"min_productos_compartidos": 2},
        "detector": _detectar_cuentas_vinculadas,
    },
}

# Topes de parámetros que no son "cualquier entero positivo" (un porcentaje).
_MAXIMOS_PARAMETRO = {"min_pct_sin_compra": 100}


def _es_admin():
    return request.args.get("rol_solicitante") == "administrador"


def _error_403():
    return jsonify({"error": "Solo un administrador puede consultar alertas de fraude"}), 403


def _error_grafo(e):
    if isinstance(e, (ServiceUnavailable, SessionExpired, ConnectionError)):
        return jsonify({
            "error": "El grafo de fraude (Neo4j) no está disponible en este momento",
            "codigo": "GRAFO_NO_DISPONIBLE",
        }), 503
    return jsonify({"error": f"Error al consultar el grafo de fraude: {str(e)}"}), 500


def _ejecutar(session, tipo, parametros):
    alertas = PATRONES[tipo]["detector"](session, **parametros)
    alertas.sort(key=lambda a: (-a["score"], [c["id_usuario"] for c in a["cuentas"]]))
    return alertas


@bp.route("/api/fraude/patrones", methods=["GET"])
def patrones_fraude():
    if not _es_admin():
        return _error_403()
    return jsonify({
        "patrones": [
            {
                "tipo": tipo,
                "nombre": p["nombre"],
                "descripcion": p["descripcion"],
                "parametros": dict(p["parametros"]),
            }
            for tipo, p in PATRONES.items()
        ]
    }), 200


@bp.route("/api/fraude/alertas/<tipo>", methods=["GET"])
def alertas_por_patron(tipo):
    if not _es_admin():
        return _error_403()
    if tipo not in PATRONES:
        return jsonify({"error": f"Patrón de fraude desconocido: '{tipo}'"}), 404

    parametros = {}
    for nombre, default in PATRONES[tipo]["parametros"].items():
        crudo = request.args.get(nombre)
        if crudo is None or crudo.strip() == "":
            parametros[nombre] = default
            continue
        try:
            valor = int(crudo)
        except (TypeError, ValueError):
            valor = None
        if valor is None or valor < 1:
            return jsonify({"error": f"{nombre} debe ser un entero positivo"}), 400
        maximo = _MAXIMOS_PARAMETRO.get(nombre)
        if maximo is not None and valor > maximo:
            return jsonify({"error": f"{nombre} debe ser un entero entre 1 y {maximo}"}), 400
        parametros[nombre] = valor

    try:
        with neo4j_driver.session() as session:
            alertas = _ejecutar(session, tipo, parametros)
    except Exception as e:
        return _error_grafo(e)

    # total = alertas detectadas; la lista se corta en MAX_ALERTAS_POR_TIPO.
    return jsonify({
        "tipo": tipo,
        "alertas": alertas[:MAX_ALERTAS_POR_TIPO],
        "total": len(alertas),
        "parametros": parametros,
    }), 200


# Resumen por cuenta: corre los 4 detectores con sus defaults y agrega por
# cuenta. score_total combina las alertas de la cuenta en la misma escala
# 0-100 que una alerta (para poder darle `nivel`): el score de su peor alerta
# + 10 por cada patrón distinto adicional en el que aparece (hasta +30 si cae
# en los 4), con tope 100. Aparecer en varios patrones independientes es más
# grave que aparecer varias veces en el mismo (p.ej. una cuenta promotora de
# dos tiendas tiene 2 alertas de sesgo, pero un solo patrón).
@bp.route("/api/fraude/resumen", methods=["GET"])
def resumen_fraude():
    if not _es_admin():
        return _error_403()

    por_tipo = {}
    cuentas = {}
    total_alertas = 0
    try:
        with neo4j_driver.session() as session:
            for tipo, patron in PATRONES.items():
                alertas = _ejecutar(session, tipo, dict(patron["parametros"]))
                por_tipo[tipo] = len(alertas)
                total_alertas += len(alertas)
                for alerta in alertas:
                    for c in alerta["cuentas"]:
                        info = cuentas.setdefault(c["id_usuario"], {
                            "id_usuario": c["id_usuario"],
                            "nombre": c.get("nombre"),
                            "patrones": [],
                            "alertas": 0,
                            "_max": 0,
                        })
                        info["alertas"] += 1
                        info["_max"] = max(info["_max"], alerta["score"])
                        if tipo not in info["patrones"]:
                            info["patrones"].append(tipo)
    except Exception as e:
        return _error_grafo(e)

    cuentas_riesgo = []
    for info in cuentas.values():
        score_total = _acotar(info.pop("_max") + 10 * (len(info["patrones"]) - 1))
        info["score_total"] = score_total
        info["nivel"] = _nivel(score_total)
        cuentas_riesgo.append(info)
    cuentas_riesgo.sort(key=lambda c: (-c["score_total"], -c["alertas"], c["id_usuario"]))

    return jsonify({
        "por_tipo": por_tipo,
        "total_alertas": total_alertas,
        "cuentas_riesgo": cuentas_riesgo[:MAX_ALERTAS_POR_TIPO],
    }), 200
