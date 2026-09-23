"""
Prueba de concurrencia para la oferta de inventario limitado (flash sale).

Standalone: NO es parte de la app Flask, se corre manualmente contra un
servidor real ya levantado (python backend/main.py, escuchando en
http://127.0.0.1:8000) y con Redis disponible.

Dispara 50 requests concurrentes de "reservar 1 unidad" contra una oferta con
límite 10, simulando 50 compradores distintos, y verifica que Redis (vía el
script Lua atómico) haya evitado la sobreventa: exactamente 10 éxitos, 40
rechazos, stock final en 0.

Usa un producto REAL del catálogo de Mongo (por defecto PROD-0001), porque
POST/DELETE /api/ofertas validan que el producto exista y que el solicitante
sea su dueño o un administrador. Se opera como administrador (id 1). Si ya hay
una oferta activa en ese producto, el script aborta sin tocarla (para no
pisar una oferta real); cambia PRODUCTO_ID o finalízala a mano.

Uso:
    python backend/scripts/prueba_concurrencia_oferta.py
"""

import concurrent.futures

import requests

BASE_URL = "http://127.0.0.1:8000"
PRODUCTO_ID = "PROD-0001"
ROL_ADMIN = "administrador"
ID_USUARIO_ADMIN = 1
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


def crear_oferta():
    resp = requests.post(
        f"{BASE_URL}/api/ofertas",
        json={
            "producto_id": PRODUCTO_ID,
            "cantidad_limite": LIMITE_OFERTA,
            "duracion_minutos": DURACION_MINUTOS,
            "rol_solicitante": ROL_ADMIN,
            "id_usuario": ID_USUARIO_ADMIN,
        },
        timeout=5,
    )
    if resp.status_code != 201:
        raise RuntimeError(f"No se pudo crear la oferta de prueba: {resp.status_code} {resp.text}")
    print(f"Oferta creada: {resp.json()}")


def reservar_una_unidad(id_usuario):
    try:
        resp = requests.post(
            f"{BASE_URL}/api/ofertas/{PRODUCTO_ID}/reservar",
            json={"id_usuario": id_usuario, "cantidad": 1},
            timeout=10,
        )
        return resp.status_code, resp.json()
    except requests.RequestException as e:
        return None, {"error": str(e)}


def main():
    print("=" * 70)
    print("PRUEBA DE CONCURRENCIA - OFERTA DE INVENTARIO LIMITADO (FLASH SALE)")
    print("=" * 70)

    print(f"\n[1/5] Verificando que {PRODUCTO_ID} no tenga una oferta activa...")
    verificar_sin_oferta_activa()

    print(f"[2/5] Creando oferta nueva con límite {LIMITE_OFERTA} "
          f"y duración {DURACION_MINUTOS} min...")
    crear_oferta()

    print(f"[3/5] Disparando {TOTAL_REQUESTS} requests concurrentes "
          f"(1 unidad c/u, {MAX_WORKERS} workers)...")

    resultados = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = [
            executor.submit(reservar_una_unidad, id_usuario)
            for id_usuario in range(1, TOTAL_REQUESTS + 1)
        ]
        for futuro in concurrent.futures.as_completed(futuros):
            resultados.append(futuro.result())

    exitos = sum(1 for status, _ in resultados if status == 201)
    rechazos = sum(1 for status, _ in resultados if status != 201)
    otros_codigos = {}
    for status, body in resultados:
        if status != 201:
            otros_codigos.setdefault(status, 0)
            otros_codigos[status] += 1

    print(f"[4/5] Resultados: {exitos} éxitos (201), {rechazos} rechazos.")
    if otros_codigos:
        print(f"       Desglose de rechazos por código: {otros_codigos}")

    print(f"[5/5] Consultando stock_restante real en la oferta...")
    resp_final = requests.get(f"{BASE_URL}/api/ofertas/{PRODUCTO_ID}", timeout=5)
    if resp_final.status_code == 200:
        stock_restante_real = resp_final.json()["stock_restante"]
    else:
        stock_restante_real = None
        print(f"       ADVERTENCIA: no se pudo leer la oferta al final "
              f"({resp_final.status_code} {resp_final.text})")

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"Total de requests disparados : {TOTAL_REQUESTS}")
    print(f"Éxitos (201)                 : {exitos}")
    print(f"Rechazos (409/otro)          : {rechazos}")
    print(f"Stock restante esperado      : 0")
    print(f"Stock restante real          : {stock_restante_real}")

    exito_esperado = LIMITE_OFERTA
    rechazo_esperado = TOTAL_REQUESTS - LIMITE_OFERTA

    if exitos == exito_esperado and rechazos == rechazo_esperado and stock_restante_real == 0:
        print("\nRESULTADO: PASS -- no hubo sobreventa bajo concurrencia.")
    else:
        print("\nRESULTADO: FAIL -- discrepancia detectada:")
        if exitos != exito_esperado:
            print(f"  - Se esperaban {exito_esperado} éxitos, hubo {exitos}.")
        if rechazos != rechazo_esperado:
            print(f"  - Se esperaban {rechazo_esperado} rechazos, hubo {rechazos}.")
        if stock_restante_real != 0:
            print(f"  - Se esperaba stock_restante == 0, fue {stock_restante_real}.")

    print("\nLimpiando oferta de prueba...")
    limpiar_oferta()
    print("Listo.")


if __name__ == "__main__":
    main()
