"""Chequeos estáticos ligeros sobre los módulos del proyecto (sin dependencias externas).

Uso:  python tests/revisar_estilo.py
"""
import ast
import io
import os
import re
import sys

import glob

FILES = sorted(glob.glob("*.py") + glob.glob("ui/*.py"))


def nombres_usados(tree):
    usados = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            usados.add(n.id)
        elif isinstance(n, ast.Attribute):
            pass
    # atributos tipo mod.func
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute):
            base = n
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                usados.add(base.id)
    return usados


def revisar(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    lineas = src.splitlines()
    usados = nombres_usados(tree)
    # también los nombres citados en cadenas (p.ej. columnas) no cuentan
    problemas = []

    # 1) imports sin usar
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                if a.name == "*":
                    problemas.append((n.lineno, "import-estrella",
                                      f"from {getattr(n, 'module', '?')} import * oculta el origen de los nombres"))
                    continue
                local = a.asname or a.name.split(".")[0]
                if local not in usados:
                    problemas.append((n.lineno, "import-sin-uso", f"«{local}» importado pero no usado"))

    # 2) except desnudo / except Exception sin uso
    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler) and n.type is None:
            problemas.append((n.lineno, "except-desnudo", "`except:` captura incluso KeyboardInterrupt"))

    # 3) asignaciones a variables locales nunca leídas (dentro de funciones)
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        asignadas = {}
        leidas = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Name):
                if isinstance(n.ctx, ast.Store):
                    asignadas.setdefault(n.id, n.lineno)
                else:
                    leidas.add(n.id)
        for nombre, ln in asignadas.items():
            if nombre not in leidas and not nombre.startswith("_"):
                problemas.append((ln, "variable-sin-uso", f"«{nombre}» se asigna en {fn.name}() y nunca se lee"))

    # 4) funciones muy largas
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        fin = max((getattr(x, "lineno", fn.lineno) for x in ast.walk(fn)), default=fn.lineno)
        largo = fin - fn.lineno
        if largo > 80:
            problemas.append((fn.lineno, "funcion-larga", f"{fn.name}() ocupa ~{largo} líneas"))

    # 5) líneas largas
    largas = [i + 1 for i, l in enumerate(lineas) if len(l) > 120]
    if largas:
        problemas.append((largas[0], "lineas-largas", f"{len(largas)} líneas superan 120 caracteres"))

    # 6) TODO/FIXME/print de depuración
    for i, l in enumerate(lineas, start=1):
        if re.search(r"\b(TODO|FIXME|XXX)\b", l):
            problemas.append((i, "pendiente", l.strip()[:70]))
        if re.match(r"\s*print\(", l):
            problemas.append((i, "print", l.strip()[:70]))
    return sorted(problemas)


total = 0
for f in FILES:
    if not os.path.exists(f):
        continue
    p = revisar(f)
    if p:
        print(f"\n=== {f} ===")
        for ln, tipo, msg in p:
            print(f"  {f}:{ln:<5} [{tipo}] {msg}")
        total += len(p)
print(f"\nTOTAL: {total} observaciones")
