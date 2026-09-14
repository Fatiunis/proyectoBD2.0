"""
Prueba de concurrencia para la oferta de inventario limitado (flash sale).

Standalone: NO es parte de la app Flask, se corre manualmente contra un
servidor real ya levantado (python backend/main.py, escuchando en
http://127.0.0.1:8000) y con Redis disponible.

Dispara 50 requests concurrentes de "reservar 1 unidad" contra una oferta con
límite 10, simulando 50 compradores distintos, y verifica que Redis (vía el
script Lua atómico) haya evitado la sobreventa: exactamente 10 éxitos, 40
rechazos, stock final en 0.

Uso:
    python backend/scripts/prueba_concurrencia_oferta.py
"""

import concurrent.futures

import requests

BASE_URL = "http://127.0.0.1:8000"
PRODUCTO_ID = "PROD-TEST-CONCURRENCIA"
LIMITE_OFERTA = 10
TOTAL_REQUESTS = 50
MAX_WORKERS = 20


def limpiar_oferta():
    try:
        requests.delete(
            f"{BASE_URL}/api/ofertas/{PRODUCTO_ID}",
            params={"rol_solicitante": "administrador"},
            timeout=5,
        )
    except requests.RequestException:
        # No importa si falla (p.ej. no existía la oferta): es solo limpieza.
        pass


def crear_oferta():
    resp = requests.post(
        f"{BASE_URL}/api/ofertas",
        json={
            "producto_id": PRODUCTO_ID,
            "cantidad_limite": LIMITE_OFERTA,
            "rol_solicitante": "administrador",
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

    print(f"\n[1/5] Limpiando oferta previa de {PRODUCTO_ID} (si existía)...")
    limpiar_oferta()

    print(f"[2/5] Creando oferta nueva con límite {LIMITE_OFERTA}...")
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
