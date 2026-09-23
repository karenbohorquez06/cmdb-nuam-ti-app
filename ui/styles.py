"""Paleta de colores y hoja de estilos de la aplicación.

Mantener el CSS aquí evita que app.py cargue con más de cien líneas de estilos
y permite reutilizar los colores desde los componentes.
"""
import streamlit as st

ROJO_FONDO = "#f8d7da"
ROJO_TEXTO = "#842029"
ROJO_FUERTE = "#f1aeb5"
AMARILLO_FONDO = "#fff3cd"
VERDE_FONDO = "#d1e7dd"

# Resaltado de una celda con diferencias o incoherencias.
CELDA_ROJA = f"background-color: {ROJO_FUERTE}; color: {ROJO_TEXTO}; font-weight: 600"

CSS = """<style>
    .stApp { overflow-x: hidden; }
    /* Header principal */
    .main-header {
        background: linear-gradient(135deg, #FF4201 0%, #FF4201 100%);
        padding: 2rem;
        border-radius: 15px;
        margin-bottom: 1.5rem;
        color: white;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    /* Tarjetas de métricas */
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 15px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        transition: transform 0.3s ease;
        text-align: center;
        width: 100%;
        box-sizing: border-box;
        min-height: 130px;
    }
    .metric-card:hover { transform: translateY(-3px); }
    .metric-value { font-size: 2rem; font-weight: bold; color: #FF4201; }
    .metric-label { font-size: 0.9rem; color: #6c757d; margin-top: 0.5rem; }
    .alert-card {
        background: white;
        border-radius: 15px;
        border: 1px solid rgba(0,0,0,0.08);
        box-shadow: 0 5px 15px rgba(0,0,0,0.06);
        padding: 1.3rem;
        text-align: center;
        width: 100%;
        box-sizing: border-box;
        min-height: 130px;
    }
    .alert-card.error { border-color: #dc3545; }
    .alert-card.warning { border-color: #ffc107; }
    .alert-card .metric-value { font-size: 2rem; font-weight: bold; margin-bottom: 0.25rem; }
    .alert-card.error .metric-value { color: #dc3545; }
    .alert-card.warning .metric-value { color: #856404; }
    .alert-card .metric-label { color: #6c757d; font-size: 0.95rem; }
    .validation-pass {
        background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%);
        color: #155724;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        font-weight: bold;
    }
    /* Botones */
    .stButton > button, .stDownloadButton > button {
        border-radius: 25px;
        font-weight: bold;
    }
    .stButton > button[kind="primary"] {
        background: #FF4201;
        border-color: #FF4201;
        color: white;
    }
    /* Wizard */
    .wizard { display: flex; gap: .5rem; margin: 0 0 1.5rem 0; flex-wrap: wrap; }
    .wizard-step {
        flex: 1 1 160px; display: flex; align-items: center; gap: .6rem;
        padding: .7rem 1rem; border-radius: 12px; background: #f1f3f5; color: #6c757d;
        border: 2px solid transparent; font-weight: 600;
    }
    .wizard-step .num {
        width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center;
        justify-content: center; background: #dee2e6; color: #495057; flex-shrink: 0;
    }
    .wizard-step.done { background: #fff1eb; color: #b53000; }
    .wizard-step.done .num { background: #FF4201; color: white; }
    .wizard-step.active { background: white; border-color: #FF4201; color: #212529; box-shadow: 0 4px 12px rgba(255,66,1,.15); }
    .wizard-step.active .num { background: #FF4201; color: white; }
    .wizard-step small { display: block; font-weight: 400; font-size: .75rem; color: #6c757d; }
    .legend-chip { display: inline-block; padding: .15rem .6rem; border-radius: 8px; margin-right: .5rem;
        margin-bottom: .3rem; font-size: .85rem; cursor: help; border: 1px solid rgba(0,0,0,.08); }
    /* Indicador de inclusión */
    .inclusion-card { border-radius: 15px; padding: 1.2rem 1.5rem; margin: .5rem 0 1rem 0; background: white;
        border-left: 8px solid #6c757d; box-shadow: 0 5px 15px rgba(0,0,0,.06); }
    .inclusion-card.ok { border-left-color: #28a745; }
    .inclusion-card.partial { border-left-color: #ffc107; }
    .inclusion-card.ko { border-left-color: #dc3545; }
    .inclusion-title { font-size: .95rem; color: #6c757d; }
    .inclusion-answer { font-size: 2.2rem; font-weight: bold; line-height: 1.1; }
    .inclusion-card.ok .inclusion-answer { color: #28a745; }
    .inclusion-card.partial .inclusion-answer { color: #b58100; }
    .inclusion-card.ko .inclusion-answer { color: #dc3545; }
    .inclusion-detail { color: #495057; font-size: .9rem; margin-top: .3rem; }
    /* Diferencias a nivel de carácter */
    .diff-table { width: 100%; border-collapse: collapse; font-size: .88rem; }
    .diff-table th { text-align: left; background: #f1f3f5; padding: .45rem .6rem; position: sticky; top: 0; }
    .diff-table td { padding: .45rem .6rem; border-top: 1px solid #e9ecef; vertical-align: top; }
    .diff-cell { font-family: ui-monospace, "Cascadia Code", Consolas, monospace; white-space: pre-wrap; }
    .diff-del { background: #f1aeb5; color: #842029; border-radius: 3px; text-decoration: line-through; }
    .diff-ins { background: #a7dfb9; color: #0f5132; border-radius: 3px; font-weight: 600; }
    .diff-empty { color: #adb5bd; font-style: italic; }
</style>"""


def inject_css():
    """Inyecta la hoja de estilos en la página. Llamar una sola vez, al inicio."""
    st.markdown(CSS, unsafe_allow_html=True)
