"""
Prueba de concurrencia para la oferta relámpago con reserva temporal.

Standalone: NO es parte de la app Flask, se corre manualmente contra un
servidor real ya levantado (python backend/main.py, escuchando en
http://127.0.0.1:8000) con Redis y Mongo disponibles.

Mecánica que se prueba: reservar NO descuenta el cupo, aparta unidades por
RESERVA_OFERTA_TTL_SEGUNDOS y agrega una línea "oferta:{pid}" al carrito. La
disponibilidad es cupo_sin_vender - reservas activas, y se comprueba y aparta
dentro de un único script Lua atómico.

Dispara 50 reservas concurrentes de 1 unidad (50 compradores distintos)
contra una oferta con límite 10 y verifica:
  - exactamente 10 éxitos (201) y 40 rechazos 409 "Stock insuficiente";
  - stock_restante == 0 y unidades_reservadas == 10 (sin sobreventa);
  - unidades_vendidas == 0 (reservar no es vender).
Después vacía los carritos de los 10 ganadores (lo que libera sus reservas)
y verifica que stock_restante vuelva a 10.

Compradores: usa ids ficticios (ID_COMPRADOR_BASE + 1 .. + 50) para no tocar
carritos reales; el endpoint de reserva no exige que el usuario exista en
Postgres. Sus carritos (carrito:{id}) se vacían al final.

Usa un producto REAL del catálogo de Mongo (por defecto PROD-0001), porque
POST/DELETE /api/ofertas validan que el producto exista y que el solicitante
sea su dueño o un administrador. La oferta se crea como administrador (id 1)
con un precio 10 % menor que el precio_base. Si ya hay una oferta activa en
ese producto, el script aborta sin tocarla (para no pisar una oferta real);
cambia PRODUCTO_ID o finalízala a mano.

Uso:
    venv\\Scripts\\python.exe backend/scripts/prueba_concurrencia_oferta.py
"""

import concurrent.futures

import requests

BASE_URL = "http://127.0.0.1:8000"
PRODUCTO_ID = "PROD-0001"
ROL_ADMIN = "administrador"
ID_USUARIO_ADMIN = 1
ID_COMPRADOR_BASE = 990000
LIMITE_OFERTA = 10
DURACION_MINUTOS = 5
TOTAL_REQUESTS = 50
MAX_WORKERS = 20


def limpiar_oferta():
    try:
        resp = requests.delete(
            f"{BASE_URL}/api/ofertas/{PRODUCTO_ID}",
            params={"rol_solicitante": ROL_ADMIN, "id_usuario": ID_USUARIO_ADMIN},
            timeout=5,
        )
        if resp.status_code != 200:
            print(f"       ADVERTENCIA: no se pudo finalizar la oferta "
                  f"({resp.status_code} {resp.text})")
    except requests.RequestException as e:
        print(f"       ADVERTENCIA: no se pudo finalizar la oferta: {e}")


def vaciar_carrito(id_usuario):
    try:
        requests.delete(f"{BASE_URL}/api/carrito/{id_usuario}", timeout=5)
    except requests.RequestException as e:
        print(f"       ADVERTENCIA: no se pudo vaciar carrito:{id_usuario}: {e}")


def verificar_sin_oferta_activa():
    # No se "limpia" una oferta previa a ciegas: PRODUCTO_ID es un producto
    # real y podría tener una oferta legítima creada por su vendedor.
    resp = requests.get(f"{BASE_URL}/api/ofertas/{PRODUCTO_ID}", timeout=5)
    if resp.status_code == 200:
        raise SystemExit(
            f"ABORTADO: ya hay una oferta activa en {PRODUCTO_ID} ({resp.json()}). "
            f"No se toca para no pisar una oferta real. Finalízala o cambia "
            f"PRODUCTO_ID en este script."
        )
    if resp.status_code != 404:
        raise SystemExit(f"ABORTADO: respuesta inesperada al consultar la oferta: "
                         f"{resp.status_code} {resp.text}")


def calcular_precio_oferta():
    resp = requests.get(f"{BASE_URL}/api/productos/{PRODUCTO_ID}", timeout=5)
    if resp.status_code != 200:
        raise SystemExit(f"ABORTADO: no se pudo leer {PRODUCTO_ID}: {resp.status_code} {resp.text}")
    precio_base = resp.json().get("precio_base")
    if not precio_base or precio_base <= 0.01:
        raise SystemExit(f"ABORTADO: {PRODUCTO_ID} no tiene un precio_base utilizable ({precio_base})")
    return round(precio_base * 0.9, 2)


def crear_oferta(precio_oferta):
    resp = requests.post(
        f"{BASE_URL}/api/ofertas",
        json={
            "producto_id": PRODUCTO_ID,
            "cantidad_limite": LIMITE_OFERTA,
            "duracion_minutos": DURACION_MINUTOS,
            "precio_oferta": precio_oferta,
            "rol_solicitante": ROL_ADMIN,
            "id_usuario": ID_USUARIO_ADMIN,
        },
        timeout=5,
    )
    if resp.status_code != 201:
        raise RuntimeError(f"No se pudo crear la oferta de prueba: {resp.status_code} {resp.text}")
    print(f"       Oferta creada: {resp.json()}")


def reservar_una_unidad(id_usuario):
    try:
        resp = requests.post(
            f"{BASE_URL}/api/ofertas/{PRODUCTO_ID}/reservar",
            json={"id_usuario": id_usuario, "cantidad": 1, "rol_solicitante": "comprador"},
            timeout=10,
        )
        return id_usuario, resp.status_code, resp.json()
    except (requests.RequestException, ValueError) as e:
        return id_usuario, None, {"error": str(e)}


def leer_oferta():
    resp = requests.get(f"{BASE_URL}/api/ofertas/{PRODUCTO_ID}", timeout=5)
    if resp.status_code != 200:
        print(f"       ADVERTENCIA: no se pudo leer la oferta ({resp.status_code} {resp.text})")
        return {}
    return resp.json()


def main():
    print("=" * 70)
    print("PRUEBA DE CONCURRENCIA - OFERTA RELÁMPAGO CON RESERVA TEMPORAL")
    print("=" * 70)

    print(f"\n[1/6] Verificando que {PRODUCTO_ID} no tenga una oferta activa...")
    verificar_sin_oferta_activa()

    precio_oferta = calcular_precio_oferta()
    print(f"[2/6] Creando oferta con límite {LIMITE_OFERTA}, precio {precio_oferta} "
          f"y duración {DURACION_MINUTOS} min...")
    crear_oferta(precio_oferta)

    compradores = [ID_COMPRADOR_BASE + i for i in range(1, TOTAL_REQUESTS + 1)]
    ganadores = []
    try:
        print(f"[3/6] Disparando {TOTAL_REQUESTS} reservas concurrentes "
              f"(1 unidad c/u, {MAX_WORKERS} workers)...")
        resultados = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futuros = [executor.submit(reservar_una_unidad, id_usuario) for id_usuario in compradores]
            for futuro in concurrent.futures.as_completed(futuros):
                resultados.append(futuro.result())

        ganadores = [id_usuario for id_usuario, status, _ in resultados if status == 201]
        exitos = len(ganadores)
        rechazos = TOTAL_REQUESTS - exitos
        desglose = {}
        for _, status, body in resultados:
            if status != 201:
                clave = f"{status} {body.get('error')}"
                desglose[clave] = desglose.get(clave, 0) + 1

        print(f"[4/6] Resultados: {exitos} éxitos (201), {rechazos} rechazos.")
        if desglose:
            print(f"       Desglose de rechazos: {desglose}")

        print("[5/6] Consultando la oferta tras las reservas...")
        oferta = leer_oferta()
        stock_restante = oferta.get("stock_restante")
        reservadas = oferta.get("unidades_reservadas")
        vendidas = oferta.get("unidades_vendidas")
        print(f"       stock_restante={stock_restante} unidades_reservadas={reservadas} "
              f"unidades_vendidas={vendidas}")

        print("[6/6] Vaciando los carritos de los ganadores (libera sus reservas)...")
        for id_usuario in ganadores:
            vaciar_carrito(id_usuario)
        stock_tras_liberar = leer_oferta().get("stock_restante")
        print(f"       stock_restante tras liberar={stock_tras_liberar}")
    finally:
        # Los perdedores no deberían tener carrito, pero por si acaso.
        for id_usuario in compradores:
            if id_usuario not in ganadores:
                vaciar_carrito(id_usuario)
        print("\nLimpiando oferta de prueba...")
        limpiar_oferta()

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"Total de reservas disparadas      : {TOTAL_REQUESTS}")
    print(f"Éxitos (201)                      : {exitos}   (esperado {LIMITE_OFERTA})")
    print(f"Rechazos                          : {rechazos}   (esperado {TOTAL_REQUESTS - LIMITE_OFERTA})")
    print(f"stock_restante tras reservar      : {stock_restante}   (esperado 0)")
    print(f"unidades_reservadas               : {reservadas}   (esperado {LIMITE_OFERTA})")
    print(f"unidades_vendidas                 : {vendidas}   (esperado 0)")
    print(f"stock_restante tras liberar       : {stock_tras_liberar}   (esperado {LIMITE_OFERTA})")

    fallas = []
    if exitos != LIMITE_OFERTA:
        fallas.append(f"se esperaban {LIMITE_OFERTA} éxitos, hubo {exitos}")
    if rechazos != TOTAL_REQUESTS - LIMITE_OFERTA:
        fallas.append(f"se esperaban {TOTAL_REQUESTS - LIMITE_OFERTA} rechazos, hubo {rechazos}")
    if stock_restante != 0:
        fallas.append(f"stock_restante tras reservar debía ser 0, fue {stock_restante}")
    if reservadas != LIMITE_OFERTA:
        fallas.append(f"unidades_reservadas debía ser {LIMITE_OFERTA}, fue {reservadas}")
    if vendidas != 0:
        fallas.append(f"unidades_vendidas debía ser 0, fue {vendidas}")
    if stock_tras_liberar != LIMITE_OFERTA:
        fallas.append(f"stock_restante tras liberar debía ser {LIMITE_OFERTA}, fue {stock_tras_liberar}")

    if not fallas:
        print("\nRESULTADO: PASS -- no hubo sobreventa bajo concurrencia y liberar devolvió el cupo.")
    else:
        print("\nRESULTADO: FAIL -- discrepancias:")
        for f in fallas:
            print(f"  - {f}")
    print("Listo.")


if __name__ == "__main__":
    main()
