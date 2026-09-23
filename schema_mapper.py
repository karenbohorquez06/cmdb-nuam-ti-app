"""Selección dinámica de esquema: infiere el tipo de cada columna y aplica los
tipos confirmados por el usuario sin perder el formato original de los datos."""
import re

import pandas as pd

TEXTO = "Texto"
IDENTIFICADOR = "Identificador / Código"
EMAIL = "Email"
ENTERO = "Entero"
DECIMAL = "Decimal (Float)"
FECHA = "Fecha"
BOOLEANO = "Booleano (Sí/No)"

TIPOS = [TEXTO, IDENTIFICADOR, EMAIL, ENTERO, DECIMAL, FECHA, BOOLEANO]

TIPO_DESCRIPCION = {
    TEXTO: "Texto libre. Se eliminan espacios sobrantes al inicio y al final.",
    IDENTIFICADOR: "Se conserva exactamente (ceros a la izquierda, guiones, mayúsculas).",
    EMAIL: "Se conserva el formato del correo; se valida su estructura.",
    ENTERO: "Número sin decimales.",
    DECIMAL: "Número con decimales. Acepta 1.234,56 y 1,234.56.",
    FECHA: "Fecha (día/mes/año o año-mes-día).",
    BOOLEANO: "Sí/No, Verdadero/Falso, 1/0.",
}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_TRUE = {"si", "sí", "s", "true", "verdadero", "v", "1", "x", "yes", "y"}
_FALSE = {"no", "n", "false", "falso", "f", "0", "", "-"}
_ID_TOKENS = {"id", "key", "identificador", "ident", "codigo", "código", "code", "uuid", "serial",
              "nit", "rut", "sku", "cod", "placa", "serie"}
_EMAIL_TOKENS = {"email", "e-mail", "correo", "mail"}
_DATE_TOKENS = {"fecha", "date", "vencimiento", "inicio", "fin"}


def _tokens(name):
    return [t for t in re.split(r"[^a-z0-9áéíóúñ]+", str(name).lower()) if t]


def _looks_like_id_name(name):
    toks = _tokens(name)
    return any(t in _ID_TOKENS or t.endswith("id") and len(t) <= 6 for t in toks)


def _looks_like_email_name(name):
    return any(t in _EMAIL_TOKENS or "correo" in t or "email" in t for t in _tokens(name))


ESTILO_COMA_DECIMAL = "coma"    # 1.234,56  (convención de Chile, Perú y Colombia)
ESTILO_PUNTO_DECIMAL = "punto"  # 1,234.56  (convención anglosajona)
ESTILO_NOMBRE = {
    ESTILO_COMA_DECIMAL: "la coma como separador decimal (1.234,56)",
    ESTILO_PUNTO_DECIMAL: "el punto como separador decimal (1,234.56)",
}


def column_decimal_style(series):
    """Deduce, mirando toda la columna, si la coma o el punto es el separador decimal.

    Se busca evidencia inequívoca: un separador seguido de una cantidad de dígitos
    distinta de tres (12,5 / 9.99) o dos separadores en el mismo número (1.234,56).
    Si no la hay, se usa el patrón de miles y, en último caso, la coma, que es la
    convención de Chile, Perú y Colombia."""
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return ESTILO_COMA_DECIMAL

    ambos_coma_ultima = values.str.fullmatch(r"-?\d{1,3}(\.\d{3})+,\d+")
    ambos_punto_ultimo = values.str.fullmatch(r"-?\d{1,3}(,\d{3})+\.\d+")
    coma_no_miles = values.str.fullmatch(r"-?\d+,(\d{1,2}|\d{4,})")
    punto_no_miles = values.str.fullmatch(r"-?\d+\.(\d{1,2}|\d{4,})")
    fuerte_coma = int(ambos_coma_ultima.sum() + coma_no_miles.sum())
    fuerte_punto = int(ambos_punto_ultimo.sum() + punto_no_miles.sum())
    if fuerte_coma != fuerte_punto:
        return ESTILO_COMA_DECIMAL if fuerte_coma > fuerte_punto else ESTILO_PUNTO_DECIMAL

    # Sin evidencia: si hay grupos de miles, el otro símbolo es el decimal.
    miles_punto = int(values.str.fullmatch(r"-?\d{1,3}(\.\d{3})+").sum())
    miles_coma = int(values.str.fullmatch(r"-?\d{1,3}(,\d{3})+").sum())
    if miles_punto != miles_coma:
        return ESTILO_COMA_DECIMAL if miles_punto > miles_coma else ESTILO_PUNTO_DECIMAL
    return ESTILO_COMA_DECIMAL


def parse_number(value, style=ESTILO_COMA_DECIMAL):
    """Convierte '1.234,56', '1,234.56', '$ 1 234', '15%' a float. None si no es número.
    `style` indica qué símbolo actúa como separador decimal en la columna."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    pct = s.endswith("%")
    s = re.sub(r"[^\d,.\-+eE]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if style == ESTILO_COMA_DECIMAL and s.count(",") == 1:
            s = s.replace(",", ".")
        else:
            # La coma actúa como separador de miles.
            s = s.replace(",", "")
    elif s.count(".") > 1 or (style == ESTILO_COMA_DECIMAL and "." in s
                              and len(s.rsplit(".", 1)[1]) == 3 and s.lstrip("-+")[0] != "0"):
        s = s.replace(".", "")
    try:
        num = float(s)
    except ValueError:
        return None
    return num / 100 if pct else num


def parse_dates(series):
    s = series.astype("string").str.strip()
    out = pd.to_datetime(s, errors="coerce", format="ISO8601")
    missing = out.isna() & s.notna() & (s != "")
    if missing.any():
        out.loc[missing] = pd.to_datetime(s[missing], errors="coerce", dayfirst=True, format="mixed")
    # Números seriales de Excel (ej. 45123)
    missing = out.isna() & s.notna() & s.str.fullmatch(r"\d{5}(\.\d+)?").fillna(False)
    if missing.any():
        serial = pd.to_numeric(s[missing], errors="coerce")
        out.loc[missing] = pd.to_datetime("1899-12-30") + pd.to_timedelta(serial, unit="D")
    return out


def infer_column_type(name, series):
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    if _looks_like_email_name(name):
        return EMAIL
    if values.empty:
        return IDENTIFICADOR if _looks_like_id_name(name) else TEXTO
    sample = values.head(500)
    ratio = lambda mask: float(mask.mean()) if len(mask) else 0.0  # noqa: E731

    if ratio(sample.str.match(EMAIL_RE)) >= 0.8:
        return EMAIL
    if _looks_like_id_name(name):
        return IDENTIFICADOR
    # Ceros a la izquierda => código, no número
    if ratio(sample.str.fullmatch(r"0\d+")) > 0.1:
        return IDENTIFICADOR
    lower = sample.str.lower()
    if lower.isin(_TRUE | _FALSE - {""}).all() and lower.nunique() <= 2 and not sample.str.fullmatch(r"\d+").all():
        return BOOLEANO
    nums = sample.map(parse_number)
    if ratio(nums.notna()) >= 0.95:
        if nums.dropna().map(lambda v: float(v).is_integer()).all() and not sample.str.contains(r"[.,]\d{1,2}$").any():
            return ENTERO
        return DECIMAL
    date_like = sample.str.contains(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}")
    if ratio(date_like) >= 0.8 or (any(t in _DATE_TOKENS for t in _tokens(name)) and ratio(date_like) >= 0.5):
        if ratio(parse_dates(sample).notna()) >= 0.8:
            return FECHA
    return TEXTO


def infer_schema(*dfs):
    """Devuelve un DataFrame con Columna, Tipo detectado, Tipo de dato y Ejemplo
    para la unión de columnas de los DataFrames recibidos."""
    columns, seen = [], set()
    for df in dfs:
        for c in df.columns:
            if c not in seen:
                seen.add(c)
                columns.append(c)
    rows = []
    for col in columns:
        series = pd.concat([df[col] for df in dfs if col in df.columns], ignore_index=True)
        tipo = infer_column_type(col, series)
        ejemplos = series.dropna().astype(str)
        ejemplos = ejemplos[ejemplos.str.strip() != ""].head(3).tolist()
        rows.append({
            "Columna": col,
            "Tipo detectado": tipo,
            "Tipo de dato": tipo,
            "Ejemplos": " | ".join(ejemplos),
            "Vacíos": int(series.isna().sum()),
        })
    return pd.DataFrame(rows)


def decimal_styles(schema, *dfs):
    """Separador decimal por columna, deducido con los datos de todos los archivos."""
    out = {}
    for col, tipo in schema.items():
        if tipo not in (ENTERO, DECIMAL):
            continue
        series = [df[col] for df in dfs if col in df.columns]
        if series:
            out[col] = column_decimal_style(pd.concat(series, ignore_index=True))
    return out


def _normalize_email(value):
    if pd.isna(value):
        return pd.NA
    s = str(value).strip().replace(" ", "")
    if s.lower().startswith("mailto:"):
        s = s[7:]
    if "@" in s:
        local, domain = s.rsplit("@", 1)
        s = f"{local}@{domain.lower()}"
    return s


def apply_schema(df, schema, styles=None):
    """Aplica un mapeo {columna: tipo}. Devuelve (df_tipado, reporte).
    El reporte es un DataFrame con los valores que no se pudieron convertir.

    `styles` indica, por columna, qué símbolo es el separador decimal. Conviene
    calcularlo sobre todos los archivos a la vez (con `decimal_styles`) para que
    la misma columna se interprete igual en ambos."""
    styles = styles or {}
    out = df.copy()
    report = []
    for col, tipo in schema.items():
        if col not in out.columns:
            continue
        original = out[col]
        present = original.notna() & (original.astype("string").str.strip() != "")
        if tipo == IDENTIFICADOR:
            converted = original.astype("string").str.strip()
            invalid = pd.Series(False, index=original.index)
        elif tipo == TEXTO:
            converted = original.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
            invalid = pd.Series(False, index=original.index)
        elif tipo == EMAIL:
            converted = original.map(_normalize_email).astype("string")
            invalid = present & ~converted.fillna("").str.match(EMAIL_RE)
        elif tipo in (ENTERO, DECIMAL):
            style = styles.get(col) or column_decimal_style(original)
            nums = pd.to_numeric(original.map(lambda v: parse_number(v, style)), errors="coerce")
            if tipo == ENTERO:
                not_int = nums.notna() & (nums % 1 != 0)
                converted = nums.where(~not_int).round().astype("Int64")
                invalid = present & (nums.isna() | not_int)
            else:
                converted = nums.astype("float64")
                invalid = present & nums.isna()
        elif tipo == FECHA:
            converted = parse_dates(original)
            invalid = present & converted.isna()
        elif tipo == BOOLEANO:
            low = original.astype("string").str.strip().str.lower()
            converted = pd.Series(pd.NA, index=original.index, dtype="boolean")
            converted[low.isin(_TRUE).fillna(False)] = True
            converted[low.isin(_FALSE - {""}).fillna(False)] = False
            invalid = present & converted.isna()
        else:
            continue

        n_invalid = int(invalid.sum())
        if n_invalid:
            ejemplos = original[invalid].astype(str).head(5).tolist()
            if tipo == EMAIL:
                accion = "Se conservan tal cual, pero no tienen formato de correo válido."
            else:
                accion = "Quedarán vacíos. Si desea conservarlos, asigne el tipo «Texto» o «Identificador»."
            report.append({
                "Columna": col,
                "Tipo asignado": tipo,
                "Valores no válidos": n_invalid,
                "Ejemplos": " | ".join(ejemplos),
                "Qué pasará": accion,
                "Filas": invalid[invalid].index.tolist(),
            })
        out[col] = converted
    return out, pd.DataFrame(report, columns=["Columna", "Tipo asignado", "Valores no válidos", "Ejemplos", "Qué pasará", "Filas"])
