import streamlit as st
import pandas as pd
import re
from datetime import datetime, date
from data_loader import read_file
import data_cleaning as dc
import importlib
importlib.reload(dc)
from validation_engine import *
from comparator import compare_dataframes
from reporting import *
from database import init_db
import plotly.express as px
import plotly.graph_objects as go
 
# Configuración de página
st.set_page_config(
    layout="wide",
    page_title="CMDB Quality Platform",
    page_icon="",
    initial_sidebar_state="expanded"
)
 
# Inicializar base de datos
db = init_db()
 
# Estilos CSS mejorados
st.markdown("""
<style>
    /* Estilos generales */
    .stApp {
        
    }
    .main-container {
        background-color: white;
        border-radius: 15px;
        padding: 20px;
        margin-top: 20px;
        width: 100%;
        max-width: 100%;
        box-sizing: border-box;
    }
    .stApp {
        overflow-x: hidden;
    }
    /* Header principal */
    .main-header {
        background: linear-gradient(135deg, #FF4201 0%, #FF4201 100%);
        padding: 2rem;
        border-radius: 15px;
        margin-bottom: 2rem;
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
        min-height: 140px;
    }
    .metric-card:hover {
        transform: translateY(-3px);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: #FF4201;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #6c757d;
        margin-top: 0.5rem;
    }
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
    .alert-card.error {
        border-color: #dc3545;
    }
    .alert-card.warning {
        border-color: #ffc107;
    }
    .alert-card .metric-value {
        font-size: 2rem;
        font-weight: bold;
        margin-bottom: 0.25rem;
    }
    .alert-card.error .metric-value {
        color: #dc3545;
    }
    .alert-card.warning .metric-value {
        color: #856404;
    }
    .alert-card .metric-label {
        color: #6c757d;
        font-size: 0.95rem;
    }
    /* Validaciones */
    .validation-pass {
        background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%);
        color: #155724;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        font-weight: bold;
    }
    .validation-fail {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .validation-warning {
        background: linear-gradient(135deg, #ffe259 0%, #ffa751 100%);
        color: #856404;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    /* Botones */
    .stButton > button {
        background: linear-gradient(135deg, #FF4201 0%, #FF4201 100%);
        color: white;
        border: none;
        padding: 0.6rem 1.5rem;
        border-radius: 25px;
        font-weight: bold;
        transition: all 0.3s ease;
        width: 100%;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 20px rgba(0,0,0,0.2);
    }
    /* Sidebar */
    .css-1d391kg {
        background: linear-gradient(180deg, #2c3e50 0%, #3498db 100%);
    }
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
        background-color: white;
        padding: 0.5rem;
        border-radius: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 0.5rem 1rem;
        font-weight: bold;
    }
    /* DataFrames */
    .dataframe {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)
 
# Header
st.markdown("""
<div class="main-header">
<h1>🏢 CMDB Quality Platform</h1>
<p>Plataforma integral de calidad de datos para infraestructura TI</p>
</div>
""", unsafe_allow_html=True)
 
# Sidebar
with st.sidebar:
    st.markdown("###  Configuración")
    esquema = st.selectbox(
        " Esquema a validar:",
        ["Licencias TI", "Dominios", "Certificados", "General"],
        help="Seleccione el tipo de esquema para aplicar reglas específicas"
    )
    modo = st.radio(
        "Modo de análisis:",
        ["Comparar archivos", "Validar archivo único", "Limpiar archivo"],
        index=0,
        help="Seleccione si desea comparar archivos, validar uno o limpiar texto de un archivo"
    )

    # Histórico
    with st.expander(" Histórico de Validaciones", expanded=False):
        historico = db.obtener_historicos(5)
        if not historico.empty:
            st.dataframe(historico[['fecha_validacion', 'esquema', 'score_calidad']], use_container_width=True)
    st.markdown("--")
 
# Función de validación para Licencias TI (con integridad referencial)
def validate_licencias(df, db):
    errors = []
    warnings = []
    # Obtener datos de referencia
    proveedores_validos = set(db.obtener_proveedores())
    aplicaciones_validas = set(db.obtener_aplicaciones())
    usuarios_validos = {u['email'] for u in db.obtener_usuarios()}
    # Listas de valores permitidos
    paises_permitidos = ['Colombia', 'Perú', 'Chile', 'tranversal']
    tipo_lic_permitidos = ['Hardware', 'Software', 'Soporte', 'Nube']
    tipo_vigencia_permitidos = ['Activo', 'Por Renovar', 'Por vencer', 'Vencido', 'Inactivo']
    tipo_usuario_permitidos = ['Equipos de Computo', 'Celulares', 'Personas', 'Cuentas']
    tipo_entorno_permitidos = ['Producción', 'Pruebas', 'Certificación', 'Todos los Anteriores', 'No Aplica']
    estado_permitidos = ['Vigente', 'Vencida', 'Finalizada']
    moneda_permitidos = ['USD', 'UF', 'COP', 'CLP', 'PEN', 'EUR', 'Varias monedas']
    for idx, row in df.iterrows():
        # Validar Proveedor (Integridad Referencial)
        if pd.notna(row.get('Proveedor')):
            if row['Proveedor'] not in proveedores_validos:
                errors.append(f"Fila {idx}: Proveedor '{row['Proveedor']}' no existe en la base de datos maestra")
        # Validar Producto asociado
        if pd.notna(row.get('Producto asociado')):
            if row['Producto asociado'] not in aplicaciones_validas:
                warnings.append(f"Fila {idx}: Producto asociado '{row['Producto asociado']}' no existe en aplicaciones")
        # Validar Responsable/Correo
        if pd.notna(row.get('Responsable / Correo')):
            if row['Responsable / Correo'] not in usuarios_validos:
                warnings.append(f"Fila {idx}: Responsable '{row['Responsable / Correo']}' no existe en usuarios")
            else:
                # Validar formato de email
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_pattern, str(row['Responsable / Correo'])):
                    warnings.append(f"Fila {idx}: Formato de correo inválido: {row['Responsable / Correo']}")
        # Validar País
        if pd.notna(row.get('Pais')) and row['Pais'] not in paises_permitidos:
            errors.append(f"Fila {idx}: País '{row['Pais']}' no permitido")
        # Validar cantidades
        if pd.notna(row.get('Cantidad Total')) and row['Cantidad Total'] < 0:
            errors.append(f"Fila {idx}: Cantidad Total no puede ser negativa")
        if pd.notna(row.get('Cantidad Asignadas')) and row['Cantidad Asignadas'] < 0:
            errors.append(f"Fila {idx}: Cantidad Asignadas no puede ser negativa")
        if all(pd.notna(row.get(col)) for col in ['Cantidad Total', 'Cantidad Asignadas']):
            if row['Cantidad Asignadas'] > row['Cantidad Total']:
                errors.append(f"Fila {idx}: Cantidad Asignadas ({row['Cantidad Asignadas']}) > Cantidad Total ({row['Cantidad Total']})")
            disponible_esperado = row['Cantidad Total'] - row['Cantidad Asignadas']
            if pd.notna(row.get('Cantidad Disponible')):
                if abs(row['Cantidad Disponible'] - disponible_esperado) > 0.01:
                    warnings.append(f"Fila {idx}: Cantidad Disponible ({row['Cantidad Disponible']}) no coincide con cálculo ({disponible_esperado})")
        # Validar fechas
        if all(pd.notna(row.get(col)) for col in ['Fecha Compra', 'Fecha Vencimiento']):
            try:
                fecha_compra = pd.to_datetime(row['Fecha Compra'])
                fecha_vencimiento = pd.to_datetime(row['Fecha Vencimiento'])
                if fecha_compra > fecha_vencimiento:
                    errors.append(f"Fila {idx}: Fecha Compra es posterior a Fecha Vencimiento")
            except:
                warnings.append(f"Fila {idx}: Formato de fecha inválido")
        # Validar URL
        if pd.notna(row.get('Enlace Contrato')):
            url_pattern = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
            if not re.match(url_pattern, str(row['Enlace Contrato'])):
                warnings.append(f"Fila {idx}: URL inválida: {row['Enlace Contrato']}")
    return errors, warnings
 
# Función de validación para Dominios
def validate_dominios(df, db):
    errors = []
    warnings = []
    proveedores_validos = set(db.obtener_proveedores())
    aplicaciones_validas = set(db.obtener_aplicaciones())
    usuarios_validos = {u['email'] for u in db.obtener_usuarios()}
    paises_permitidos = ['Colombia', 'Perú', 'Chile']
    tipo_vigencia_permitidos = ['Anual', 'semestral', 'Mensual']
    entorno_permitidos = ['Producción', 'Pruebas', 'Certificación', 'Todos los Anteriores', 'No Aplica']
    estado_permitidos = ['Activo', 'Por Renovar', 'Por vencer', 'Vencido', 'Inactivo']
    for idx, row in df.iterrows():
        # Validar dominio
        if pd.notna(row.get('Dominio')):
            domain_pattern = r'^([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$'
            if not re.match(domain_pattern, str(row['Dominio'])):
                errors.append(f"Fila {idx}: Formato de dominio inválido: {row['Dominio']}")
        # Validar proveedor
        if pd.notna(row.get('Proveedor del dominio')):
            if row['Proveedor del dominio'] not in proveedores_validos:
                errors.append(f"Fila {idx}: Proveedor '{row['Proveedor del dominio']}' no existe en maestros")
        # Validar activo asociado
        if pd.notna(row.get('Activo Asociado')):
            if row['Activo Asociado'] not in aplicaciones_validas:
                warnings.append(f"Fila {idx}: Activo Asociado '{row['Activo Asociado']}' no existe")
        # Validar responsable
        if pd.notna(row.get('Responsable TI')):
            if row['Responsable TI'] not in usuarios_validos:
                warnings.append(f"Fila {idx}: Responsable TI '{row['Responsable TI']}' no existe")
        # Validar país
        if pd.notna(row.get('Pais')) and row['Pais'] not in paises_permitidos:
            errors.append(f"Fila {idx}: País '{row['Pais']}' no permitido")
        # Validar fechas
        if all(pd.notna(row.get(col)) for col in ['Fecha Inicio / Vencimiento', 'Fecha Vencimiento']):
            try:
                fecha_inicio = pd.to_datetime(row['Fecha Inicio / Vencimiento'])
                fecha_vencimiento = pd.to_datetime(row['Fecha Vencimiento'])
                if fecha_inicio > fecha_vencimiento:
                    errors.append(f"Fila {idx}: Fecha Inicio es posterior a Fecha Vencimiento")
            except:
                warnings.append(f"Fila {idx}: Formato de fecha inválido")
    return errors, warnings
 
# Función de validación para Certificados
def validate_certificados(df, db):
    errors = []
    warnings = []
    aplicaciones_validas = set(db.obtener_aplicaciones())
    tipo_certificado_permitidos = ['OV', 'EV', 'Firma Digital', 'Interno']
    tipo_vigencia_permitidos = ['Anual', 'Mensual', 'Vitalicia']
    estado_permitidos = ['Activo', 'Por Renovar', 'Por vencer', 'Vencido', 'Inactivo']
    today = datetime.now().date()
    for idx, row in df.iterrows():
        # Validar activo asociado
        if pd.notna(row.get('Activo asociado')):
            if row['Activo asociado'] not in aplicaciones_validas:
                warnings.append(f"Fila {idx}: Activo asociado '{row['Activo asociado']}' no existe")
        # Validar tipo de certificado
        if pd.notna(row.get('Tipo de Certificado')) and row['Tipo de Certificado'] not in tipo_certificado_permitidos:
            errors.append(f"Fila {idx}: Tipo de Certificado '{row['Tipo de Certificado']}' no permitido")
        # Validar estado
        if pd.notna(row.get('Estado')) and row['Estado'] not in estado_permitidos:
            errors.append(f"Fila {idx}: Estado '{row['Estado']}' no permitido")
        # Calcular días restantes
        if pd.notna(row.get('Fecha Vencimiento')):
            try:
                fecha_vencimiento = pd.to_datetime(row['Fecha Vencimiento']).date()
                dias_restantes = (fecha_vencimiento - today).days
                if pd.notna(row.get('Dias Restantes')):
                    if abs(row['Dias Restantes'] - dias_restantes) > 1:
                        warnings.append(f"Fila {idx}: Días Restantes ({row['Dias Restantes']}) no coincide con cálculo ({dias_restantes})")
            except:
                warnings.append(f"Fila {idx}: Formato de fecha inválido en Fecha Vencimiento")
        # Validar URL
        if pd.notna(row.get('Enlace Certificado')):
            url_pattern = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
            if not re.match(url_pattern, str(row['Enlace Certificado'])):
                warnings.append(f"Fila {idx}: URL inválida en Enlace Certificado")
    return errors, warnings
 
# Interfaz principal
old_file = None
new_file = None
single_file = None

if modo == "Comparar archivos":
    col1, col2 = st.columns(2, gap="large")
    
    with col1:
        st.markdown("###  Datos Anteriores")
        old_file = st.file_uploader("Cargar archivo anterior", type=['csv', 'xlsx', 'xls'], key="old")
        if old_file:
            st.success(f" {old_file.name} cargado correctamente")
    
    with col2:
        st.markdown("###  Datos Nuevos")
        new_file = st.file_uploader("Cargar archivo nuevo", type=['csv', 'xlsx', 'xls'], key="new")
        if new_file:
            st.success(f" {new_file.name} cargado correctamente")

elif modo == "Validar archivo único":
    st.markdown("###  Validación de Calidad para un Solo Archivo")
    single_file = st.file_uploader("Cargar archivo único", type=['csv', 'xlsx', 'xls'], key="single")
    if single_file:
        st.success(f" {single_file.name} cargado correctamente")

if modo == "Comparar archivos" and old_file and new_file:
    try:
        with st.spinner(" Procesando archivos..."):
            # Cargar y limpiar datos
            old_df = dc.clean_data(read_file(old_file))
            new_df = dc.clean_data(read_file(new_file))
            st.markdown('<div class="main-container">', unsafe_allow_html=True)
            # Validación según esquema
            if esquema == "Licencias TI":
                errors, warnings = validate_licencias(new_df, db)
            elif esquema == "Dominios":
                errors, warnings = validate_dominios(new_df, db)
            elif esquema == "Certificados":
                errors, warnings = validate_certificados(new_df, db)
            else:
                errors, warnings = [], []
            # Mostrar resultados de validación
            if errors or warnings:
                st.markdown("###  Resultados de Validación")
                col_err, col_warn, col_view = st.columns([1, 1, 1])
                with col_err:
                    if errors:
                        st.markdown(f"""
<div class="alert-card error">
  <div class="metric-value">{len(errors)}</div>
  <div class="metric-label">Errores</div>
</div>
""", unsafe_allow_html=True)
                with col_warn:
                    if warnings:
                        st.markdown(f"""
<div class="alert-card warning">
  <div class="metric-value">{len(warnings)}</div>
  <div class="metric-label">Advertencias</div>
</div>
""", unsafe_allow_html=True)
                with col_view:
                    if st.button("Ver tabla completa", key="view_all_issues"):
                        st.session_state.show_issues_modal = True

                # Modal con tabla completa de errores y advertencias
                if st.session_state.get("show_issues_modal", False):
                    st.markdown("---")
                    st.markdown("### Tabla Completa de Errores y Advertencias")
                    
                    issues_data = []
                    for error in errors:
                        issues_data.append({"Tipo": "Error", "Detalle": error})
                    for warning in warnings:
                        issues_data.append({"Tipo": "Advertencia", "Detalle": warning})
                    
                    if issues_data:
                        issues_df = pd.DataFrame(issues_data)
                        st.dataframe(issues_df, use_container_width=True, height=400)
                        
                        # Descargar tabla como CSV
                        csv = issues_df.to_csv(index=False)
                        st.download_button(
                            "Descargar tabla de problemas",
                            csv,
                            "problemas_validacion.csv",
                            "text/csv",
                            key="download_issues"
                        )
                        
                        if st.button("Cerrar tabla", key="close_issues_modal"):
                            st.session_state.show_issues_modal = False
            else:
                st.markdown('<div class="validation-pass"> ¡Todas las validaciones pasaron correctamente!</div>', unsafe_allow_html=True)
            # Comparación de datos
            st.markdown("###  Análisis Comparativo")
            common = list(set(old_df.columns) & set(new_df.columns))
            col_keys, col_comps = st.columns(2)
            with col_keys:
                keys = st.multiselect(" Columnas clave", common, 
                                     help="Seleccione las columnas que identifican registros únicos")
            with col_comps:
                cols = st.multiselect(" Columnas a comparar", common,
                                     help="Seleccione las columnas que desea comparar")

            # Score de calidad y métricas generales
            calidad_score = data_quality_score(new_df)
            color_quality = "#28a745" if calidad_score >= 90 else "#ffc107" if calidad_score >= 70 else "#dc3545"
            
            # Mostrar métricas totales de archivos
            st.markdown("####  Resumen de Registros")
            col_total_a, col_total_b, col_calidad = st.columns(3)
            with col_total_a:
                st.markdown(f"""
<div class="metric-card">
<div class="metric-value">{len(old_df)}</div>
<div class="metric-label">Total Archivo A</div>
</div>
                """, unsafe_allow_html=True)
            with col_total_b:
                st.markdown(f"""
<div class="metric-card">
<div class="metric-value">{len(new_df)}</div>
<div class="metric-label">Total Archivo B</div>
</div>
                """, unsafe_allow_html=True)
            with col_calidad:
                st.markdown(f"""
<div class="metric-card">
<div class="metric-value" style="color: {color_quality}">{calidad_score:.0f}%</div>
<div class="metric-label"> Calidad</div>
</div>
                """, unsafe_allow_html=True)

            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=calidad_score,
                title={'text': "Score de Calidad"},
                domain={'x': [0, 1], 'y': [0, 1]},
                gauge={'axis': {'range': [None, 100]},
                       'bar': {'color': "#FF4201"},
                       'steps': [
                           {'range': [0, 70], 'color': "#f8d7da"},
                           {'range': [70, 90], 'color': "#fff3cd"},
                           {'range': [90, 100], 'color': "#d4edda"}],
                       'threshold': {'line': {'color': "red", 'width': 4},
                                     'thickness': 0.75, 'value': calidad_score}}))
            st.plotly_chart(fig, use_container_width=True, key="gauge_calidad_inicial")

            if keys and cols:
                result = compare_dataframes(old_df, new_df, keys, cols)
                
                # Calcular métricas de comparación
                total_registros_a = len(old_df)
                total_registros_b = len(new_df)
                registros_coincidentes = len(result.unchanged)
                registros_nuevos = len(result.added)
                registros_eliminados = len(result.removed)
                registros_modificados = len(result.changed)
                
                # Calcular porcentaje de coincidencia general
                total_registros_unicos = len(set(old_df.index.tolist() + new_df.index.tolist()))
                if total_registros_unicos > 0:
                    porcentaje_coincidencia = round(100 * registros_coincidentes / total_registros_unicos, 2)
                else:
                    porcentaje_coincidencia = 0
                
                # Mostrar métricas de comparación detalladas
                st.markdown("####  Análisis de Diferencias")
                col_new, col_del, col_match, col_mod = st.columns(4)
                
                color_new = "#28a745" if registros_nuevos == 0 else "#ffc107"
                color_del = "#28a745" if registros_eliminados == 0 else "#dc3545"
                color_match = "#28a745" if registros_coincidentes > 0 else "#dc3545"
                color_mod = "#28a745" if registros_modificados == 0 else "#ffc107"
                
                with col_new:
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value" style="color: {color_new}">+{registros_nuevos}</div>
<div class="metric-label">Registros Nuevos</div>
</div>
                    """, unsafe_allow_html=True)
                with col_del:
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value" style="color: {color_del}">-{registros_eliminados}</div>
<div class="metric-label">Registros Eliminados</div>
</div>
                    """, unsafe_allow_html=True)
                with col_match:
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value" style="color: {color_match}">{registros_coincidentes}</div>
<div class="metric-label">Coincidentes</div>
</div>
                    """, unsafe_allow_html=True)
                with col_mod:
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value" style="color: {color_mod}">{registros_modificados}</div>
<div class="metric-label">Modificados</div>
</div>
                    """, unsafe_allow_html=True)

                # Segunda fila de métricas - Resumen general
                st.markdown("####  Coincidencia General")
                col_coincidencia, col_resumen_a, col_resumen_b = st.columns(3)
                
                with col_coincidencia:
                    color_coincidencia = "#28a745" if porcentaje_coincidencia >= 90 else "#ffc107" if porcentaje_coincidencia >= 70 else "#dc3545"
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value" style="color: {color_coincidencia}">{porcentaje_coincidencia}%</div>
<div class="metric-label">% Coincidencia</div>
</div>
                    """, unsafe_allow_html=True)
                
                with col_resumen_a:
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value">{total_registros_a}</div>
<div class="metric-label">Registros Archivo A</div>
</div>
                    """, unsafe_allow_html=True)
                
                with col_resumen_b:
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value">{total_registros_b}</div>
<div class="metric-label">Registros Archivo B</div>
</div>
                    """, unsafe_allow_html=True)

                # Gráfico de distribución de cambios
                st.markdown("####  Distribución de Cambios")
                distribucion_data = {
                    'Coincidentes': registros_coincidentes,
                    'Nuevos': registros_nuevos,
                    'Eliminados': registros_eliminados,
                    'Modificados': registros_modificados
                }
                fig_distribucion = px.pie(
                    values=list(distribucion_data.values()),
                    names=list(distribucion_data.keys()),
                    title='Distribución de Registros',
                    color_discrete_sequence=['#28a745', '#ffc107', '#dc3545', '#17a2b8']
                )
                st.plotly_chart(fig_distribucion, use_container_width=True, key="pie_distribucion_cambios")

                # Métricas en tarjetas actualizadas (para tabs)
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value">+{registros_nuevos}</div>
<div class="metric-label">Nuevos</div>
</div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value">-{registros_eliminados}</div>
<div class="metric-label">Eliminados</div>
</div>
                    """, unsafe_allow_html=True)
                with col3:
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value">{registros_modificados}</div>
<div class="metric-label">Modificados</div>
</div>
                    """, unsafe_allow_html=True)
                with col4:
                    st.markdown(f"""
<div class="metric-card">
<div class="metric-value" style="color: {color_quality}">{calidad_score:.0f}%</div>
<div class="metric-label"> Calidad</div>
</div>
                    """, unsafe_allow_html=True)

                tab1, tab2, tab3, tab4 = st.tabs([
                    " Registros Nuevos", " Registros Eliminados", " Registros Modificados", " Estadísticas"
                ])
                with tab1:
                    if not result.added.empty:
                        st.markdown(f"**Total: {len(result.added)} registros nuevos**")
                        st.dataframe(result.added, use_container_width=True)
                        csv = result.added.to_csv(index=False)
                        st.download_button(" Descargar CSV", csv, "registros_nuevos.csv", "text/csv")
                    else:
                        st.info("No se encontraron registros nuevos")
                with tab2:
                    if not result.removed.empty:
                        st.markdown(f"**Total: {len(result.removed)} registros eliminados**")
                        st.dataframe(result.removed, use_container_width=True)
                        csv = result.removed.to_csv(index=False)
                        st.download_button(" Descargar CSV", csv, "registros_eliminados.csv", "text/csv")
                    else:
                        st.info("No se encontraron registros eliminados")
                with tab3:
                    if not result.changed.empty:
                        st.markdown(f"**Total: {len(result.changed)} registros modificados**")
                        st.dataframe(result.changed, use_container_width=True)
                        csv = result.changed.to_csv(index=False)
                        st.download_button(" Descargar CSV", csv, "registros_modificados.csv", "text/csv")
                    else:
                        st.info("No se encontraron registros modificados")
                with tab4:
                    st.markdown("**Estadísticas Detalladas**")
                    
                    # Tabla resumen
                    resumen_stats = pd.DataFrame({
                        "Métrica": [
                            "Total Archivo A",
                            "Total Archivo B",
                            "Registros Coincidentes",
                            "Registros Nuevos",
                            "Registros Eliminados",
                            "Registros Modificados",
                            "% Coincidencia General"
                        ],
                        "Valor": [
                            f"{total_registros_a}",
                            f"{total_registros_b}",
                            f"{registros_coincidentes}",
                            f"{registros_nuevos}",
                            f"{registros_eliminados}",
                            f"{registros_modificados}",
                            f"{porcentaje_coincidencia}%"
                        ]
                    })
                    st.dataframe(resumen_stats, use_container_width=True)
                    
                    #st.divider()
                    
                    # # Validación de nulos
                    # nulls_df = validate_nulls(new_df)
                    # if not nulls_df.empty and nulls_df['nulos'].sum() > 0:
                    #     st.markdown("**Valores Nulos por Columna**")
                    #     fig_nulls = px.bar(nulls_df, x='columna', y='nulos', 
                    #                       title='Valores Nulos por Columna',
                    #                       color='nulos', color_continuous_scale='Viridis')
                    #     st.plotly_chart(fig_nulls, use_container_width=True, key="bar_nulls_estadisticas")
                    # else:
                    #     st.info('No se encontraron valores nulos.')
                    
                    # st.divider()
                    
                    # # Perfil de datos
                    # st.markdown("**Perfil de Datos - Archivo B**")
                    # profile = generate_profile(new_df)
                    # st.dataframe(profile, use_container_width=True)
                
                # Botón para guardar en histórico
                st.divider()
                if st.button(" Guardar resultados en histórico", key="save_historical"):
                    historico_id = db.guardar_historico(
                        esquema=esquema,
                        archivo_anterior=old_file.name,
                        archivo_nuevo=new_file.name,
                        score_calidad=calidad_score,
                        total_registros=len(new_df),
                        errores_encontrados=len(errors),
                        advertencias=len(warnings),
                        detalles=f"Coincidentes: {registros_coincidentes}, Nuevos: {registros_nuevos}, Eliminados: {registros_eliminados}, Modificados: {registros_modificados}, Coincidencia: {porcentaje_coincidencia}%"
                    )
                    st.success(f"Resultados guardados en histórico (ID: {historico_id})")
            else:
                st.info("Selecciona columnas clave y columnas a comparar para ver los resultados de comparación.")

            st.markdown("###  Estadísticas de Datos")
            nulls_df = validate_nulls(new_df)
            if not nulls_df.empty and nulls_df['nulos'].sum() > 0:
                fig_nulls = px.bar(nulls_df, x='columna', y='nulos', 
                                  title='Valores Nulos por Columna',
                                  color='nulos', color_continuous_scale='Viridis')
                st.plotly_chart(fig_nulls, use_container_width=True, key="bar_nulls_final")
            else:
                st.info('No se encontraron valores nulos.')
            profile = generate_profile(new_df)
            st.dataframe(profile, use_container_width=True)

            st.markdown('</div>', unsafe_allow_html=True)
    except Exception as e:
        st.error(f" Error: {str(e)}")
        st.exception(e)
elif modo == "Validar archivo único" and single_file:
    try:
        with st.spinner(" Procesando archivo único..."):
            df = dc.clean_data(read_file(single_file))
            st.markdown('<div class="main-container">', unsafe_allow_html=True)
            # Validación según esquema
            if esquema == "Licencias TI":
                errors, warnings = validate_licencias(df, db)
            elif esquema == "Dominios":
                errors, warnings = validate_dominios(df, db)
            elif esquema == "Certificados":
                errors, warnings = validate_certificados(df, db)
            else:
                errors, warnings = [], []

            if errors or warnings:
                st.markdown("###  Resultados de Validación")
                col_err, col_warn, col_view = st.columns(3)
                with col_err:
                    if errors:
                        st.markdown(f"""
<div class="alert-card error">
  <div class="metric-value">{len(errors)}</div>
  <div class="metric-label">Errores</div>
</div>
""", unsafe_allow_html=True)
                with col_warn:
                    if warnings:
                        st.markdown(f"""
<div class="alert-card warning">
  <div class="metric-value">{len(warnings)}</div>
  <div class="metric-label">Advertencias</div>
</div>
""", unsafe_allow_html=True)
                with col_view:
                    if st.button("Ver tabla completa", key="view_all_issues_single"):
                        st.session_state.show_issues_modal_single = True
                
                if st.session_state.get("show_issues_modal_single", False):
                    st.markdown("---")
                    st.markdown("#### Tabla Completa de Problemas")
                    
                    issues_data = []
                    for error in errors:
                        issues_data.append({"Tipo": "Error", "Detalle": error})
                    for warning in warnings:
                        issues_data.append({"Tipo": "Advertencia", "Detalle": warning})
                    
                    issues_df = pd.DataFrame(issues_data)
                    st.dataframe(issues_df, use_container_width=True, height=400)
                    
                    csv = issues_df.to_csv(index=False)
                    st.download_button(
                        label="Descargar CSV",
                        data=csv,
                        file_name="problemas_validacion.csv",
                        mime="text/csv",
                        key="download_issues_single"
                    )
                    
                    if st.button("Cerrar tabla", key="close_issues_modal_single"):
                        st.session_state.show_issues_modal_single = False
                    st.markdown("---")
            else:
                st.markdown('<div class="validation-pass"> ¡Todas las validaciones pasaron correctamente!</div>', unsafe_allow_html=True)

            calidad_score = data_quality_score(df)
            color_quality = "#28a745" if calidad_score >= 90 else "#ffc107" if calidad_score >= 70 else "#dc3545"

            st.markdown("####  Resumen de Calidad de Archivo")
            col_total, col_quality = st.columns(2)
            with col_total:
                st.markdown(f"""
<div class="metric-card">
<div class="metric-value">{len(df)}</div>
<div class="metric-label">Total Registros</div>
</div>
                """, unsafe_allow_html=True)
            with col_quality:
                st.markdown(f"""
<div class="metric-card">
<div class="metric-value" style="color: {color_quality}">{calidad_score:.0f}%</div>
<div class="metric-label"> Calidad</div>
</div>
                """, unsafe_allow_html=True)

            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=calidad_score,
                title={'text': "Score de Calidad"},
                domain={'x': [0, 1], 'y': [0, 1]},
                gauge={'axis': {'range': [None, 100]},
                       'bar': {'color': "#FF4201"},
                       'steps': [
                           {'range': [0, 70], 'color': "#f8d7da"},
                           {'range': [70, 90], 'color': "#fff3cd"},
                           {'range': [90, 100], 'color': "#d4edda"}],
                       'threshold': {'line': {'color': "red", 'width': 4},
                                     'thickness': 0.75, 'value': calidad_score}}))
            st.plotly_chart(fig, use_container_width=True, key="gauge_calidad_single")

            st.markdown("###  Estadísticas de Datos")
            nulls_df = validate_nulls(df)
            if not nulls_df.empty and nulls_df['nulos'].sum() > 0:
                fig_nulls = px.bar(nulls_df, x='columna', y='nulos', 
                                  title='Valores Nulos por Columna',
                                  color='nulos', color_continuous_scale='Viridis')
                st.plotly_chart(fig_nulls, use_container_width=True, key="bar_nulls_single")
            else:
                st.info('No se encontraron valores nulos.')
            profile = generate_profile(df)
            st.dataframe(profile, use_container_width=True)

            st.markdown('</div>', unsafe_allow_html=True)
    except Exception as e:
        st.error(f" Error: {str(e)}")
        st.exception(e)
elif modo == "Limpiar archivo":
    st.markdown("###  Limpiador de Texto")
    st.info("Suba un archivo Excel o CSV para eliminar espacios, caracteres especiales y dejar cada palabra con mayúscula inicial.")
    clean_file = st.file_uploader("Cargar archivo para limpiar", type=['csv', 'xlsx', 'xls'], key="clean_file")

    if clean_file:
        try:
            with st.spinner("Limpiando archivo..."):
                df = read_file(clean_file)
                try:
                    cleaned_df = dc.normalize_text_data(df)
                except AttributeError:
                    # If attribute missing due to import caching, reload and try again
                    importlib.reload(dc)
                    if hasattr(dc, 'normalize_text_data'):
                        cleaned_df = dc.normalize_text_data(df)
                    else:
                        raise

                st.markdown('<div class="main-container">', unsafe_allow_html=True)
                st.success(f"Archivo procesado: {clean_file.name}")
                st.markdown("#### Vista previa")
                st.dataframe(cleaned_df.head(50), use_container_width=True)

                csv_data = cleaned_df.to_csv(index=False)
                st.download_button(
                    label="Descargar archivo limpio",
                    data=csv_data,
                    file_name=f"{clean_file.name.rsplit('.', 1)[0]}_limpio.csv",
                    mime="text/csv",
                    key="download_cleaned_file"
                )
                st.markdown('</div>', unsafe_allow_html=True)
        except Exception as e:
            st.error(f" Error al limpiar el archivo: {str(e)}")
            st.exception(e)
else:
    if modo == "Comparar archivos":
        st.info(" **Instrucciones:** Cargue ambos archivos para comparar y seleccione las columnas clave y columnas a comparar.")
    elif modo == "Limpiar archivo":
        st.info(" **Instrucciones:** Cargue un archivo Excel o CSV para limpiarlo.")
    else:
        st.info(" **Instrucciones:** Cargue un archivo único para validar su calidad de datos.")
