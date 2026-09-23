"""Componentes visuales reutilizables (tarjetas, tablas con color, gráficos y errores).

No conocen el estado del asistente: reciben todo por parámetro, así que pueden
usarse desde cualquier paso.
"""
import html as html_lib

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_loader as dl
from ui.styles import AMARILLO_FONDO, CELDA_ROJA, ROJO_FONDO, VERDE_FONDO

def show_error(exc, context="procesar la información"):
    """Muestra un error en lenguaje natural."""
    message, suggestion = dl.friendly_message(exc, context)
    st.error(f"**{message}**\n\n{suggestion or ''}")


def show_file_warnings(warnings):
    for w in sorted(warnings, key=lambda w: ["error", "warning", "info"].index(w["nivel"])):
        text = f"**{w['titulo']}.** {w['detalle']}"
        if w["nivel"] == "error":
            st.error(text)
        elif w["nivel"] == "warning":
            st.warning(text)
        else:
            st.caption(text)


def metric_card(value, label, color=None, help=None):
    style = f' style="color: {color}"' if color else ""
    tip = f' title="{html_lib.escape(help)}"' if help else ""
    st.markdown(f"""
<div class="metric-card"{tip}>
<div class="metric-value"{style}>{value}</div>
<div class="metric-label">{label}</div>
</div>""", unsafe_allow_html=True)


def quality_color(score):
    return "#28a745" if score >= 90 else "#ffc107" if score >= 70 else "#dc3545"


def quality_gauge(score, key):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={'text': "Score de Calidad"},
        domain={'x': [0, 1], 'y': [0, 1]},
        gauge={'axis': {'range': [None, 100]},
               'bar': {'color': "#FF4201"},
               'steps': [
                   {'range': [0, 70], 'color': ROJO_FONDO},
                   {'range': [70, 90], 'color': AMARILLO_FONDO},
                   {'range': [90, 100], 'color': VERDE_FONDO}],
               'threshold': {'line': {'color': "red", 'width': 4},
                             'thickness': 0.75, 'value': score}}))
    fig.update_layout(height=280, margin=dict(t=50, b=10))
    st.plotly_chart(fig, width="stretch", key=key)


MAX_STYLED_ROWS = 3000


def styled(df, cell_mask=None, row_colors=None, cell_css=CELDA_ROJA):
    """Aplica colores a un DataFrame: celdas con incoherencias en rojo
    (`cell_mask`) y color de fondo por fila (`row_colors`, Serie de colores)."""
    df = df.head(MAX_STYLED_ROWS)

    def _css(_):
        css = pd.DataFrame("", index=df.index, columns=df.columns)
        if row_colors is not None:
            rc = row_colors.reindex(df.index).fillna("")
            for col in df.columns:
                css[col] = [f"background-color: {c}" if c else "" for c in rc]
        if cell_mask is not None:
            m = cell_mask.reindex(index=df.index, columns=df.columns).fillna(False).astype(bool)
            css = css.mask(m, cell_css)
        return css

    fmt = {c: (lambda v: "" if pd.isna(v) else v.strftime("%Y-%m-%d"))
           for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])}
    return df.style.apply(_css, axis=None).format(fmt, na_rep="")


def styled_note(df):
    if len(df) > MAX_STYLED_ROWS:
        st.caption(f"Se muestran con color las primeras {MAX_STYLED_ROWS:,} filas de {len(df):,}. "
                   "Descargue el archivo para ver todas.")


def table_height(n_rows, max_height=420):
    return min(max_height, 36 * (n_rows + 1) + 3)


def csv_bytes(df, index=False):
    # utf-8-sig para que Excel muestre bien tildes, ñ y correos.
    return df.to_csv(index=index).encode("utf-8-sig")
