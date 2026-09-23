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


def normalize_text_data(df: pd.DataFrame, schema: dict = None) -> pd.DataFrame:
    """Normaliza el texto libre. Si se recibe `schema` ({columna: tipo} de
    schema_mapper), solo se normalizan las columnas de tipo Texto; correos,
    identificadores, números y fechas se conservan tal cual."""
    df = df.copy()
    if schema is not None:
        from schema_mapper import TEXTO
        for col, tipo in schema.items():
            if col in df.columns and tipo == TEXTO:
                df[col] = df[col].apply(_normalize_text)
        return df

    # Helpers to detect ID/KEY and email columns
    def _is_id_column(name: str) -> bool:
        if not name:
            return False
        name_l = str(name).lower()
        # split on non-alphanumeric to get tokens
        tokens = re.split(r'[^a-z0-9]+', name_l)
        id_keywords = {'id', 'key', 'identificador', 'ident', 'codigo', 'code', 'uuid', 'serial', 'serialnumber', 'serial_number'}
        for t in tokens:
            if not t:
                continue
            if t in id_keywords:
                return True
            # catch patterns like account_id, id_user, user-id
            if t.endswith('id') or t.endswith('key'):
                return True
        return False

    def _is_email_column(name: str) -> bool:
        if not name:
            return False
        name_l = str(name).lower()
        tokens = re.split(r'[^a-z0-9]+', name_l)
        email_keywords = {'email', 'e-mail', 'correo', 'correo_electronico', 'mail'}
        for t in tokens:
            if not t:
                continue
            if t in email_keywords or 'email' in t or 'correo' in t or t == 'mail':
                return True
        return False

    # Simple but permissive email regex that allows +, -, _, . in local-part
    email_regex = re.compile(r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$')

    for col in df.columns:
        # Only operate on object/string columns
        if not (pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col])):
            continue

        if _is_id_column(col):
            # ID/KEY columns: preserve internal characters but trim surrounding whitespace
            df[col] = df[col].apply(lambda v: v if pd.isna(v) else str(v).strip())
            continue

        if _is_email_column(col):
            # Email columns: normalize to a valid-looking email when possible, without adding extra columns
            def _normalize_email(v):
                if pd.isna(v):
                    return v
                s = str(v).strip()
                # remove stray spaces inside the email
                s = s.replace(' ', '')
                # if no @ present, return trimmed original
                if '@' not in s:
                    return s
                local, domain = s.split('@', 1)
                # keep allowed characters in local-part, remove others
                local = re.sub(r'[^A-Za-z0-9._%+\-]', '', local)
                # keep allowed characters in domain, remove others
                domain = re.sub(r'[^A-Za-z0-9.\-]', '', domain)
                domain = domain.strip('.')
                domain = domain.lower()
                candidate = f"{local}@{domain}"
                # if candidate matches email pattern, use it; else keep trimmed original
                if email_regex.match(candidate):
                    return candidate
                return s

            df[col] = df[col].apply(_normalize_email)
            continue

        # Default: apply existing normalization
        df[col] = df[col].apply(_normalize_text)

    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Limpieza estructural sin alterar el contenido: nombres de columna sin
    espacios, textos sin espacios al inicio/fin, sin filas totalmente vacías ni
    duplicadas. No cambia mayúsculas/minúsculas (eso se decide al comparar) ni
    convierte vacíos en el texto "nan"."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            stripped = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)
            df[col] = stripped.mask(stripped.map(lambda v: isinstance(v, str) and v == ""))

    df = df.dropna(how="all")
    df = df.drop_duplicates()
    return df
