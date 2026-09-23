import html as html_lib
import re
import unicodedata

import pandas as pd
import plotly.express as px
import streamlit as st

import data_cleaning as dc
import data_loader as dl
import schema_mapper as sm
import diffing
from comparator import (ESTADO_ALTA, ESTADO_AYUDA, ESTADO_BAJA, ESTADO_ICONO,
                        ESTADO_MODIFICACION, ESTADO_SIN_CAMBIOS, ESTADOS,
                        CompareOptions, compare_dataframes, compare_positional)
from database import init_db
from reporting import generate_profile, to_excel
from validation_engine import data_quality_score, validate_nulls
from validators import run_validation, validation_quality_score
from ui.components import (csv_bytes, metric_card, quality_color, quality_gauge,
                           show_error, show_file_warnings, styled, styled_note,
                           table_height)
from ui.styles import (AMARILLO_FONDO, ROJO_FONDO, ROJO_FUERTE, ROJO_TEXTO,
                       VERDE_FONDO, inject_css)

# Configuración de página
st.set_page_config(
    layout="wide",
    page_title="CMDB Quality Platform",
    page_icon="",
    initial_sidebar_state="expanded"
)

# Inicializar base de datos
db = init_db()


inject_css()

# Header
st.markdown("""
<div class="main-header">
<h1>CMDB Quality Platform</h1>
<p>Plataforma integral de calidad de datos para infraestructura TI</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Estado del asistente
# ---------------------------------------------------------------------------
MODOS = {
    "Comparar archivos": ["old", "new"],
    "Validar archivo único": ["single"],
    "Limpiar archivo": ["clean"],
}
MODO_AYUDA = {
    "Comparar archivos": "Compara una versión anterior y una nueva para encontrar registros nuevos, eliminados y modificados.",
    "Validar archivo único": "Revisa la calidad de un archivo aplicando las reglas del esquema seleccionado.",
    "Limpiar archivo": "Normaliza textos (espacios, caracteres especiales, mayúsculas) respetando correos, códigos y fechas.",
}
ESQUEMAS = ["Licencias TI", "Dominios", "Certificados", "Cuentas", "Usuario", "Infraestructura", "General"]
SLOT_LABEL = {
    "old": "Archivo 1 (anterior)",
    "new": "Archivo 2 (nuevo)",
    "single": "Archivo a validar",
    "clean": "Archivo a limpiar",
}
P_CARGA = "Carga de archivos"
P_ESQUEMA = "Esquema de datos"
P_REGLAS = "Reglas de comparación"
P_RESULTADOS = "Resultados"
PASOS_SUB = {
    P_CARGA: "Hoja y revisión previa",
    P_ESQUEMA: "Confirmar tipos",
    P_REGLAS: "Clave y tolerancias",
    P_RESULTADOS: "Análisis y descarga",
}
ESTADO_COLOR = {ESTADO_ALTA: VERDE_FONDO, ESTADO_BAJA: ROJO_FONDO,
                ESTADO_MODIFICACION: AMARILLO_FONDO, ESTADO_SIN_CAMBIOS: "#f1f3f5"}
REGLAS_DEFAULT = {
    "keys": [], "cols": None, "excluded": [],
    "ignore_case": False, "ignore_accents": False, "ignore_spaces": True,
    "numeric_tolerance": 0.0, "date_tolerance": True,
    "fuzzy_enabled": False, "fuzzy_algo": diffing.JARO_WINKLER, "fuzzy_threshold": 0.85,
}
FUZZY_ALGORITHM_HELP = {
    diffing.JARO_WINKLER: (
        "Compara caracteres y da mayor peso a los prefijos coincidentes. "
        "Es recomendable para nombres o códigos con errores pequeños de escritura."
    ),
    diffing.LEVENSHTEIN: (
        "Calcula las inserciones, eliminaciones y sustituciones necesarias para "
        "convertir un texto en otro. Es útil para medir diferencias generales."
    ),
}
DEFAULT_OPTS = {"sheet": None, "header_row": 1, "fill_merged": False, "skip_rows": False, "skip_cols": False}

ss = st.session_state
ss.setdefault("step", 1)
ss.setdefault("cfg", {"modo": "Comparar archivos", "esquema": "Licencias TI"})
ss.setdefault("files", {})
ss.setdefault("opts", {})
ss.setdefault("acks", {})
ss.setdefault("schema_map", None)
ss.setdefault("schema_sig", None)
ss.setdefault("schema_input", None)
ss.setdefault("schema_version", 0)
ss.setdefault("cmp", dict(REGLAS_DEFAULT))


def current_slots():
    return MODOS[ss.cfg["modo"]]


def pasos_actuales():
    """Los pasos del asistente dependen del modo elegido en el menú lateral."""
    pasos = [P_CARGA, P_ESQUEMA]
    if ss.cfg["modo"] == "Comparar archivos":
        pasos.append(P_REGLAS)
    pasos.append(P_RESULTADOS)
    return pasos


def paso_actual():
    pasos = pasos_actuales()
    ss.step = max(1, min(ss.step, len(pasos)))
    return pasos[ss.step - 1]


def reset_schema():
    ss.schema_map = None
    ss.schema_sig = None
    ss.schema_input = None
    ss.cmp = dict(REGLAS_DEFAULT)


def reset_files():
    ss.files = {}
    ss.opts = {}
    ss.acks = {}
    reset_schema()


def go_to(step):
    if pasos_actuales()[step - 1] == P_ESQUEMA:
        # Se reconstruye la tabla del editor desde el mapeo guardado para no perder
        # los cambios del usuario al volver a este paso.
        ss.schema_input = None
    ss.step = step


def restart():
    reset_files()
    ss.step = 1


def files_signature():
    return tuple(
        (s, ss.files[s]["name"], len(ss.files[s]["data"]), tuple(sorted(ss.opts.get(s, DEFAULT_OPTS).items())))
        for s in current_slots() if s in ss.files
    )


# ---------------------------------------------------------------------------
# Utilidades de carga (con caché para que la interfaz responda al instante)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, max_entries=20)
def cached_sheets(name, data):
    return dl.get_sheet_info(name, data)


@st.cache_data(show_spinner=False, max_entries=20)
def cached_load(name, data, sheet, header_row, fill_merged, skip_rows, skip_cols):
    return dl.load_table(name, data, sheet, header_row, fill_merged, skip_rows, skip_cols)


@st.cache_data(show_spinner=False, max_entries=20)
def cached_clean(name, data, sheet, header_row, fill_merged, skip_rows, skip_cols):
    return dc.clean_data(cached_load(name, data, sheet, header_row, fill_merged, skip_rows, skip_cols)[0])


@st.cache_data(show_spinner=False, max_entries=20)
def cached_prepare(name, data, sheet, header_row, fill_merged, skip_rows, skip_cols,
                   schema_items, style_items):
    limpio = cached_clean(name, data, sheet, header_row, fill_merged, skip_rows, skip_cols)
    return sm.apply_schema(limpio, dict(schema_items), dict(style_items))


def _load_args(slot):
    f, o = ss.files[slot], ss.opts.get(slot, DEFAULT_OPTS)
    return (f["name"], f["data"], o["sheet"], o["header_row"], o["fill_merged"], o["skip_rows"], o["skip_cols"])


def load_slot(slot):
    return cached_load(*_load_args(slot))


def cleaned_slot(slot):
    return cached_clean(*_load_args(slot))


def numeric_styles():
    """Separador decimal por columna, deducido con todos los archivos cargados,
    para que la misma columna no se interprete distinto en cada uno."""
    if not ss.schema_map:
        return ()
    dfs = [cleaned_slot(s) for s in current_slots() if s in ss.files]
    return tuple(sorted(sm.decimal_styles(ss.schema_map, *dfs).items()))


def prepared_slot(slot):
    return cached_prepare(*_load_args(slot), tuple(ss.schema_map.items()), numeric_styles())


# ---------------------------------------------------------------------------
# Navegación del asistente
# ---------------------------------------------------------------------------
def render_stepper():
    markup = '<div class="wizard">'
    for i, title in enumerate(pasos_actuales(), start=1):
        cls = "active" if i == ss.step else "done" if i < ss.step else ""
        num = "✓" if i < ss.step else str(i)
        markup += (f'<div class="wizard-step {cls}"><div class="num">{num}</div>'
                   f'<div>{title}<small>{PASOS_SUB[title]}</small></div></div>')
    st.markdown(markup + "</div>", unsafe_allow_html=True)


def step_header(texto):
    st.markdown(f"### {ss.step}. {texto}")


def nav_buttons(can_continue=True, next_label="Siguiente →", blocked_reason=None):
    st.divider()
    left, _, right = st.columns([1, 2, 1])
    with left:
        if ss.step > 1:
            st.button("← Anterior", on_click=go_to, args=(ss.step - 1,), width="stretch")
    with right:
        if ss.step < len(pasos_actuales()):
            st.button(next_label, on_click=go_to, args=(ss.step + 1,), type="primary",
                      disabled=not can_continue, width="stretch")
    if not can_continue and blocked_reason:
        st.caption(f"Para continuar: {blocked_reason}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def _cambiar_modo():
    nuevo = ss.get("nav_modo", ss.cfg["modo"])
    if nuevo != ss.cfg["modo"]:
        ss.cfg["modo"] = nuevo
        reset_files()
        ss.step = 1


with st.sidebar:
    st.markdown("### Modo de análisis")
    modos = list(MODOS)
    if "nav_modo" not in ss:
        ss["nav_modo"] = ss.cfg["modo"]
    st.radio("Seleccione el análisis", modos, key="nav_modo", on_change=_cambiar_modo,
             captions=[MODO_AYUDA[m] for m in modos], label_visibility="collapsed")

    if ss.cfg["modo"] != "Limpiar archivo":
        st.markdown("### Configuración")
        if "nav_esquema" not in ss:
            ss["nav_esquema"] = ss.cfg["esquema"]
        ss.cfg["esquema"] = st.selectbox(
            "Esquema de reglas", ESQUEMAS, key="nav_esquema",
            help="Reglas de negocio que se aplicarán (países permitidos, fechas, cantidades...). "
                 "«General» solo revisa estructura y calidad.")

    st.markdown("---")
    pasos = pasos_actuales()
    st.caption(f"Paso {ss.step} de {len(pasos)}: **{pasos[ss.step - 1]}**")
    for slot in current_slots():
        if slot in ss.files:
            st.caption(f"{SLOT_LABEL[slot]}: {ss.files[slot]['name']}")
    st.button("↺ Reiniciar asistente", on_click=restart, width="stretch")
    st.markdown("---")
    with st.expander("Histórico de Validaciones", expanded=False):
        historico = db.obtener_historicos(5)
        if not historico.empty:
            st.dataframe(historico[['fecha_validacion', 'esquema', 'score_calidad']], width="stretch")
        else:
            st.caption("Aún no hay resultados guardados.")

render_stepper()


# ---------------------------------------------------------------------------
# Paso: Carga de archivos
# ---------------------------------------------------------------------------
def render_slot(slot):
    """Renderiza la carga de un archivo. Devuelve (listo, motivo_si_no)."""
    st.markdown(f"#### {SLOT_LABEL[slot]}")

    if slot not in ss.files:
        up = st.file_uploader(
            "Arrastre o seleccione un archivo (.xlsx, .xlsm, .xls o .csv)",
            key=f"uploader_{slot}",
            help="Si su archivo tiene varias hojas, podrá elegir cuál analizar en el siguiente paso.",
        )
        if up is None:
            return False, f"cargue el {SLOT_LABEL[slot].lower()}."
        try:
            dl.check_extension(up.name)
        except dl.FileLoadError as exc:
            show_error(exc)
            return False, "cargue un archivo con formato soportado."
        ss.files[slot] = {"name": up.name, "data": up.getvalue()}
        ss.opts[slot] = dict(DEFAULT_OPTS)
        st.rerun()

    f = ss.files[slot]
    size = len(f["data"])
    size_txt = f"{size / 1048576:,.1f} MB" if size >= 1048576 else f"{max(size / 1024, 0.1):,.1f} KB"
    head_l, head_r = st.columns([3, 1], vertical_alignment="center")
    head_l.success(f"**{f['name']}** ({size_txt})")

    def _remove(s=slot):
        ss.files.pop(s, None)
        ss.opts.pop(s, None)
        ss.acks.pop(s, None)
        reset_schema()

    head_r.button("Cambiar", key=f"remove_{slot}", on_click=_remove, width="stretch")

    opts = ss.opts.setdefault(slot, dict(DEFAULT_OPTS))
    is_xlsx = dl.get_extension(f["name"]) in dl.OPENPYXL_EXTENSIONS

    try:
        sheets = cached_sheets(f["name"], f["data"])
    except dl.FileLoadError as exc:
        show_error(exc)
        return False, "corrija el archivo o cargue otro."

    # Selector interactivo de hoja
    if sheets:
        names = [s["nombre"] for s in sheets]
        if opts["sheet"] not in names:
            visibles = [s["nombre"] for s in sheets if s["visible"]]
            opts["sheet"] = visibles[0] if visibles else names[0]
        if len(sheets) > 1:
            def _fmt(n):
                s = next(x for x in sheets if x["nombre"] == n)
                extra = f" · {s['filas']} filas × {s['columnas']} columnas" if s["filas"] else ""
                return f"{n}{' (oculta)' if not s['visible'] else ''}{extra}"

            st.info(f"Este libro tiene **{len(sheets)} hojas**. Seleccione la que contiene los datos a analizar.")
            opts["sheet"] = st.selectbox("Hoja / pestaña", names, index=names.index(opts["sheet"]),
                                         format_func=_fmt, key=f"sheet_{slot}")

    with st.expander("Opciones de lectura", expanded=opts["header_row"] != 1 or opts["fill_merged"]):
        c1, c2 = st.columns(2)
        opts["header_row"] = int(c1.number_input(
            "Fila donde están los encabezados", min_value=1, max_value=100, value=opts["header_row"],
            key=f"header_{slot}", help="Úselo si el archivo tiene títulos o logos antes de la tabla."))
        if is_xlsx:
            opts["fill_merged"] = c2.checkbox(
                "Rellenar celdas combinadas", value=opts["fill_merged"], key=f"fill_{slot}",
                help="Copia el valor de la celda combinada a todas las celdas que abarca.")
            opts["skip_rows"] = c2.checkbox("Excluir filas ocultas / filtradas", value=opts["skip_rows"], key=f"srows_{slot}")
            opts["skip_cols"] = c2.checkbox("Excluir columnas ocultas", value=opts["skip_cols"], key=f"scols_{slot}")

    try:
        with st.spinner("Leyendo y revisando el archivo..."):
            df, warnings = load_slot(slot)
    except dl.FileLoadError as exc:
        show_error(exc)
        return False, "corrija el archivo, elija otra hoja o ajuste las opciones de lectura."

    m1, m2, m3 = st.columns(3)
    m1.metric("Filas", f"{len(df):,}")
    m2.metric("Columnas", df.shape[1])
    m3.metric("Hoja", opts["sheet"] or "—")

    relevant = [w for w in warnings if w["nivel"] in ("error", "warning")]
    if warnings:
        st.markdown("**Revisión preventiva**")
        show_file_warnings(warnings)
    if not relevant:
        st.success("No se detectaron celdas combinadas, columnas ocultas ni otros problemas de estructura.")

    with st.expander("Vista previa (primeras 10 filas)", expanded=bool(relevant)):
        st.dataframe(df.head(10), width="stretch")

    if any(w["nivel"] == "error" for w in warnings):
        return False, f"resuelva los problemas marcados en rojo del {SLOT_LABEL[slot].lower()}."
    if relevant:
        sig = (f["name"], len(f["data"]), tuple(sorted(opts.items())))
        ack = st.checkbox("He revisado las advertencias y deseo continuar con este archivo",
                          value=ss.acks.get(slot) == sig, key=f"ack_{slot}_{hash(sig)}")
        ss.acks[slot] = sig if ack else None
    return True, None


def step_upload():
    step_header("Cargue sus archivos")
    slots = current_slots()
    ready, reasons = [], []
    cols = st.columns(len(slots), gap="large") if len(slots) > 1 else [st.container()]
    for col, slot in zip(cols, slots):
        with col:
            with st.container(border=True):
                ok, reason = render_slot(slot)
        ready.append(ok)
        if reason:
            reasons.append(reason)

    if ss.cfg["modo"] == "Comparar archivos" and all(ready):
        a, b = load_slot("old")[0], load_slot("new")[0]
        common = [c for c in b.columns if c in a.columns]
        only_a = [c for c in a.columns if c not in b.columns]
        only_b = [c for c in b.columns if c not in a.columns]
        if not common:
            st.error("**Los archivos no comparten ninguna columna con el mismo nombre**, por lo que no se pueden comparar. "
                     "Verifique que eligió la hoja correcta y que la fila de encabezados es la misma en ambos.")
            ready.append(False)
            reasons.append("los archivos deben tener al menos una columna en común.")
        elif only_a or only_b:
            detail = []
            if only_a:
                detail.append(f"solo en el Archivo 1: {', '.join(only_a[:8])}{'…' if len(only_a) > 8 else ''}")
            if only_b:
                detail.append(f"solo en el Archivo 2: {', '.join(only_b[:8])}{'…' if len(only_b) > 8 else ''}")
            st.warning(f"Hay {len(common)} columnas en común. Algunas columnas no están en ambos archivos "
                       f"({'; '.join(detail)}) y no se podrán comparar.", icon="⚠️")

    # Si cambió algún archivo u opción, el esquema confirmado ya no es válido.
    if ss.schema_sig is not None and ss.schema_sig != files_signature():
        reset_schema()
    nav_buttons(all(ready), blocked_reason=reasons[0] if reasons else None)


# ---------------------------------------------------------------------------
# Paso: Esquema de datos
# ---------------------------------------------------------------------------
def step_schema():
    step_header("Confirme el tipo de dato de cada columna")
    st.caption("Detectamos automáticamente el tipo de cada columna. Revíselo y ajústelo si es necesario: "
               "así los correos, códigos con ceros a la izquierda, montos y fechas se procesan sin perder su formato.")
    slots = current_slots()
    try:
        dfs = [cleaned_slot(s) for s in slots]
    except Exception as exc:  # noqa: BLE001
        show_error(exc, "leer los archivos")
        nav_buttons(False)
        return

    sig = files_signature()
    if ss.schema_sig != sig:
        ss.schema_map, ss.schema_input, ss.schema_sig = None, None, sig
    if ss.schema_input is None:
        base = sm.infer_schema(*dfs)
        if ss.schema_map:
            base["Tipo de dato"] = base["Columna"].map(ss.schema_map).fillna(base["Tipo de dato"])
        ss.schema_input = base
        ss.schema_version += 1

    with st.expander("¿Qué significa cada tipo?"):
        for t in sm.TIPOS:
            st.markdown(f"- **{t}**: {sm.TIPO_DESCRIPCION[t]}")

    edited = st.data_editor(
        ss.schema_input,
        key=f"schema_editor_{ss.schema_version}",
        hide_index=True,
        width="stretch",
        disabled=["Columna", "Tipo detectado", "Ejemplos", "Vacíos"],
        column_config={
            "Columna": st.column_config.TextColumn("Columna", width="medium"),
            "Tipo detectado": st.column_config.TextColumn("Tipo detectado", width="medium"),
            "Tipo de dato": st.column_config.SelectboxColumn(
                "Tipo de dato", options=sm.TIPOS, required=True, width="medium",
                help="Haga clic para cambiar el tipo"),
            "Ejemplos": st.column_config.TextColumn("Ejemplos de valores", width="large"),
            "Vacíos": st.column_config.NumberColumn("Vacíos", width="small"),
        },
    )
    ss.schema_map = dict(zip(edited["Columna"], edited["Tipo de dato"]))
    changed = int((edited["Tipo de dato"] != edited["Tipo detectado"]).sum())
    if changed:
        st.caption(f"Modificó el tipo de {changed} columna(s) respecto a lo detectado.")

    # Vista previa de la conversión
    st.markdown("#### Resultado de aplicar los tipos")
    try:
        results = [prepared_slot(s) for s in slots]
    except Exception as exc:  # noqa: BLE001
        show_error(exc, "aplicar los tipos de datos")
        nav_buttons(False)
        return

    all_reports = pd.concat(
        [r.assign(Archivo=SLOT_LABEL[s]) for s, (_, r) in zip(slots, results) if not r.empty] or [pd.DataFrame()],
        ignore_index=True)
    if all_reports.empty:
        st.success("Todos los valores son compatibles con los tipos seleccionados.")
    else:
        total = int(all_reports["Valores no válidos"].sum())
        st.warning(f"**{total} valores no coinciden con el tipo asignado.** Revise la tabla: puede cambiar el tipo "
                   "de la columna arriba o continuar si es lo esperado.", icon="⚠️")
        cols_show = (["Archivo"] if len(slots) > 1 else []) + ["Columna", "Tipo asignado", "Valores no válidos", "Ejemplos", "Qué pasará"]
        st.dataframe(all_reports[cols_show], hide_index=True, width="stretch")

    estilos = dict(numeric_styles())
    if estilos:
        detalle = "; ".join(f"«{c}» usa {sm.ESTILO_NOMBRE[e]}" for c, e in estilos.items())
        st.caption(f"Formato numérico detectado: {detalle}.")

    tabs = st.tabs([SLOT_LABEL[s] for s in slots]) if len(slots) > 1 else [st.container()]
    for tab, s, df_raw, (_, report) in zip(tabs, slots, dfs, results):
        with tab:
            preview = df_raw.head(50)
            mask = pd.DataFrame(False, index=preview.index, columns=preview.columns)
            for _, r in report.iterrows():
                rows = [i for i in r["Filas"] if i in mask.index]
                mask.loc[rows, r["Columna"]] = True
            st.caption("Vista previa de los datos originales (celdas en rojo = valor incompatible con el tipo elegido):")
            st.dataframe(styled(preview, cell_mask=mask), width="stretch")

    siguiente = "Continuar a las reglas →" if ss.cfg["modo"] == "Comparar archivos" else "Confirmar y procesar →"
    nav_buttons(True, next_label=siguiente)


# ---------------------------------------------------------------------------
# Paso 4: Resultados
# ---------------------------------------------------------------------------
ROW_RE = re.compile(r"^Fila (\S+?):")


def _plain(text):
    """Minúsculas y sin tildes, para ubicar el nombre de una columna dentro de un mensaje."""
    return unicodedata.normalize("NFKD", str(text).lower()).encode("ascii", "ignore").decode()


def _mentions(message, column):
    return re.search(rf"(?<!\w){re.escape(_plain(column))}(?!\w)", _plain(message)) is not None


def issues_to_frame(errors, warnings):
    data = [{"Tipo": "Error", "Detalle": e} for e in errors] + [{"Tipo": "Advertencia", "Detalle": w} for w in warnings]
    return pd.DataFrame(data, columns=["Tipo", "Detalle"])


def render_validation(df, key_prefix):
    esquema = ss.cfg["esquema"]
    errors, warnings = run_validation(esquema, df, db)
    if esquema == "General":
        st.caption("Esquema «General»: no se aplican reglas de negocio, solo métricas de calidad.")
    if not errors and not warnings:
        if esquema != "General":
            st.markdown('<div class="validation-pass">¡Todas las validaciones pasaron correctamente!</div>', unsafe_allow_html=True)
        return errors, warnings

    st.markdown("### Resultados de Validación")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div class="alert-card error"><div class="metric-value">{len(errors)}</div>'
                    f'<div class="metric-label">Errores</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="alert-card warning"><div class="metric-value">{len(warnings)}</div>'
                    f'<div class="metric-label">Advertencias</div></div>', unsafe_allow_html=True)

    issues_df = issues_to_frame(errors, warnings)
    t_rows, t_list = st.tabs(["Filas con incoherencias", "Listado de mensajes"])
    with t_list:
        st.dataframe(issues_df, width="stretch", height=350, hide_index=True)
        st.download_button("Descargar problemas (CSV)", csv_bytes(issues_df), "problemas_validacion.csv",
                           "text/csv", key=f"{key_prefix}_dl_issues", on_click="ignore")
    with t_rows:
        # Resaltar en rojo las filas con errores (amarillo = solo advertencias)
        # y con rojo intenso las celdas de la columna mencionada en el mensaje.
        by_row = {}
        for tipo, msg in zip(issues_df["Tipo"], issues_df["Detalle"]):
            m = ROW_RE.match(msg)
            if not m:
                continue
            try:
                idx = type(df.index[0])(m.group(1)) if len(df.index) else m.group(1)
            except (TypeError, ValueError):
                idx = m.group(1)
            entry = by_row.setdefault(idx, {"Error": [], "Advertencia": []})
            entry[tipo].append(msg[m.end():].strip())
        rows = [i for i in df.index if i in by_row]
        if not rows:
            st.info("Los mensajes no hacen referencia a filas específicas.")
        else:
            view = df.loc[rows].copy()
            view.insert(0, "Problemas", ["; ".join(by_row[i]["Error"] + by_row[i]["Advertencia"]) for i in rows])
            row_colors = pd.Series([ROJO_FONDO if by_row[i]["Error"] else AMARILLO_FONDO for i in rows], index=view.index)
            cell_mask = pd.DataFrame(False, index=view.index, columns=view.columns)
            for i in rows:
                text = " ".join(by_row[i]["Error"] + by_row[i]["Advertencia"])
                for c in df.columns:
                    if _mentions(text, c):
                        cell_mask.at[i, c] = True
            st.markdown(f'<span class="legend-chip" style="background:{ROJO_FONDO}">Fila con errores</span>'
                        f'<span class="legend-chip" style="background:{AMARILLO_FONDO}">Solo advertencias</span>'
                        f'<span class="legend-chip" style="background:{ROJO_FUERTE};color:{ROJO_TEXTO}">Celda con el problema</span>',
                        unsafe_allow_html=True)
            st.dataframe(styled(view, cell_mask=cell_mask, row_colors=row_colors), width="stretch",
                         height=table_height(len(view), 400),
                         column_config={"Problemas": st.column_config.TextColumn(width="large")})
            styled_note(view)
    return errors, warnings


def render_quality(df, key_prefix, score_override=None):
    st.markdown("### Estadísticas de Datos")
    score = data_quality_score(df) if score_override is None else score_override
    c1, c2 = st.columns([1, 2])
    with c1:
        metric_card(f"{len(df):,}", "Total Registros")
        st.write("")
        metric_card(f"{score:.0f}%", "Calidad (celdas completas)", quality_color(score))
    with c2:
        quality_gauge(score, f"{key_prefix}_gauge")
    nulls_df = validate_nulls(df)
    if not nulls_df.empty and nulls_df['nulos'].sum() > 0:
        fig_nulls = px.bar(nulls_df, x='columna', y='nulos', title='Valores Nulos por Columna',
                           color='nulos', color_continuous_scale='Viridis')
        st.plotly_chart(fig_nulls, width="stretch", key=f"{key_prefix}_nulls")
    else:
        st.info('No se encontraron valores nulos.')
    with st.expander("Perfil de columnas"):
        profile = generate_profile(df)
        profile.insert(1, "tipo asignado", profile["columna"].map(ss.schema_map or {}))
        st.dataframe(profile, width="stretch", hide_index=True)
    return score


def quality_status(score):
    if score >= 90:
        return "Conforme / Aprobado"
    if score >= 75:
        return "Advertencia / Revisión"
    return "Rechazado"


# ---------------------------------------------------------------------------
# Glosario de estados y reglas de comparación
# ---------------------------------------------------------------------------
def render_glossary():
    chips = "".join(
        f'<span class="legend-chip" style="background:{ESTADO_COLOR[e]}" title="{ESTADO_AYUDA[e]}">'
        f'{ESTADO_ICONO[e]} {e}</span>' for e in ESTADOS)
    st.markdown(chips, unsafe_allow_html=True)
    with st.expander("Glosario: ¿qué significa cada estado?"):
        for e in ESTADOS:
            st.markdown(f"- {ESTADO_ICONO[e]} **{e}**: {ESTADO_AYUDA[e]}")
        st.markdown("- **Diferencias cosméticas**: mayúsculas/minúsculas, tildes, espacios o formato de fecha. "
                    "El dato es equivalente pero está escrito de otra forma; aparecen en «Detalle de diferencias» "
                    "con su tipo exacto.")
        st.markdown("- **Registros repetidos**: cuando una clave aparece varias veces, se emparejan 1 a 1 por "
                    "orden de aparición (1ª con 1ª, 2ª con 2ª...). Ninguna fila se descarta.")


def current_options():
    c = ss.cmp
    return CompareOptions(
        ignore_case=c["ignore_case"], ignore_accents=c["ignore_accents"], ignore_spaces=c["ignore_spaces"],
        numeric_tolerance=float(c["numeric_tolerance"]), date_tolerance=c["date_tolerance"],
        excluded=list(c["excluded"]), fuzzy_enabled=c["fuzzy_enabled"], fuzzy_algo=c["fuzzy_algo"],
        fuzzy_threshold=float(c["fuzzy_threshold"]),
    )


def options_key():
    c = ss.cmp
    return (c["ignore_case"], c["ignore_accents"], c["ignore_spaces"], float(c["numeric_tolerance"]),
            c["date_tolerance"], tuple(c["excluded"]), c["fuzzy_enabled"], c["fuzzy_algo"],
            float(c["fuzzy_threshold"]))


def _options_from_key(k):
    return CompareOptions(ignore_case=k[0], ignore_accents=k[1], ignore_spaces=k[2], numeric_tolerance=k[3],
                          date_tolerance=k[4], excluded=list(k[5]), fuzzy_enabled=k[6], fuzzy_algo=k[7],
                          fuzzy_threshold=k[8])


@st.cache_data(show_spinner=False, max_entries=8)
def run_comparison(old_df, new_df, keys, cols, opts_key):
    return compare_dataframes(old_df, new_df, list(keys), list(cols), _options_from_key(opts_key))


@st.cache_data(show_spinner=False, max_entries=8)
def run_positional(old_df, new_df, columnas, opts_key):
    return compare_positional(old_df, new_df, list(columnas), _options_from_key(opts_key))


def _keys_changed(prefix):
    """Al cambiar la clave, las columnas afectadas entran o salen de la comparación al instante."""
    keys = ss.get(f"{prefix}_keys", [])
    liberadas = [k for k in ss.cmp["keys"] if k not in keys]
    ss.cmp["keys"] = keys
    kc, ke = f"{prefix}_cols", f"{prefix}_excl"
    if ke in ss:
        ss[ke] = [c for c in ss[ke] if c not in keys]
        ss.cmp["excluded"] = ss[ke]
    if kc in ss:
        ss[kc] = ([c for c in ss[kc] if c not in keys]
                  + [c for c in liberadas if c not in ss[kc] and c not in ss.cmp["excluded"]])
        ss.cmp["cols"] = ss[kc]


def _excluded_changed(prefix):
    """Una columna marcada como volátil sale de la comparación al instante."""
    excl = ss.get(f"{prefix}_excl", [])
    liberadas = [c for c in ss.cmp["excluded"] if c not in excl]
    ss.cmp["excluded"] = excl
    kc = f"{prefix}_cols"
    if kc in ss:
        ss[kc] = ([c for c in ss[kc] if c not in excl]
                  + [c for c in liberadas if c not in ss[kc] and c not in ss.cmp["keys"]])
        ss.cmp["cols"] = ss[kc]


def render_rules(common, prefix):
    """Controles de clave, columnas y tolerancias. Se usan tanto en el paso de
    reglas como en los resultados, compartiendo el mismo estado."""
    c = ss.cmp
    kk, kc, ke = f"{prefix}_keys", f"{prefix}_cols", f"{prefix}_excl"
    if kk not in ss:
        ss[kk] = [k for k in c["keys"] if k in common]
    if ke not in ss:
        ss[ke] = [x for x in c["excluded"] if x in common and x not in ss[kk]]
    if kc not in ss:
        base = c["cols"] if c["cols"] is not None else []
        ss[kc] = [x for x in base if x in common and x not in ss[kk] and x not in ss[ke]]

    col1, col2 = st.columns(2)
    with col1:
        keys = st.multiselect(
            "Columnas clave (identificador del registro)", common, key=kk,
            on_change=_keys_changed, args=(prefix,),
            help="Columnas que identifican cada registro (ID, Serial, Dominio...). Si una clave se repite, "
                 "los registros se emparejan 1 a 1 por orden de aparición.")
    disponibles = [x for x in common if x not in keys]
    with col2:
        cols = st.multiselect(
            "Columnas a comparar", disponibles, key=kc,
            help="Seleccione las columnas cuyo contenido desea contrastar entre ambos archivos.")
    excl = st.multiselect(
        "Columnas volátiles a ignorar en el cruce", disponibles, key=ke,
        on_change=_excluded_changed, args=(prefix,),
        help="Columnas que cambian por sí solas y no deben contar como diferencia: marcas de tiempo de auditoría, "
             "IDs autoincrementales, usuario de última modificación...")
    c["keys"], c["excluded"] = keys, excl
    c["cols"] = [x for x in cols if x not in excl]

    with st.expander("Tolerancias y sensibilidad", expanded=prefix == "rules"):
        t1, t2 = st.columns(2)
        with t1:
            st.markdown("**Números y fechas**")
            c["numeric_tolerance"] = float(st.number_input(
                "Tolerancia numérica (±)", min_value=0.0, value=float(c["numeric_tolerance"]),
                step=0.01, format="%.4f", key=f"{prefix}_tol",
                help="Diferencias menores o iguales a este margen no se consideran un cambio. "
                     "Ejemplo: 0.01 para montos."))
            st.caption(
                f"Permite diferencias numéricas absolutas de hasta ±{c['numeric_tolerance']:.4f}. "
                "Con 0 se exige igualdad exacta; por ejemplo, con 0.01, 100 y 100.01 "
                "se consideran equivalentes."
            )
            c["date_tolerance"] = st.toggle(
                "Ignorar formato de fecha/hora y zona horaria", value=c["date_tolerance"], key=f"{prefix}_date",
                help="Trata 2024-01-15 y 15/01/2024 como la misma fecha.")
        with t2:
            st.markdown("**Texto**")
            c["ignore_case"] = st.toggle(
                "Ignorar mayúsculas/minúsculas", value=c["ignore_case"], key=f"{prefix}_case",
                help="Desactivado, «Hola» y «hola» se reportan como diferencia.")
            c["ignore_accents"] = st.toggle(
                "Ignorar tildes y acentos", value=c["ignore_accents"], key=f"{prefix}_acc",
                help="Desactivado, «Camión» y «Camion» se reportan como diferencia.")
            c["ignore_spaces"] = st.toggle(
                "Ignorar espacios sobrantes", value=c["ignore_spaces"], key=f"{prefix}_sp",
                help="Desactivado, los espacios dobles o invisibles se reportan como diferencia.")
        st.divider()
        c["fuzzy_enabled"] = st.toggle(
            "Sugerir coincidencias parciales (fuzzy matching)", value=c["fuzzy_enabled"], key=f"{prefix}_fz",
            help="Cuando una clave no tiene coincidencia exacta, busca la más parecida entre altas y bajas.")
        if c["fuzzy_enabled"]:
            st.info(
                "El fuzzy matching busca posibles equivalencias entre registros que no coinciden "
                "exactamente. Las coincidencias se muestran como sugerencias y no modifican los datos."
            )
            f1, f2 = st.columns(2)
            c["fuzzy_algo"] = f1.selectbox("Algoritmo de similitud", diffing.ALGORITMOS,
                                           index=diffing.ALGORITMOS.index(c["fuzzy_algo"]), key=f"{prefix}_algo")
            st.caption(FUZZY_ALGORITHM_HELP[c["fuzzy_algo"]])
            c["fuzzy_threshold"] = f2.slider("Similitud mínima", 0.50, 1.0, float(c["fuzzy_threshold"]), 0.01,
                                             key=f"{prefix}_thr", format="%.2f")
    return keys, c["cols"]


# ---------------------------------------------------------------------------
# Paso: Reglas de comparación
# ---------------------------------------------------------------------------
def step_rules():
    step_header("Defina las reglas de comparación")
    st.caption("Elija qué identifica a cada registro, qué columnas se contrastan y qué diferencias deben tolerarse.")
    try:
        old_df = prepared_slot("old")[0]
        new_df = prepared_slot("new")[0]
    except Exception as exc:  # noqa: BLE001
        show_error(exc, "preparar los archivos")
        nav_buttons(False)
        return

    common = [c for c in new_df.columns if c in old_df.columns]
    keys, cols = render_rules(common, "rules")
    st.info(f"**Reglas activas:** {current_options().describe()}.")

    if not keys:
        st.warning("Seleccione al menos una columna clave. Si ninguna columna identifica al registro por sí sola, "
                   "combine varias (por ejemplo, País + Serial).")
    else:
        dup_a = int(old_df.duplicated(subset=keys, keep=False).sum())
        dup_b = int(new_df.duplicated(subset=keys, keep=False).sum())
        if dup_a or dup_b:
            st.info(f"La clave elegida se repite en {dup_a} filas del Archivo 1 y {dup_b} del Archivo 2. "
                    "Esos registros se emparejarán 1 a 1 por orden de aparición, sin descartar ninguno.")
    nav_buttons(bool(keys and cols), next_label="Comparar →",
                blocked_reason=None if keys and cols else
                "elija la columna clave y al menos una columna a comparar.")


# ---------------------------------------------------------------------------
# Resultados de la comparación
# ---------------------------------------------------------------------------
def inclusion_card(inc):
    if inc["contenido"]:
        clase, respuesta = "ok", "SÍ"
        detalle = f"Los {inc['total_a']:,} registros del Archivo 1 están presentes e idénticos en el Archivo 2."
    elif inc["contenido_por_clave"]:
        clase, respuesta = "partial", "PARCIAL"
        detalle = (f"Todas las claves del Archivo 1 existen en el Archivo 2, pero "
                   f"{inc['encontrados'] - inc['identicos']:,} registros tienen diferencias de contenido.")
    else:
        clase, respuesta = "ko", "NO"
        detalle = (f"{inc['faltantes']:,} de {inc['total_a']:,} registros del Archivo 1 no se encontraron "
                   f"en el Archivo 2 (bajas).")
    st.markdown(f"""
<div class="inclusion-card {clase}">
  <div class="inclusion-title">¿Archivo 1 totalmente contenido en Archivo 2?</div>
  <div class="inclusion-answer">{respuesta}</div>
  <div class="inclusion-detail">{detalle}<br>
  <b>Cobertura exacta: {inc['cobertura_exacta']}%</b> (registros idénticos) &middot;
  Cobertura por clave: {inc['cobertura_clave']}% ({inc['encontrados']:,} de {inc['total_a']:,} registros encontrados).</div>
</div>""", unsafe_allow_html=True)


def diff_table_html(view, limit=150):
    filas = []
    for _, r in view.head(limit).iterrows():
        ha, hb = diffing.char_diff_html(r["Valor en Archivo 1"], r["Valor en Archivo 2"])
        filas.append(
            f"<tr><td>{html_lib.escape(str(r['Clave']))}</td>"
            f"<td>{html_lib.escape(str(r['Columna']))}</td>"
            f"<td class='diff-cell'>{ha}</td><td class='diff-cell'>{hb}</td>"
            f"<td>{html_lib.escape(str(r['Tipo de diferencia']))}</td>"
            f"<td>{r['Similitud']}%</td></tr>")
    return ("<table class='diff-table'><thead><tr><th>Clave</th><th>Columna</th>"
            "<th>Valor en Archivo 1</th><th>Valor en Archivo 2</th><th>Tipo de diferencia</th>"
            "<th>Similitud</th></tr></thead><tbody>" + "".join(filas) + "</tbody></table>")


@st.fragment
def comparison_section(old_df, new_df, errors, warnings, score):
    """Sección comparativa. Es un fragmento: al cambiar la clave, las columnas o
    las tolerancias solo se recalcula esta parte, por lo que el refresco es inmediato."""
    st.markdown("### Análisis Comparativo")
    render_glossary()
    common = [c for c in new_df.columns if c in old_df.columns]

    with st.expander("Ajustar reglas de comparación (clave, columnas y tolerancias)",
                     expanded=not ss.cmp["keys"]):
        keys, cols = render_rules(common, "res")
        st.caption(f"Reglas activas: {current_options().describe()}.")

    if not keys:
        st.info("Seleccione al menos una **columna clave** para ver la comparación. "
                "Los resultados se actualizan automáticamente al cambiarla.")
        return
    if not cols:
        st.info("Seleccione al menos una columna a comparar.")
        return

    opts_key = options_key()
    result = run_comparison(old_df, new_df, tuple(keys), tuple(cols), opts_key)
    inc = result.inclusion
    inclusion_card(inc)

    n_altas, n_bajas = len(result.added), len(result.removed)
    n_mod, n_igual = len(result.changed), len(result.unchanged)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        metric_card(f"+{n_altas}", f"{ESTADO_ICONO[ESTADO_ALTA]} Altas",
                    "#28a745" if n_altas == 0 else "#ffc107", help=ESTADO_AYUDA[ESTADO_ALTA])
    with c2:
        metric_card(f"-{n_bajas}", f"{ESTADO_ICONO[ESTADO_BAJA]} Bajas",
                    "#28a745" if n_bajas == 0 else "#dc3545", help=ESTADO_AYUDA[ESTADO_BAJA])
    with c3:
        metric_card(n_mod, f"{ESTADO_ICONO[ESTADO_MODIFICACION]} Modificaciones",
                    "#28a745" if n_mod == 0 else "#dc3545", help=ESTADO_AYUDA[ESTADO_MODIFICACION])
    with c4:
        metric_card(n_igual, f"{ESTADO_ICONO[ESTADO_SIN_CAMBIOS]} Sin cambios", "#6c757d",
                    help=ESTADO_AYUDA[ESTADO_SIN_CAMBIOS])
    with c5:
        metric_card(f"{inc['cobertura_exacta']}%", "% Inclusión del Archivo 1",
                    quality_color(inc["cobertura_exacta"]),
                    help="Porcentaje de registros del Archivo 1 que están, idénticos, en el Archivo 2.")

    if not result.frecuencias.empty:
        st.warning(
            f"**Desbalance de repeticiones:** {len(result.frecuencias)} clave(s) aparecen distinta cantidad de "
            f"veces en cada archivo. Quedaron sin pareja {result.huerfanos_a} registro(s) del Archivo 1 "
            f"(reportados como bajas) y {result.huerfanos_b} del Archivo 2 (reportados como altas). "
            "Vea la pestaña «Repetidos».")

    cosmeticas = (int(result.details["Tipo de diferencia"].isin(diffing.TIPOS_COSMETICOS).sum())
                  if not result.details.empty else 0)
    if cosmeticas:
        st.info(f"De las diferencias encontradas, **{cosmeticas} son de formato** (mayúsculas, tildes, espacios, "
                "formato de fecha o dentro de la tolerancia numérica). Véalas en «Detalle de diferencias».")

    tabs = st.tabs([
        f"Vista consolidada ({result.total_keys})",
        f"Detalle de diferencias ({len(result.details)})",
        f"Modificaciones ({n_mod})",
        f"Altas ({n_altas})",
        f"Bajas ({n_bajas})",
        "Orden (cruce posicional)",
        f"Repetidos ({len(result.frecuencias)})",
        "Coincidencias sugeridas",
        "Estadísticas",
    ])

    with tabs[0]:
        estados = [e for e in ESTADOS if e in set(result.consolidated["Estado"])]
        default = [e for e in estados if e != ESTADO_SIN_CAMBIOS] or estados
        filtro = st.multiselect("Mostrar", estados, default=default,
                                key=f"w_filtro_{'_'.join(estados)}",
                                format_func=lambda e: f"{ESTADO_ICONO[e]} {e}")
        view = result.consolidated[result.consolidated["Estado"].isin(filtro)]
        row_colors = view["Estado"].map(ESTADO_COLOR).fillna("")
        st.dataframe(styled(view, cell_mask=result.consolidated_mask.loc[view.index], row_colors=row_colors),
                     width="stretch", height=table_height(len(view)), hide_index=True)
        styled_note(view)

    with tabs[1]:
        det = result.details
        if det.empty:
            st.success("No hay diferencias de contenido entre los registros emparejados.")
        else:
            resumen = (det["Tipo de diferencia"].value_counts()
                       .rename_axis("Tipo de diferencia").reset_index(name="Celdas"))
            st.dataframe(resumen, hide_index=True, width="stretch", height=table_height(len(resumen), 240))
            tipos = resumen["Tipo de diferencia"].tolist()
            sel = st.multiselect("Filtrar por tipo", tipos, default=tipos, key=f"w_tipos_{'_'.join(tipos)}")
            view = det[det["Tipo de diferencia"].isin(sel)]
            st.caption("Diferencias carácter a carácter: en rojo tachado lo que está en el Archivo 1, "
                       "en verde lo que aparece en el Archivo 2.")
            with st.container(height=420, border=True):
                st.html(diff_table_html(view))
            if len(view) > 150:
                st.caption(f"Se muestran las primeras 150 de {len(view):,} diferencias. "
                           "Descargue el detalle completo para verlas todas.")
            st.download_button("Descargar detalle de diferencias (CSV)", csv_bytes(view),
                               "detalle_diferencias.csv", "text/csv", key="dl_det", on_click="ignore")

    with tabs[2]:
        if result.changed.empty:
            st.success("No se encontraron modificaciones.")
        else:
            st.caption("Cada columna comparada aparece con su valor en el **Archivo 1** y en el **Archivo 2**; "
                       "las diferencias se marcan en rojo.")
            st.dataframe(styled(result.changed, cell_mask=result.changed_mask), width="stretch",
                         height=table_height(len(result.changed)), hide_index=True)
            styled_note(result.changed)
            st.download_button("Descargar modificaciones (CSV)", csv_bytes(result.changed),
                               "modificaciones.csv", "text/csv", key="dl_mod", on_click="ignore")

    with tabs[3]:
        if result.added.empty:
            st.info("No se encontraron altas.")
        else:
            st.dataframe(styled(result.added, row_colors=pd.Series(VERDE_FONDO, index=result.added.index)),
                         width="stretch", height=table_height(len(result.added)), hide_index=True)
            st.download_button("Descargar altas (CSV)", csv_bytes(result.added), "altas.csv",
                               "text/csv", key="dl_new", on_click="ignore")

    with tabs[4]:
        if result.removed.empty:
            st.info("No se encontraron bajas.")
        else:
            st.dataframe(styled(result.removed, row_colors=pd.Series(ROJO_FONDO, index=result.removed.index)),
                         width="stretch", height=table_height(len(result.removed)), hide_index=True)
            st.download_button("Descargar bajas (CSV)", csv_bytes(result.removed), "bajas.csv",
                               "text/csv", key="dl_del", on_click="ignore")

    with tabs[5]:
        st.caption("Compara fila a fila (fila N del Archivo 1 contra fila N del Archivo 2) para detectar "
                   "desplazamientos, filas insertadas o eliminadas en la secuencia.")
        if st.toggle("Ejecutar cruce posicional", value=True, key="w_pos"):
            pos = run_positional(old_df, new_df, tuple(keys + cols), opts_key)
            if pos.mismo_orden:
                st.success("Ambos archivos tienen exactamente el mismo orden y contenido fila a fila.")
            else:
                st.warning("Los archivos **no** están en el mismo orden. Vea el detalle por fila.", icon="⚠️")
            p1, p2, p3, p4, p5 = st.columns(5)
            p1.metric("Iguales en su posición", f"{pos.iguales:,}")
            p2.metric("Desplazadas", f"{pos.desplazadas:,}", help="Mismo contenido, distinta posición.")
            p3.metric("Contenido distinto", f"{pos.distintas:,}", help="Misma posición, contenido diferente.")
            p4.metric("Solo en Archivo 1", f"{pos.solo_en_a:,}")
            p5.metric("Solo en Archivo 2", f"{pos.solo_en_b:,}")
            if not pos.detalle.empty:
                st.dataframe(pos.detalle, width="stretch", hide_index=True,
                             height=table_height(len(pos.detalle)))
                st.download_button("Descargar detalle posicional (CSV)", csv_bytes(pos.detalle),
                                   "detalle_posicional.csv", "text/csv", key="dl_pos", on_click="ignore")

    with tabs[6]:
        st.caption("Los registros con clave repetida se emparejan 1 a 1 por su orden de aparición. "
                   "Aquí se listan las claves cuya cantidad de repeticiones no coincide entre archivos.")
        if result.frecuencias.empty:
            st.success("Todas las claves aparecen la misma cantidad de veces en ambos archivos.")
        else:
            st.dataframe(result.frecuencias, width="stretch", hide_index=True,
                         height=table_height(len(result.frecuencias)))
            st.download_button("Descargar desbalance de repeticiones (CSV)", csv_bytes(result.frecuencias),
                               "repeticiones.csv", "text/csv", key="dl_frec", on_click="ignore")

    with tabs[7]:
        if not ss.cmp["fuzzy_enabled"]:
            st.info("Active «Sugerir coincidencias parciales (fuzzy matching)» en las reglas de comparación "
                    "para buscar equivalencias aproximadas entre altas y bajas.")
        elif result.fuzzy.empty:
            st.info(result.fuzzy_nota or "No se encontraron coincidencias parciales.")
        else:
            st.caption(f"Pares sugeridos con el algoritmo {ss.cmp['fuzzy_algo']} "
                       f"(similitud ≥ {ss.cmp['fuzzy_threshold']:.0%}). Son sugerencias: no se aplican "
                       "automáticamente al resultado.")
            st.dataframe(result.fuzzy, width="stretch", hide_index=True, height=table_height(len(result.fuzzy)))

    with tabs[8]:
        s1, s2 = st.columns(2)
        with s1:
            resumen_stats = pd.DataFrame({
                "Métrica": ["Total Archivo 1", "Total Archivo 2", "Sin cambios", "Altas", "Bajas", "Modificaciones",
                            "Celdas con diferencia", "Inclusión exacta del Archivo 1", "Cobertura por clave",
                            "Archivo 1 contenido en Archivo 2"],
                "Valor": [inc["total_a"], inc["total_b"], n_igual, n_altas, n_bajas, n_mod, len(result.details),
                          f"{inc['cobertura_exacta']}%", f"{inc['cobertura_clave']}%",
                          "SÍ" if inc["contenido"] else "NO"],
            })
            resumen_stats["Valor"] = resumen_stats["Valor"].astype(str)
            st.dataframe(resumen_stats, width="stretch", hide_index=True, height=table_height(10))
            st.caption(f"Reglas aplicadas: {result.options.describe()}.")
        with s2:
            fig = px.pie(values=[n_igual, n_altas, n_bajas, n_mod],
                         names=[ESTADO_SIN_CAMBIOS, ESTADO_ALTA, ESTADO_BAJA, ESTADO_MODIFICACION],
                         title='Distribución de Registros',
                         color_discrete_sequence=['#28a745', '#ffc107', '#dc3545', '#17a2b8'])
            st.plotly_chart(fig, width="stretch", key="pie_distribucion_cambios")

    st.divider()
    d1, d2 = st.columns(2)
    with d1:
        hojas = {
            "Resumen": resumen_stats,
            "Consolidado": result.consolidated,
            "Detalle diferencias": result.details,
            "Modificaciones": result.changed,
            "Altas": result.added,
            "Bajas": result.removed,
            "Repeticiones": result.frecuencias,
            "Problemas validacion": issues_to_frame(errors, warnings),
        }
        if not result.fuzzy.empty:
            hojas["Coincidencias sugeridas"] = result.fuzzy
        st.download_button("Descargar reporte completo (Excel)", to_excel(hojas),
                           "reporte_comparacion.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_report", on_click="ignore", width="stretch")
    with d2:
        if st.button("Guardar resultados en histórico", key="save_historical", width="stretch"):
            historico_id = db.guardar_historico(
                esquema=ss.cfg["esquema"],
                archivo_anterior=ss.files["old"]["name"],
                archivo_nuevo=ss.files["new"]["name"],
                score_calidad=score,
                total_registros=len(new_df),
                errores_encontrados=len(errors),
                advertencias=len(warnings),
                detalles=(f"Clave: {', '.join(keys)}. Altas: {n_altas}, Bajas: {n_bajas}, "
                          f"Modificaciones: {n_mod}, Sin cambios: {n_igual}, "
                          f"Inclusión exacta: {inc['cobertura_exacta']}%")
            )
            st.success(f"Resultados guardados en histórico (ID: {historico_id})")


def step_results():
    modo = ss.cfg["modo"]
    step_header(f"Resultados — {modo}")
    if not ss.schema_map:
        st.warning("Primero confirme el esquema de datos.")
        nav_buttons(False)
        return
    try:
        with st.spinner("Procesando..."):
            prepared = {s: prepared_slot(s)[0] for s in current_slots()}

        if modo == "Comparar archivos":
            old_df, new_df = prepared["old"], prepared["new"]
            st.caption(f"Las reglas del esquema «{ss.cfg['esquema']}» se aplican al Archivo 2 (el más reciente).")
            errors, warnings = render_validation(new_df, "cmp")
            st.markdown("#### Resumen de Registros")
            c1, c2, c3 = st.columns(3)
            score = validation_quality_score(ss.cfg["esquema"], new_df) or data_quality_score(new_df)
            with c1:
                metric_card(f"{len(old_df):,}", "Total Archivo 1")
            with c2:
                metric_card(f"{len(new_df):,}", "Total Archivo 2")
            with c3:
                metric_card(f"{score:.0f}%", "Calidad Archivo 2", quality_color(score))
            if ss.cfg["esquema"] in {"Cuentas", "Usuario", "Infraestructura"}:
                st.caption(f"Clasificación del archivo: **{quality_status(score)}**.")
            comparison_section(old_df, new_df, errors, warnings, score)
            with st.expander("Estadísticas de datos del Archivo 2"):
                render_quality(new_df, "cmp", score_override=score)

        elif modo == "Validar archivo único":
            df = prepared["single"]
            render_validation(df, "single")
            score = validation_quality_score(ss.cfg["esquema"], df) or data_quality_score(df)
            if ss.cfg["esquema"] in {"Cuentas", "Usuario", "Infraestructura"}:
                st.caption(f"Clasificación del archivo: **{quality_status(score)}**.")
            render_quality(df, "single", score_override=score)

        else:
            original = cleaned_slot("clean")
            typed = prepared["clean"]
            cleaned = dc.normalize_text_data(typed, ss.schema_map)
            text_cols = [c for c, t in ss.schema_map.items() if t == sm.TEXTO and c in cleaned.columns]
            preserved = [c for c, t in ss.schema_map.items() if t != sm.TEXTO and c in cleaned.columns]
            orig_view = original.reindex(index=cleaned.index, columns=cleaned.columns)
            changed_mask = pd.DataFrame(False, index=cleaned.index, columns=cleaned.columns)
            for c in text_cols:
                a = orig_view[c].astype("string")
                b = cleaned[c].astype("string")
                changed_mask[c] = (a.fillna("") != b.fillna("")).to_numpy()
            n_changed = int(changed_mask.to_numpy().sum())

            c1, c2, c3 = st.columns(3)
            with c1:
                metric_card(f"{len(cleaned):,}", "Registros")
            with c2:
                metric_card(n_changed, "Celdas normalizadas")
            with c3:
                metric_card(len(preserved), "Columnas conservadas")
            if preserved:
                st.info("Estas columnas **no** se modificaron para no perder su formato (correos, códigos, números, fechas): "
                        + ", ".join(f"`{c}`" for c in preserved))
            st.markdown("#### Vista previa (celdas normalizadas resaltadas)")
            st.dataframe(styled(cleaned, cell_mask=changed_mask, cell_css=f"background-color: {AMARILLO_FONDO}"),
                         width="stretch", height=420)
            styled_note(cleaned)
            base = ss.files["clean"]["name"].rsplit(".", 1)[0]
            d1, d2 = st.columns(2)
            d1.download_button("Descargar archivo limpio (Excel)", to_excel({"Datos": cleaned}), f"{base}_limpio.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               on_click="ignore", width="stretch")
            d2.download_button("Descargar archivo limpio (CSV)", csv_bytes(cleaned), f"{base}_limpio.csv",
                               "text/csv", on_click="ignore", width="stretch")
    except Exception as exc:  # noqa: BLE001
        show_error(exc, "generar los resultados")
    nav_buttons()


PANTALLAS = {P_CARGA: step_upload, P_ESQUEMA: step_schema, P_REGLAS: step_rules, P_RESULTADOS: step_results}
PANTALLAS[paso_actual()]()
