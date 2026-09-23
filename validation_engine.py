import pandas as pd

def validate_nulls(df: pd.DataFrame):
    return df.isnull().sum().reset_index(name="nulos").rename(columns={"index": "columna"})

def validate_duplicates(df: pd.DataFrame, keys):
    if not keys:
        return pd.DataFrame()
    return df[df.duplicated(subset=keys, keep=False)]

def validate_types(df: pd.DataFrame):
    return pd.DataFrame({
        "columna": df.columns,
        "tipo": df.dtypes.astype(str)
    })

def data_quality_score(df: pd.DataFrame):
    total = df.size
    if total == 0:
        return 0.0
    nulls = df.isnull().sum().sum()
    return round(100 * (1 - nulls / total), 2)

