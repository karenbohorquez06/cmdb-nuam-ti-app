import pandas as pd
import io

def generate_profile(df: pd.DataFrame):
    data = []
    for col in df.columns:
        data.append({
            "columna": col,
            "tipo": str(df[col].dtype),
            "nulos": df[col].isnull().sum(),
            "unicos": df[col].nunique()
        })
    return pd.DataFrame(data)

def to_excel(sheets: dict):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return buffer.getvalue()