"""Pruebas de la lógica de negocio: carga, tipos, comparación y diferencias.

Ejecutar:  python tests/test_nucleo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

import data_cleaning as dc  # noqa: E402
import data_loader as dl  # noqa: E402
import diffing  # noqa: E402
import schema_mapper as sm  # noqa: E402
import validators as v  # noqa: E402
from comparator import CompareOptions, compare_dataframes, compare_positional  # noqa: E402
from tests import fixtures  # noqa: E402


def test_carga_csv_detecta_separador_y_codificacion():
    df, avisos = dl.load_table("archivo1.csv", fixtures.CSV_A)
    assert list(df.columns)[:2] == ["ID", "Nombre"]
    assert len(df) == 5
    assert "Perú" in df["Pais"].tolist(), "debe respetar las tildes de un archivo Windows-1252"
    detalle = " ".join(a["detalle"] for a in avisos)
    assert "punto y coma" in detalle and "Windows-1252" in detalle
    # El índice es el número de fila real del archivo, para que los mensajes coincidan.
    assert df.index.tolist() == [2, 3, 4, 5, 6]


def test_carga_excel_avisa_de_celdas_combinadas_y_ocultas():
    libro = fixtures.excel_multihoja()
    hojas = dl.get_sheet_info("multi.xlsx", libro)
    assert [h["nombre"] for h in hojas] == ["Portada", "Datos", "Oculta"]
    assert hojas[2]["visible"] is False

    df, avisos = dl.load_table("multi.xlsx", libro, sheet="Datos", header_row=2)
    titulos = {a["titulo"] for a in avisos}
    assert "Celdas combinadas" in titulos
    assert "Columnas ocultas o colapsadas" in titulos
    assert "Filas ocultas, filtradas o colapsadas" in titulos
    assert df["Serial"].tolist() == ["00123", "00124"], "el cero a la izquierda debe conservarse"

    # Al excluir lo oculto, desaparecen la columna C y la fila 4.
    df2, _ = dl.load_table("multi.xlsx", libro, sheet="Datos", header_row=2,
                           skip_hidden_rows=True, skip_hidden_cols=True)
    assert "Costo" not in df2.columns and len(df2) == 1


def test_errores_en_lenguaje_natural():
    casos = [("informe.pdf", b"x", "formato no soportado"),
             ("libro.xlsx", b"no es un zip", "no es un libro de Excel"),
             ("vacio.csv", b"", "está vacío"),
             ("roto.csv", b"a,b\n1,2\n1,2,3,4\n", "columnas")]
    for nombre, datos, esperado in casos:
        try:
            dl.load_table(nombre, datos)
            raise AssertionError(f"{nombre} debería fallar")
        except dl.FileLoadError as exc:
            assert esperado in exc.message, f"{nombre}: {exc.message}"
            assert exc.suggestion, "todo error debe traer una sugerencia para el usuario"


def test_tipos_sin_perdida_de_formato():
    df, _ = dl.load_table("archivo1.csv", fixtures.CSV_A)
    esquema = sm.infer_schema(dc.clean_data(df))
    tipos = dict(zip(esquema["Columna"], esquema["Tipo detectado"]))
    assert tipos["ID"] == sm.IDENTIFICADOR
    assert tipos["Responsable / Correo"] == sm.EMAIL
    assert tipos["Cantidad Total"] == sm.DECIMAL
    assert tipos["Fecha Compra"] == sm.FECHA


def test_separador_decimal_por_columna():
    casos = {
        "coma": (["100,50", "100,505", "200", "7"], [100.5, 100.505, 200.0, 7.0]),
        "punto": (["1,234.56", "9.99", "1,000.00", "12"], [1234.56, 9.99, 1000.0, 12.0]),
        "mixto_eu": (["1.234,56", "2.000", "15,5", "0,75"], [1234.56, 2000.0, 15.5, 0.75]),
        "miles_coma": (["1,000", "2,500", "3,750", "10"], [1000.0, 2500.0, 3750.0, 10.0]),
        "miles_punto": (["1.000", "2.500", "3.750", "10"], [1000.0, 2500.0, 3750.0, 10.0]),
    }
    for nombre, (valores, esperado) in casos.items():
        estilo = sm.column_decimal_style(pd.Series(valores))
        assert [sm.parse_number(x, estilo) for x in valores] == esperado, nombre


def test_el_estilo_decimal_se_deduce_con_ambos_archivos():
    # "100,505" es ambiguo por sí solo; junto a "100,50" queda claro que la coma es decimal.
    a = pd.DataFrame({"Cantidad": ["100,50", "200", "300"]})
    b = pd.DataFrame({"Cantidad": ["100,505", "200", "50"]})
    esquema = {"Cantidad": sm.DECIMAL}
    estilos = sm.decimal_styles(esquema, a, b)
    assert estilos["Cantidad"] == sm.ESTILO_COMA_DECIMAL
    assert sm.apply_schema(b, esquema, estilos)[0]["Cantidad"].tolist() == [100.505, 200.0, 50.0]


def _preparar(datos, nombre, esquema=None, estilos=None):
    df, _ = dl.load_table(nombre, datos)
    limpio = dc.clean_data(df)
    if esquema is None:
        info = sm.infer_schema(limpio)
        esquema = dict(zip(info["Columna"], info["Tipo de dato"]))
    return sm.apply_schema(limpio, esquema, estilos)[0], esquema


def _ambos_archivos():
    a_limpio = dc.clean_data(dl.load_table("a.csv", fixtures.CSV_A)[0])
    b_limpio = dc.clean_data(dl.load_table("b.csv", fixtures.CSV_B)[0])
    info = sm.infer_schema(a_limpio, b_limpio)
    esquema = dict(zip(info["Columna"], info["Tipo de dato"]))
    estilos = sm.decimal_styles(esquema, a_limpio, b_limpio)
    return (sm.apply_schema(a_limpio, esquema, estilos)[0],
            sm.apply_schema(b_limpio, esquema, estilos)[0])


COLUMNAS = ["Nombre", "Responsable / Correo", "Cantidad Total", "Fecha Compra", "Pais", "Auditoria"]


def test_duplicados_se_emparejan_uno_a_uno_sin_descartar():
    a, b = _ambos_archivos()
    opciones = CompareOptions(excluded=["Auditoria"])
    r = compare_dataframes(a, b, ["ID"], COLUMNAS, opciones)
    # L-1 aparece 3 veces en A y 2 en B: se cruzan 1ª-1ª y 2ª-2ª, y la 3ª queda como baja.
    assert len(r.added) == 1 and len(r.removed) == 2
    assert len(r.changed) == 2 and len(r.unchanged) == 1
    assert len(r.added) + len(r.removed) + len(r.changed) + len(r.unchanged) == r.total_keys
    assert r.huerfanos_a == 1 and r.huerfanos_b == 0
    assert r.frecuencias.iloc[0]["Veces en Archivo 1"] == 3
    assert r.frecuencias.iloc[0]["Veces en Archivo 2"] == 2
    # Ninguna fila del archivo original desaparece del resultado.
    assert len(r.consolidated) == r.total_keys


def test_tipos_de_diferencia_y_tolerancias():
    a, b = _ambos_archivos()
    estricto = CompareOptions(excluded=["Auditoria"], ignore_spaces=False)
    tipos = set(compare_dataframes(a, b, ["ID"], COLUMNAS, estricto).details["Tipo de diferencia"])
    assert {diffing.TILDES, diffing.MAYUSCULAS, diffing.NUM_DISTINTO} <= tipos

    tolerante = CompareOptions(excluded=["Auditoria"], ignore_case=True, ignore_accents=True,
                               ignore_spaces=True, numeric_tolerance=0.01, date_tolerance=True)
    r = compare_dataframes(a, b, ["ID"], COLUMNAS, tolerante)
    assert r.details.empty, "con las tolerancias activas no debe quedar ninguna diferencia"
    assert len(r.unchanged) == 3


def test_inclusion_del_archivo_1_en_el_2():
    a, b = _ambos_archivos()
    parcial = compare_dataframes(a, b, ["ID"], COLUMNAS, CompareOptions(excluded=["Auditoria"]))
    assert parcial.inclusion["contenido"] is False
    assert parcial.inclusion["faltantes"] == 2

    total = compare_dataframes(a, pd.concat([a, b], ignore_index=True), ["ID"], COLUMNAS,
                               CompareOptions(excluded=["Auditoria"]))
    assert total.inclusion["contenido"] is True
    assert total.inclusion["cobertura_exacta"] == 100.0
    assert len(total.removed) == 0


def test_columnas_volatiles_excluidas():
    a, b = _ambos_archivos()
    sin_excluir = compare_dataframes(a, b, ["ID"], COLUMNAS, CompareOptions())
    con_excluir = compare_dataframes(a, b, ["ID"], COLUMNAS, CompareOptions(excluded=["Auditoria"]))
    assert "Auditoria" in sin_excluir.cols and "Auditoria" not in con_excluir.cols
    assert len(sin_excluir.unchanged) < len(con_excluir.unchanged)


def test_cruce_posicional():
    a = pd.DataFrame({"ID": ["1", "2", "3", "4"], "V": ["a", "b", "c", "d"]})
    b = pd.DataFrame({"ID": ["1", "9", "2", "3"], "V": ["a", "z", "b", "C"]})
    pos = compare_positional(a, b, ["ID", "V"], CompareOptions())
    assert pos.mismo_orden is False
    assert (pos.iguales, pos.desplazadas, pos.distintas) == (1, 1, 1)
    assert (pos.solo_en_a, pos.solo_en_b) == (1, 1)
    assert set(pos.detalle["Tipo"]) == {"Solo en Archivo 1", "Solo en Archivo 2", "Desplazada",
                                        "Contenido distinto en la misma posición"}

    igual = compare_positional(a, a.copy(), ["ID", "V"], CompareOptions())
    assert igual.mismo_orden is True and igual.iguales == 4


def test_clasificacion_y_resaltado_por_caracter():
    casos = [
        (("Hola", "hola"), diffing.MAYUSCULAS),
        (("Camión", "Camion"), diffing.TILDES),
        (("a  b", "a b"), diffing.ESPACIOS),
        (("2024-01-15", "15/01/2024"), diffing.FORMATO_FECHA),
        (("100.00", "100.005"), diffing.NUM_TOLERANCIA),
        (("Servidor A", "Servidor B"), diffing.TEXTO_DISTINTO),
        (("dato", None), diffing.FALTANTE),
    ]
    for (x, y), esperado in casos:
        tipo, _ = diffing.classify_difference(x, y, numeric_tolerance=0.01)
        assert tipo == esperado, f"{x!r} vs {y!r} -> {tipo}"

    izquierda, derecha = diffing.char_diff_html("Camión rojo", "Camion Rojo")
    assert 'class="diff-del"' in izquierda and 'class="diff-ins"' in derecha
    assert "&lt;" not in "Camión rojo"  # el escapado solo aplica a contenido peligroso
    assert diffing.char_diff_html("<b>", "x")[0].startswith('<span class="diff-del">&lt;b&gt;')

    assert diffing.jaro_winkler("Servidor A", "Servidor B") > 0.9
    assert 0 < diffing.levenshtein_ratio("Servidor A", "Servidor B") < 1


def test_limpieza_respeta_correos_codigos_y_vacios():
    df = pd.DataFrame({"ID": ["  007 "], "Correo": [" Juan.Perez+ti@Empresa.COM "],
                       "Nombre": ["  josé   pérez  "], "Vacio": ["   "]})
    esquema = {"ID": sm.IDENTIFICADOR, "Correo": sm.EMAIL, "Nombre": sm.TEXTO, "Vacio": sm.TEXTO}
    tipado = sm.apply_schema(dc.clean_data(df), esquema)[0]
    limpio = dc.normalize_text_data(tipado, esquema)
    assert limpio["ID"].iloc[0] == "007", "un identificador no pierde el cero a la izquierda"
    assert limpio["Correo"].iloc[0] == "Juan.Perez+ti@empresa.com", "el correo conserva su formato"
    assert limpio["Nombre"].iloc[0] == "Jose Perez", "la limpieza de texto normaliza tildes"
    assert pd.isna(limpio["Vacio"].iloc[0]), "una celda en blanco no se convierte en el texto 'nan'"


def test_validador_infraestructura_reconoce_la_columna_modelo():
    """Regresión: un mapeo mal escrito hacía que el validador abortara sin revisar nada."""
    df = fixtures.marco_infraestructura()
    errores, _ = v.validate_infraestructura(df)
    assert not any("ausente" in e for e in errores), errores
    faltante = df.drop(columns=["Modelo"])
    errores2, _ = v.validate_infraestructura(faltante)
    assert any("Modelo" in e and "ausente" in e for e in errores2)


class _BaseDeDatosFalsa:
    """Sustituto de DatabaseManager: evita tocar SQLite en las pruebas."""

    def obtener_proveedores(self):
        return ["Proveedor S.A."]

    def obtener_aplicaciones(self):
        return ["App Uno"]

    def obtener_usuarios(self):
        return [{"email": "ana@empresa.com"}]


def test_contrato_de_los_validadores():
    import re
    df = fixtures.marco_infraestructura()
    db = _BaseDeDatosFalsa()
    for esquema in ["Licencias TI", "Dominios", "Certificados", "Cuentas", "Usuario", "Infraestructura"]:
        resultado = v.run_validation(esquema, df, db)
        assert isinstance(resultado, tuple) and len(resultado) == 2, esquema
        errores, avisos = resultado
        assert isinstance(errores, list) and isinstance(avisos, list), esquema
        for mensaje in errores + avisos:
            assert re.match(r"^(Fila \S+?:|Columna |Nivel )", mensaje), f"{esquema}: {mensaje}"
    assert v.run_validation("General", df, db) == ([], [])


if __name__ == "__main__":
    from tests.runner import ejecutar
    sys.exit(ejecutar(globals(), "núcleo"))
