"""Pruebas de la interfaz: recorre el asistente en los tres modos con AppTest.

Ejecutar:  python -m tests.test_app
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamlit.testing.v1 import AppTest  # noqa: E402

from tests import fixtures  # noqa: E402

TIEMPO_LIMITE = 120
# Las columnas a comparar se eligen explícitamente (no vienen preseleccionadas).
COLUMNAS_A_COMPARAR = ["Nombre", "Responsable / Correo", "Cantidad Total", "Fecha Compra", "Pais"]


def _abrir():
    app = AppTest.from_file("app.py", default_timeout=TIEMPO_LIMITE)
    app.run()
    _sin_errores(app, "inicio")
    return app


def _sin_errores(app, etapa):
    assert not app.exception, f"{etapa}: {[str(e.value)[:200] for e in app.exception]}"
    assert not app.error, f"{etapa}: {[e.value[:200] for e in app.error]}"


def _cargar(app, archivos):
    app.session_state.files = {slot: {"name": nombre, "data": datos}
                               for slot, (nombre, datos) in archivos.items()}
    app.session_state.opts = {slot: dict(fixtures.OPCIONES_LECTURA) for slot in archivos}
    app.run()


def _siguiente(app):
    botones = [b for b in app.button
               if b.label.startswith(("Siguiente", "Confirmar", "Continuar", "Comparar"))]
    assert botones, f"no hay botón para avanzar en el paso {app.session_state.step}"
    botones[0].click().run()


def test_el_menu_lateral_conserva_los_modos():
    app = _abrir()
    modos = app.sidebar.radio[0]
    assert modos.options == ["Comparar archivos", "Validar archivo único", "Limpiar archivo"]
    assert [s.label for s in app.sidebar.selectbox] == ["Esquema de reglas"]
    assert app.session_state.step == 1


def test_recorrido_de_comparacion():
    app = _abrir()
    _cargar(app, {"old": ("archivo1.csv", fixtures.CSV_A),
                  "new": ("archivo2.csv", fixtures.CSV_B)})
    _sin_errores(app, "carga")
    detectado = " ".join(c.value for c in app.caption)
    assert "punto y coma" in detectado and "Windows-1252" in detectado

    _siguiente(app)                      # -> esquema de datos
    _sin_errores(app, "esquema")
    assert app.session_state.schema_map["Responsable / Correo"] == "Email"

    _siguiente(app)                      # -> reglas de comparación
    _sin_errores(app, "reglas")
    app.multiselect(key="rules_keys").set_value(["ID"]).run()
    app.multiselect(key="rules_cols").set_value(COLUMNAS_A_COMPARAR + ["Auditoria"]).run()
    app.multiselect(key="rules_excl").set_value(["Auditoria"]).run()
    _sin_errores(app, "reglas configuradas")
    assert app.session_state.cmp["keys"] == ["ID"]
    assert "Auditoria" not in app.session_state.cmp["cols"], "la volátil sale de la comparación"

    _siguiente(app)                      # -> resultados
    _sin_errores(app, "resultados")
    assert app.session_state.step == 4

    tarjetas = " ".join(m.value for m in app.markdown if "metric-card" in m.value)
    assert "Altas" in tarjetas and "Bajas" in tarjetas and "Modificaciones" in tarjetas
    inclusion = [m.value for m in app.markdown if "inclusion-card" in m.value]
    assert inclusion, "debe mostrarse el indicador de inclusión"
    assert "¿Archivo 1 totalmente contenido en Archivo 2?" in inclusion[-1]
    avisos = " ".join(w.value for w in app.warning)
    assert "Desbalance de repeticiones" in avisos, "debe avisar de los duplicados sin pareja"
    assert any("diff-del" in str(h.proto) for h in app.get("html")), "falta el diff por carácter"


def test_las_tolerancias_refrescan_los_resultados():
    app = _abrir()
    _cargar(app, {"old": ("archivo1.csv", fixtures.CSV_A),
                  "new": ("archivo2.csv", fixtures.CSV_B)})
    _siguiente(app)
    _siguiente(app)
    app.multiselect(key="rules_keys").set_value(["ID"]).run()
    app.multiselect(key="rules_cols").set_value(COLUMNAS_A_COMPARAR).run()
    _siguiente(app)
    _sin_errores(app, "resultados")

    def diferencias():
        etiqueta = [t for t in app.tabs if t.label and t.label.startswith("Detalle de diferencias")]
        assert etiqueta, "falta la pestaña de detalle"
        return int(etiqueta[0].label.split("(")[1].rstrip(")"))

    antes = diferencias()
    assert antes > 0
    for clave in ("res_case", "res_acc"):
        app.toggle(key=clave).set_value(True).run()
    app.number_input(key="res_tol").set_value(0.01).run()
    _sin_errores(app, "con tolerancias")
    assert diferencias() < antes, "al tolerar mayúsculas, tildes y ±0,01 deben bajar las diferencias"

    app.toggle(key="res_fz").set_value(True).run()
    _sin_errores(app, "coincidencia difusa")
    app.multiselect(key="res_keys").set_value(["ID", "Nombre"]).run()
    _sin_errores(app, "cambio de clave")
    assert "Nombre" not in app.multiselect(key="res_cols").value, \
        "al pasar a clave, la columna sale de la comparación"


def _recorrer_modo(modo, slot, archivo):
    app = _abrir()
    app.sidebar.radio[0].set_value(modo).run()
    _cargar(app, {slot: archivo})
    for casilla in app.checkbox:
        if casilla.key and casilla.key.startswith("ack_"):
            casilla.check().run()
    pasos = 0
    while [b for b in app.button
           if b.label.startswith(("Siguiente", "Confirmar", "Continuar", "Comparar"))]:
        _siguiente(app)
        pasos += 1
        assert pasos <= 4, "el asistente no debería tener más de 4 pasos"
    _sin_errores(app, modo)
    assert pasos >= 2 and app.session_state.step == pasos + 1
    return app


def test_modo_validar_archivo_unico():
    app = _recorrer_modo("Validar archivo único", "single", ("archivo1.csv", fixtures.CSV_A))
    assert any("alert-card" in m.value for m in app.markdown), "faltan las tarjetas de validación"


def test_modo_limpiar_archivo():
    app = _recorrer_modo("Limpiar archivo", "clean", ("archivo1.csv", fixtures.CSV_A))
    etiquetas = " ".join(m.value for m in app.markdown if "metric-card" in m.value)
    assert "normalizadas" in etiquetas or "Registros" in etiquetas


def test_excel_multihoja_con_avisos_preventivos():
    app = _abrir()
    app.sidebar.radio[0].set_value("Validar archivo único").run()
    app.session_state.files = {"single": {"name": "multi.xlsx", "data": fixtures.excel_multihoja()}}
    opciones = dict(fixtures.OPCIONES_LECTURA)
    opciones.update({"sheet": "Datos", "header_row": 2})
    app.session_state.opts = {"single": opciones}
    app.run()
    titulos = " ".join(w.value for w in app.warning)
    assert "Celdas combinadas" in titulos
    assert "Columnas ocultas" in titulos
    assert any(s.label == "Hoja / pestaña" for s in app.selectbox), "falta el selector de hoja"


if __name__ == "__main__":
    from tests.runner import ejecutar
    sys.exit(ejecutar(globals(), "interfaz"))
