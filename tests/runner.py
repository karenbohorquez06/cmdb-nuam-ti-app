"""Ejecutor mínimo de pruebas (el proyecto no depende de pytest)."""
import time
import traceback


def ejecutar(espacio, titulo):
    """Corre todas las funciones `test_*` del módulo. Devuelve 0 si todas pasan."""
    pruebas = [(n, f) for n, f in sorted(espacio.items())
               if n.startswith("test_") and callable(f)]
    print(f"\n=== Pruebas de {titulo} ({len(pruebas)}) ===")
    fallos = []
    for nombre, funcion in pruebas:
        inicio = time.perf_counter()
        try:
            funcion()
            print(f"  OK    {nombre}  ({time.perf_counter() - inicio:.1f}s)")
        except Exception:  # noqa: BLE001
            print(f"  FALLA {nombre}")
            fallos.append((nombre, traceback.format_exc()))
    for nombre, detalle in fallos:
        print(f"\n--- {nombre} ---\n{detalle}")
    print(f"{len(pruebas) - len(fallos)}/{len(pruebas)} pruebas correctas en {titulo}.")
    return 1 if fallos else 0
