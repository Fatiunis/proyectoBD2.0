import os
import sys

# Permite ejecutar este archivo directamente ("python backend/main.py") y que
# el paquete local "app" (backend/app) se resuelva sin importar desde dónde
# se invoque el script.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
