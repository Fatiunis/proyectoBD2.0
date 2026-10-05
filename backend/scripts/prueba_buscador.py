"""
Evidencia del buscador del catálogo (Entrega 3).

Standalone: se corre contra el servidor real (python backend/main.py) con el
índice ya construido (database/migrations/indexar_productos_elasticsearch.py).
Ejerce GET /api/busqueda y GET /api/busqueda/autocompletar y verifica:

  B1  Tolerancia a errores de tipeo (fuzziness) y "¿quisiste decir?".
  B2  Sinónimos y raíces en español (es_texto_busqueda).
  B3  Relevancia: la categoría que nombra lo buscado va primero.
  B4  Autocompletado por prefijo, también con un error de tipeo.
  B5  Facetas calculadas con agregaciones, disyuntivas (elegir una marca no
      hace desaparecer las demás marcas de la lista).
  B6  Filtro de precio y ordenamiento por precio.
  B7  (opcional, --caida-real) Elasticsearch detenido -> 503 con código, y la
      búsqueda de respaldo de MongoDB sigue respondiendo.

Uso:
    venv\\Scripts\\python.exe backend/scripts/prueba_buscador.py
    venv\\Scripts\\python.exe backend/scripts/prueba_buscador.py --caida-real
"""

import argparse
import os
import subprocess
import sys
import time

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8000/api"
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
resultados = []


def verificar(caso, descripcion, condicion, detalle=""):
    resultados.append((caso, descripcion, bool(condicion)))
    print(f"   [{'OK  ' if condicion else 'FALLA'}] {descripcion}" + (f"  ({detalle})" if detalle else ""))


def buscar(**params):
    r = requests.get(f"{API}/busqueda", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def nombres(d, n=3):
    return [f"{i['nombre']} [{i['categoria']['nombre']}]" for i in d["items"][:n]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--caida-real", action="store_true")
    args = parser.parse_args()

    print("=" * 74)
    print("EVIDENCIA DEL BUSCADOR (ELASTICSEARCH)")
    print("=" * 74)

    print("\n[B1] Errores de tipeo")
    for mal, bien in [("laptp", "laptop"), ("audifnos", "audifonos"), ("celulr", "celular")]:
        d = buscar(q=mal, por_pagina=3)
        verificar("B1", f"'{mal}' encuentra resultados y sugiere '{bien}'",
                  d["total"] > 0 and d["sugerencia"] == bien, f"{d['total']} resultados; {nombres(d, 1)}")

    print("\n[B2] Sinónimos y raíces")
    d = buscar(q="portatil", por_pagina=3)
    verificar("B2", "'portatil' (sinónimo) encuentra laptops", d["items"] and d["items"][0]["categoria"]["nombre"] == "Laptops",
              str(nombres(d, 2)))
    d = buscar(q="auriculares", por_pagina=3)
    verificar("B2", "'auriculares' (sinónimo) encuentra audífonos",
              d["items"] and d["items"][0]["categoria"]["nombre"] == "Audífonos", str(nombres(d, 1)))
    d = buscar(q="mochilas", por_pagina=3)
    verificar("B2", "'mochilas' (plural) encuentra mochilas", d["total"] > 0, f"{d['total']} resultados")

    print("\n[B3] Relevancia")
    d = buscar(q="celular", por_pagina=5)
    verificar("B3", "'celular': los 5 primeros son de la categoría Celulares (no tablets 'Wi-Fi + Celular')",
              all(i["categoria"]["nombre"] == "Celulares" for i in d["items"]), str(nombres(d, 2)))
    d = buscar(q="smartphone samsung", por_pagina=3)
    verificar("B3", "'smartphone samsung' trae celulares Samsung primero",
              d["items"][0]["categoria"]["nombre"] == "Celulares" and "Samsung" in d["items"][0]["nombre"], str(nombres(d, 2)))
    d = buscar(q="mochila laptop", por_pagina=3)
    verificar("B3", "'mochila laptop' trae mochilas para laptop, no laptops",
              all(i["categoria"]["nombre"] == "Mochilas" for i in d["items"]), str(nombres(d, 2)))

    print("\n[B4] Autocompletado")
    for prefijo in ["iph", "lapt", "aufi"]:
        s = requests.get(f"{API}/busqueda/autocompletar", params={"q": prefijo}, timeout=10).json()
        verificar("B4", f"'{prefijo}' devuelve sugerencias", len(s) > 0, ", ".join(x["nombre"] for x in s[:2]))

    print("\n[B5] Facetas (agregaciones del motor)")
    d = buscar(q="mouse", por_pagina=1)
    marcas = [m["marca"] for m in d["facetas"]["marcas"]]
    verificar("B5", "la búsqueda 'mouse' trae facetas de categoría, marca, tienda y precio",
              all(d["facetas"][k] for k in ("categorias", "marcas", "tiendas", "precios")),
              f"marcas={marcas[:4]}")
    m = d["facetas"]["marcas"][0]
    d2 = buscar(q="mouse", marca=m["marca"], por_pagina=1)
    verificar("B5", f"filtrar por marca={m['marca']} deja {m['cantidad']} resultados (el conteo de la faceta)",
              d2["total"] == m["cantidad"], f"total={d2['total']}")
    verificar("B5", "con la marca elegida, la faceta de marcas sigue mostrando las demás (disyuntiva)",
              len(d2["facetas"]["marcas"]) == len(d["facetas"]["marcas"]), f"{len(d2['facetas']['marcas'])} marcas")
    verificar("B5", "las demás facetas sí se recalculan con el filtro de marca",
              sum(t["cantidad"] for t in d2["facetas"]["tiendas"]) == d2["total"])

    print("\n[B6] Precio y orden")
    d = buscar(q="laptop", precio_min=1000, precio_max=5000, orden="precio_asc", por_pagina=50)
    precios = [i["precio_base"] for i in d["items"]]
    verificar("B6", "filtro Q1,000 a Q5,000 respetado", precios and all(1000 <= p < 5000 for p in precios),
              f"{len(precios)} resultados, de Q{min(precios):.2f} a Q{max(precios):.2f}" if precios else "")
    verificar("B6", "orden por precio ascendente", precios == sorted(precios))

    if args.caida_real:
        print("\n[B7] Elasticsearch detenido de verdad")
        subprocess.run(["docker", "compose", "stop", "elasticsearch"], cwd=RAIZ, check=True, capture_output=True)
        try:
            r = requests.get(f"{API}/busqueda", params={"q": "laptop"}, timeout=15)
            verificar("B7", "GET /api/busqueda responde 503 BUSCADOR_NO_DISPONIBLE",
                      r.status_code == 503 and r.json().get("codigo") == "BUSCADOR_NO_DISPONIBLE", str(r.status_code))
            r = requests.get(f"{API}/productos", params={"q": "laptop"}, timeout=15)
            verificar("B7", "la búsqueda de respaldo (MongoDB $text) sigue respondiendo",
                      r.ok and r.json()["total"] > 0, f"{r.json().get('total')} resultados")
        finally:
            subprocess.run(["docker", "compose", "start", "elasticsearch"], cwd=RAIZ, check=True, capture_output=True)
            limite = time.time() + 120
            while time.time() < limite:
                try:
                    if requests.get(f"{API}/busqueda", params={"q": "laptop"}, timeout=5).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(3)
        verificar("B7", "al volver a levantarlo, el buscador responde de nuevo",
                  requests.get(f"{API}/busqueda", params={"q": "laptop"}, timeout=10).ok)

    total = len(resultados)
    fallas = [r for r in resultados if not r[2]]
    print("\n" + "=" * 74)
    print(f"RESUMEN: {total - len(fallas)}/{total} verificaciones correctas")
    for caso, desc, _ in fallas:
        print(f"   FALLA {caso}: {desc}")
    print("RESULTADO:", "PASS" if not fallas else "FAIL")
    sys.exit(0 if not fallas else 1)


if __name__ == "__main__":
    main()
