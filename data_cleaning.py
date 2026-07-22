import re
import unicodedata
import pandas as pd


def _normalize_text(value):
    if pd.isna(value):
        return value

    text = str(value).strip()
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Za-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.title()


def normalize_text_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].apply(_normalize_text)

    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # limpiar nombres columnas
    df.columns = df.columns.str.strip()

    # limpiar strings
    for col in df.select_dtypes(include="object"):
        df[col] = df[col].astype(str).str.strip().str.lower()

    # eliminar duplicados
    df = df.drop_duplicates()

    return df