"""Ejecuta todas las pruebas del proyecto.

Uso:  python -m tests.run_all
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import test_app, test_nucleo  # noqa: E402
from tests.runner import ejecutar  # noqa: E402

if __name__ == "__main__":
    fallos = ejecutar(vars(test_nucleo), "núcleo")
    fallos += ejecutar(vars(test_app), "interfaz")
    print("\nResultado global:", "TODO CORRECTO" if not fallos else "HAY FALLOS")
    sys.exit(1 if fallos else 0)
