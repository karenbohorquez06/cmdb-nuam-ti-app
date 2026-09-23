"""Utilidades de comparación fina de texto: similitud (Levenshtein / Jaro-Winkler),
clasificación del tipo de diferencia y resaltado a nivel de carácter."""
import html
import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd

LEVENSHTEIN = "Levenshtein"
JARO_WINKLER = "Jaro-Winkler"
ALGORITMOS = [JARO_WINKLER, LEVENSHTEIN]

# Tipos de diferencia
SIN_DIFERENCIA = "Sin diferencia"
MAYUSCULAS = "Mayúsculas/minúsculas"
TILDES = "Tildes/acentos"
MAYUS_TILDES = "Mayúsculas y tildes"
ESPACIOS = "Espacios en blanco"
FORMATO_TEXTO = "Formato de texto (espacios, mayúsculas, tildes)"
FORMATO_FECHA = "Formato de fecha/hora"
FECHA_DISTINTA = "Fecha distinta"
NUM_TOLERANCIA = "Numérico dentro de tolerancia"
NUM_DISTINTO = "Numérico distinto"
FALTANTE = "Valor faltante en un archivo"
TEXTO_DISTINTO = "Texto distinto"

# Tipos que son solo cosméticos (no cambian el dato real)
TIPOS_COSMETICOS = {MAYUSCULAS, TILDES, MAYUS_TILDES, ESPACIOS, FORMATO_TEXTO,
                    FORMATO_FECHA, NUM_TOLERANCIA}


def strip_accents(text):
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return text
    return "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))


def collapse_spaces(text):
    return re.sub(r"\s+", " ", str(text)).strip()


# ---------------------------------------------------------------------------
# Similitud
# ---------------------------------------------------------------------------
def levenshtein_distance(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def levenshtein_ratio(a, b):
    """Similitud 0..1 basada en la distancia de edición."""
    a, b = str(a), str(b)
    longest = max(len(a), len(b))
    if longest == 0:
        return 1.0
    return 1 - levenshtein_distance(a, b) / longest


def jaro(a, b):
    a, b = str(a), str(b)
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0
    window = max(la, lb) // 2 - 1
    if window < 0:
        window = 0
    a_flags, b_flags = [False] * la, [False] * lb
    matches = 0
    for i, ca in enumerate(a):
        for j in range(max(0, i - window), min(lb, i + window + 1)):
            if not b_flags[j] and b[j] == ca:
                a_flags[i] = b_flags[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    transpositions, k = 0, 0
    for i in range(la):
        if a_flags[i]:
            while not b_flags[k]:
                k += 1
            if a[i] != b[k]:
                transpositions += 1
            k += 1
    transpositions //= 2
    return (matches / la + matches / lb + (matches - transpositions) / matches) / 3


def jaro_winkler(a, b, scaling=0.1):
    base = jaro(a, b)
    prefix = 0
    for ca, cb in zip(str(a)[:4], str(b)[:4]):
        if ca != cb:
            break
        prefix += 1
    return base + prefix * scaling * (1 - base)


def similarity(a, b, algoritmo=JARO_WINKLER):
    a = "" if a is None or pd.isna(a) else str(a)
    b = "" if b is None or pd.isna(b) else str(b)
    if algoritmo == LEVENSHTEIN:
        return levenshtein_ratio(a, b)
    return jaro_winkler(a, b)


# ---------------------------------------------------------------------------
# Clasificación del tipo de diferencia
# ---------------------------------------------------------------------------
def _as_text(value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d %H:%M:%S") if (value.hour or value.minute or value.second) \
            else value.strftime("%Y-%m-%d")
    return str(value)


def _as_number(value):
    if isinstance(value, bool):
        return None
    try:
        num = pd.to_numeric(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(num) else float(num)


def _as_date(value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.tz_localize(None) if value.tzinfo else value
    text = str(value).strip()
    if not re.search(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}", text):
        return None
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True, format="mixed")
    if pd.isna(parsed):
        return None
    return parsed.tz_localize(None) if parsed.tzinfo else parsed


def classify_difference(a, b, numeric_tolerance=0.0, date_tolerance=True, algoritmo=JARO_WINKLER):
    """Devuelve (tipo_de_diferencia, similitud 0..1) para un par de valores."""
    ta, tb = _as_text(a), _as_text(b)
    if ta is None and tb is None:
        return SIN_DIFERENCIA, 1.0
    if ta is None or tb is None:
        return FALTANTE, 0.0
    if ta == tb:
        return SIN_DIFERENCIA, 1.0

    na, nb = _as_number(a), _as_number(b)
    if na is not None and nb is not None:
        delta = abs(na - nb)
        if delta == 0:
            return SIN_DIFERENCIA, 1.0
        if numeric_tolerance and delta <= numeric_tolerance:
            return NUM_TOLERANCIA, 1.0
        return NUM_DISTINTO, similarity(ta, tb, algoritmo)

    da, db = _as_date(a), _as_date(b)
    if da is not None and db is not None:
        if da == db:
            return FORMATO_FECHA, 1.0
        if date_tolerance and da.date() == db.date():
            return FORMATO_FECHA, 1.0
        return FECHA_DISTINTA, similarity(ta, tb, algoritmo)

    sa, sb = collapse_spaces(ta), collapse_spaces(tb)
    if sa == sb:
        return ESPACIOS, 1.0
    if sa.lower() == sb.lower():
        return MAYUSCULAS, 1.0
    aa, ab = strip_accents(sa), strip_accents(sb)
    if aa == ab:
        return TILDES, 1.0
    if aa.lower() == ab.lower():
        return MAYUS_TILDES, 1.0
    if strip_accents(ta).lower() == strip_accents(tb).lower():
        return FORMATO_TEXTO, 1.0
    return TEXTO_DISTINTO, similarity(ta, tb, algoritmo)


# ---------------------------------------------------------------------------
# Resaltado a nivel de carácter
# ---------------------------------------------------------------------------
def _escape(text):
    return html.escape(text).replace(" ", "&nbsp;")


def char_diff_html(a, b, css_del="diff-del", css_ins="diff-ins"):
    """Devuelve (html_a, html_b) marcando los caracteres que cambian."""
    ta = _as_text(a) or ""
    tb = _as_text(b) or ""
    matcher = SequenceMatcher(None, ta, tb, autojunk=False)
    out_a, out_b = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        frag_a, frag_b = _escape(ta[i1:i2]), _escape(tb[j1:j2])
        if tag == "equal":
            out_a.append(frag_a)
            out_b.append(frag_b)
        else:
            if frag_a:
                out_a.append(f'<span class="{css_del}">{frag_a}</span>')
            if frag_b:
                out_b.append(f'<span class="{css_ins}">{frag_b}</span>')
    vacio = '<span class="diff-empty">(vacío)</span>'
    return ("".join(out_a) or vacio, "".join(out_b) or vacio)
