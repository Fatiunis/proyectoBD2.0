import os
import sys

# Permite ejecutar este archivo directamente ("python backend/main.py") y que
# el paquete local "app" (backend/app) se resuelva sin importar desde dónde
# se invoque el script.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.sincronizacion import iniciar_relevo

DEBUG = True

app = create_app()

if __name__ == "__main__":
    # Relevo del outbox del checkout (Entrega 3): un hilo de fondo que reintenta
    # los eventos de sincronización pendientes. Con debug=True Flask arranca dos
    # procesos (el vigilante del reloader y el que atiende las peticiones); el
    # relevo solo se inicia en el segundo, marcado con WERKZEUG_RUN_MAIN.
    if not DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        iniciar_relevo(app)
    app.run(host="127.0.0.1", port=8000, debug=DEBUG, threaded=True)
