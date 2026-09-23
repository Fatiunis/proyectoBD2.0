from flask import Blueprint, request, jsonify

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
