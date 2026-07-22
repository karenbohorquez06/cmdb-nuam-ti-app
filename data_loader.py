import pandas as pd

def read_file(uploaded_file):
    if uploaded_file.name.lower().endswith(".csv"):
        return pd.read_csv(uploaded_file, sep=None, engine='python')
    return pd.read_excel(uploaded_file)