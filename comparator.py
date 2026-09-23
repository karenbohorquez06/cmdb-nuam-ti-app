"""Motor de comparación de archivos.

Incluye:
- Emparejamiento 1:1 de registros duplicados por índice de ocurrencia (no se descarta ninguna fila).
- Tolerancias configurables (numérica, de formato de fecha, mayúsculas, tildes, espacios).
- Doble cruce: por clave (desorden) y posicional (orden).
- Verificación de inclusión del Archivo 1 en el Archivo 2.
- Detalle por celda con el tipo de diferencia y coincidencia difusa opcional.
"""
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List

import numpy as np
import pandas as pd

import diffing

ESTADO_ALTA = "Alta"
ESTADO_BAJA = "Baja"
ESTADO_MODIFICACION = "Modificación"
ESTADO_SIN_CAMBIOS = "Sin cambios"
ESTADOS = [ESTADO_ALTA, ESTADO_BAJA, ESTADO_MODIFICACION, ESTADO_SIN_CAMBIOS]
ESTADO_ICONO = {ESTADO_ALTA: "🟢", ESTADO_BAJA: "🔴", ESTADO_MODIFICACION: "🟡", ESTADO_SIN_CAMBIOS: "⚪"}
ESTADO_AYUDA = {
    ESTADO_ALTA: "Altas (registros nuevos / inserciones): registros presentes en el Archivo 2 que no existen en el Archivo 1.",
    ESTADO_BAJA: "Bajas (registros eliminados / ausentes): registros presentes en el Archivo 1 que no existen en el Archivo 2. "
                 "Afectan directamente el porcentaje de inclusión del Archivo 1.",
    ESTADO_MODIFICACION: "Modificaciones (diferencias de contenido): registros que coinciden en la clave entre ambos archivos, "
                         "pero presentan variaciones en una o más columnas.",
    ESTADO_SIN_CAMBIOS: "Sin cambios (coincidencias exactas): registros idénticos en ambos archivos.",
}

SUFIJO_ANTERIOR = " (Archivo 1)"
SUFIJO_NUEVO = " (Archivo 2)"
COL_OCURRENCIA = "Ocurrencia"
COL_CAMBIOS = "Columnas con cambios"
_SEP = "‖"
_VACIO = "∅"


@dataclass
class CompareOptions:
    """Reglas de coincidencia configurables desde la interfaz."""
    ignore_case: bool = False
    ignore_accents: bool = False
    ignore_spaces: bool = True
    numeric_tolerance: float = 0.0
    date_tolerance: bool = True
    excluded: List[str] = field(default_factory=list)
    fuzzy_enabled: bool = False
    fuzzy_algo: str = diffing.JARO_WINKLER
    fuzzy_threshold: float = 0.85

    def describe(self):
        partes = []
        partes.append("ignora mayúsculas" if self.ignore_case else "distingue mayúsculas")
        partes.append("ignora tildes" if self.ignore_accents else "distingue tildes")
        partes.append("ignora espacios sobrantes" if self.ignore_spaces else "distingue espacios")
        partes.append(f"tolerancia numérica ±{self.numeric_tolerance:g}" if self.numeric_tolerance
                      else "sin tolerancia numérica")
        partes.append("ignora formato de fecha" if self.date_tolerance else "compara fechas literalmente")
        if self.excluded:
            partes.append(f"{len(self.excluded)} columna(s) excluida(s)")
        return "; ".join(partes)


@dataclass
class PositionalResult:
    """Resultado del cruce posicional (fila N de A contra fila N de B)."""
    mismo_orden: bool = True
    iguales: int = 0
    desplazadas: int = 0
    distintas: int = 0
    solo_en_a: int = 0
    solo_en_b: int = 0
    detalle: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class ComparisonResult:
    added: pd.DataFrame
    removed: pd.DataFrame
    changed: pd.DataFrame
    unchanged: pd.DataFrame
    changed_mask: pd.DataFrame = field(default_factory=pd.DataFrame)
    consolidated: pd.DataFrame = field(default_factory=pd.DataFrame)
    consolidated_mask: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Detalle celda a celda de cada diferencia, con su tipo y similitud.
    details: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Claves cuya cantidad de repeticiones difiere entre archivos.
    frecuencias: pd.DataFrame = field(default_factory=pd.DataFrame)
    huerfanos_a: int = 0
    huerfanos_b: int = 0
    # Sugerencias de coincidencia difusa entre bajas y altas.
    fuzzy: pd.DataFrame = field(default_factory=pd.DataFrame)
    fuzzy_nota: str = ""
    inclusion: dict = field(default_factory=dict)
    total_keys: int = 0
    cols: List[str] = field(default_factory=list)
    keys: List[str] = field(default_factory=list)
    options: CompareOptions = field(default_factory=CompareOptions)


# ---------------------------------------------------------------------------
# Normalización y comparación de valores
# ---------------------------------------------------------------------------
def _text_series(series):
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.strftime("%Y-%m-%d %H:%M:%S").astype("string")
    return series.astype("string")


def _norm_text(series, opts, for_key=False):
    out = _text_series(series).str.strip()
    if opts.ignore_spaces or for_key:
        out = out.str.replace(r"\s+", " ", regex=True)
    if opts.ignore_accents:
        out = out.map(lambda v: v if pd.isna(v) else diffing.strip_accents(v))
    if opts.ignore_case:
        out = out.str.lower()
    return out.mask(out == "")


def _parse_dates(series):
    from schema_mapper import parse_dates
    return parse_dates(series)


def _equal_column(a, b, opts):
    """Serie booleana: True donde los valores se consideran iguales."""
    both_na = a.isna() & b.isna()
    numeric = (pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b)
               and not pd.api.types.is_bool_dtype(a) and not pd.api.types.is_bool_dtype(b))
    if numeric:
        av, bv = a.astype("float64").to_numpy(), b.astype("float64").to_numpy()
        with np.errstate(invalid="ignore"):
            delta = np.abs(av - bv)
            close = delta <= max(opts.numeric_tolerance, 0) if opts.numeric_tolerance \
                else np.isclose(av, bv, rtol=1e-12, atol=1e-12, equal_nan=False)
        return pd.Series(np.nan_to_num(close, nan=False).astype(bool), index=a.index) | both_na

    fechas = pd.api.types.is_datetime64_any_dtype(a) and pd.api.types.is_datetime64_any_dtype(b)
    if fechas and opts.date_tolerance:
        return ((a.dt.floor("s") == b.dt.floor("s")).fillna(False)) | both_na
    if opts.date_tolerance and not fechas:
        # Columnas de texto que en realidad son fechas: se comparan por su valor, no por su formato.
        da, db = _parse_dates(a), _parse_dates(b)
        parseables = da.notna() & db.notna()
        if parseables.any():
            iguales_texto = (_norm_text(a, opts) == _norm_text(b, opts)).fillna(False)
            iguales_fecha = (da == db).fillna(False)
            return (iguales_texto | (parseables & iguales_fecha)) | both_na

    na, nb = _norm_text(a, opts), _norm_text(b, opts)
    return (na == nb).fillna(False) | both_na


def _occurrence_keys(df, keys, opts):
    """Clave de negocio y clave sintética (negocio + índice de ocurrencia) para cruzar 1:1."""
    parts = [_norm_text(df[k], opts, for_key=True).fillna(_VACIO) for k in keys]
    business = parts[0]
    for p in parts[1:]:
        business = business + _SEP + p
    business = pd.Series(business.to_numpy(), index=df.index, dtype="string")
    occurrence = business.groupby(business).cumcount()
    synthetic = business + "#" + occurrence.astype("string")
    return business, occurrence, synthetic


# ---------------------------------------------------------------------------
# Cruce por clave (desorden)
# ---------------------------------------------------------------------------
def compare_dataframes(old_df, new_df, keys: List[str], cols: List[str],
                       options: CompareOptions = None) -> ComparisonResult:
    opts = options or CompareOptions()
    keys = list(keys)
    cols = [c for c in cols
            if c not in keys and c not in opts.excluded and c in old_df.columns and c in new_df.columns]

    old, new = old_df.copy(), new_df.copy()
    b_old, occ_old, k_old = _occurrence_keys(old, keys, opts)
    b_new, occ_new, k_new = _occurrence_keys(new, keys, opts)
    old["__occ__"], new["__occ__"] = occ_old.to_numpy() + 1, occ_new.to_numpy() + 1
    old_i = old.set_index(pd.Index(k_old.to_numpy(), name="__key__"))
    new_i = new.set_index(pd.Index(k_new.to_numpy(), name="__key__"))

    added_idx = new_i.index.difference(old_i.index, sort=False)
    removed_idx = old_i.index.difference(new_i.index, sort=False)
    common_idx = new_i.index.intersection(old_i.index, sort=False)

    # Desbalance de frecuencias: la misma clave repetida N veces en A y M en B.
    cnt_old = b_old.value_counts()
    cnt_new = b_new.value_counts()
    todas = cnt_old.index.union(cnt_new.index)
    frec = pd.DataFrame({
        "Clave": [str(k).replace(_SEP, " | ") for k in todas],
        "Veces en Archivo 1": cnt_old.reindex(todas).fillna(0).astype(int).to_numpy(),
        "Veces en Archivo 2": cnt_new.reindex(todas).fillna(0).astype(int).to_numpy(),
    })
    frec = frec[(frec["Veces en Archivo 1"] != frec["Veces en Archivo 2"])
                & (frec["Veces en Archivo 1"] > 0) & (frec["Veces en Archivo 2"] > 0)].copy()
    if not frec.empty:
        frec["Sin pareja"] = (frec["Veces en Archivo 1"] - frec["Veces en Archivo 2"]).abs()
        frec["Quedan sin par en"] = np.where(frec["Veces en Archivo 1"] > frec["Veces en Archivo 2"],
                                             "Archivo 1 (bajas)", "Archivo 2 (altas)")
        frec = frec.sort_values("Sin pareja", ascending=False).reset_index(drop=True)
    huerfanos_a = int(frec.loc[frec["Quedan sin par en"].str.startswith("Archivo 1"), "Sin pareja"].sum()) if not frec.empty else 0
    huerfanos_b = int(frec.loc[frec["Quedan sin par en"].str.startswith("Archivo 2"), "Sin pareja"].sum()) if not frec.empty else 0

    o = old_i.loc[common_idx]
    n = new_i.loc[common_idx]
    diff = pd.DataFrame(index=common_idx)
    for c in cols:
        diff[c] = ~_equal_column(o[c], n[c], opts)
    changed_flag = diff.any(axis=1) if cols else pd.Series(False, index=common_idx)
    ch_idx = common_idx[changed_flag.to_numpy()]
    same_idx = common_idx[~changed_flag.to_numpy()]

    hay_duplicados = bool((old_i["__occ__"] > 1).any() or (new_i["__occ__"] > 1).any())

    def _visible(df_part, extra_cols):
        out = df_part[extra_cols].copy()
        if hay_duplicados:
            out.insert(0, COL_OCURRENCIA, df_part["__occ__"].to_numpy())
        return out

    added = _visible(new_i.loc[added_idx], keys + cols).reset_index(drop=True)
    removed = _visible(old_i.loc[removed_idx], keys + cols).reset_index(drop=True)
    unchanged = _visible(n.loc[same_idx], keys + cols).reset_index(drop=True)

    # Tabla de modificaciones: clave + valores (Archivo 1) / (Archivo 2)
    changed = _visible(n.loc[ch_idx], keys)
    mask = pd.DataFrame(False, index=changed.index, columns=changed.columns)
    changed[COL_CAMBIOS] = [", ".join(c for c in cols if diff.at[k, c]) for k in ch_idx]
    mask[COL_CAMBIOS] = False
    for c in sorted(cols, key=lambda c: not diff.loc[ch_idx, c].any()):
        changed[c + SUFIJO_ANTERIOR] = o.loc[ch_idx, c]
        changed[c + SUFIJO_NUEVO] = n.loc[ch_idx, c]
        mask[c + SUFIJO_ANTERIOR] = diff.loc[ch_idx, c]
        mask[c + SUFIJO_NUEVO] = diff.loc[ch_idx, c]
    changed = changed.reset_index(drop=True)
    mask = mask.reset_index(drop=True)

    # Detalle celda a celda con el tipo de diferencia
    detalle = []
    for k in ch_idx:
        clave = str(k).split("#")[0].replace(_SEP, " | ")
        for c in cols:
            if not diff.at[k, c]:
                continue
            va, vb = o.at[k, c], n.at[k, c]
            tipo, sim = diffing.classify_difference(va, vb, opts.numeric_tolerance,
                                                    opts.date_tolerance, opts.fuzzy_algo)
            detalle.append({
                "Clave": clave,
                COL_OCURRENCIA: int(n.at[k, "__occ__"]),
                "Columna": c,
                "Valor en Archivo 1": diffing._as_text(va),
                "Valor en Archivo 2": diffing._as_text(vb),
                "Tipo de diferencia": tipo,
                "Similitud": round(sim * 100, 1),
            })
    details = pd.DataFrame(detalle, columns=["Clave", COL_OCURRENCIA, "Columna", "Valor en Archivo 1",
                                             "Valor en Archivo 2", "Tipo de diferencia", "Similitud"])
    if not hay_duplicados and not details.empty:
        details = details.drop(columns=COL_OCURRENCIA)

    # Vista consolidada
    view_cols = ([COL_OCURRENCIA] if hay_duplicados else []) + keys + cols
    frames, masks = [], []
    for part, estado, cell_mask in (
        (_visible(n.loc[ch_idx], keys + cols), ESTADO_MODIFICACION, diff.loc[ch_idx, cols]),
        (_visible(new_i.loc[added_idx], keys + cols), ESTADO_ALTA, None),
        (_visible(old_i.loc[removed_idx], keys + cols), ESTADO_BAJA, None),
        (_visible(n.loc[same_idx], keys + cols), ESTADO_SIN_CAMBIOS, None),
    ):
        part = part.copy()
        part.insert(0, "Estado", estado)
        part = part.reindex(columns=["Estado"] + view_cols)
        m = pd.DataFrame(False, index=part.index, columns=part.columns)
        if cell_mask is not None:
            for c in cols:
                m[c] = cell_mask[c].to_numpy()
        frames.append(part)
        masks.append(m)
    consolidated = pd.concat(frames, ignore_index=True)
    consolidated_mask = pd.concat(masks, ignore_index=True)

    # Inclusión del Archivo 1 en el Archivo 2
    total_a, total_b = len(old_i), len(new_i)
    encontrados = len(common_idx)
    identicos = len(same_idx)
    inclusion = {
        "total_a": total_a,
        "total_b": total_b,
        "encontrados": encontrados,
        "identicos": identicos,
        "faltantes": len(removed_idx),
        "cobertura_clave": round(100 * encontrados / total_a, 2) if total_a else 0.0,
        "cobertura_exacta": round(100 * identicos / total_a, 2) if total_a else 0.0,
        "contenido": len(removed_idx) == 0 and len(ch_idx) == 0,
        "contenido_por_clave": len(removed_idx) == 0,
    }

    fuzzy, fuzzy_nota = _fuzzy_suggestions(old_i.loc[removed_idx], new_i.loc[added_idx], keys, cols, opts)

    return ComparisonResult(
        added=added, removed=removed, changed=changed, unchanged=unchanged,
        changed_mask=mask, consolidated=consolidated, consolidated_mask=consolidated_mask,
        details=details, frecuencias=frec, huerfanos_a=huerfanos_a, huerfanos_b=huerfanos_b,
        fuzzy=fuzzy, fuzzy_nota=fuzzy_nota, inclusion=inclusion,
        total_keys=len(new_i.index.union(old_i.index)), cols=cols, keys=keys, options=opts,
    )


def _fuzzy_suggestions(removed, added, keys, cols, opts, max_pairs=40000, top=200):
    """Empareja bajas con altas por similitud de texto para sugerir correspondencias."""
    if not opts.fuzzy_enabled:
        return pd.DataFrame(), ""
    if removed.empty or added.empty:
        return pd.DataFrame(), "No hay bajas y altas para emparejar."
    if len(removed) * len(added) > max_pairs:
        return pd.DataFrame(), (f"Se omitió la coincidencia difusa: {len(removed):,} bajas × {len(added):,} altas "
                                f"superan el límite de {max_pairs:,} combinaciones.")
    def _texto(df, columnas):
        if not columnas:
            return [""] * len(df)
        return [" | ".join("" if pd.isna(v) else str(v) for v in fila)
                for fila in df[columnas].to_numpy()]

    claves_a, claves_b = _texto(removed, keys), _texto(added, keys)
    # La similitud se calcula sobre el registro completo (clave + columnas comparadas),
    # para no sugerir pares que solo se parecen en el identificador.
    regs_a, regs_b = _texto(removed, keys + cols), _texto(added, keys + cols)
    filas = []
    for ia, ra in enumerate(regs_a):
        mejor, mejor_sim = None, 0.0
        for ib, rb in enumerate(regs_b):
            sim = diffing.similarity(ra, rb, opts.fuzzy_algo)
            if sim > mejor_sim:
                mejor, mejor_sim = ib, sim
        if mejor is not None and mejor_sim >= opts.fuzzy_threshold:
            tipo, _ = diffing.classify_difference(regs_a[ia], regs_b[mejor], algoritmo=opts.fuzzy_algo)
            filas.append({
                "Baja en Archivo 1": claves_a[ia],
                "Posible alta equivalente en Archivo 2": claves_b[mejor],
                "Similitud": round(mejor_sim * 100, 1),
                "Tipo de diferencia": tipo,
                "Registro en Archivo 1": regs_a[ia],
                "Registro en Archivo 2": regs_b[mejor],
            })
    df = pd.DataFrame(filas, columns=["Baja en Archivo 1", "Posible alta equivalente en Archivo 2",
                                      "Similitud", "Tipo de diferencia",
                                      "Registro en Archivo 1", "Registro en Archivo 2"])
    if df.empty:
        return df, f"No se encontraron pares con similitud ≥ {opts.fuzzy_threshold:.0%}."
    return df.sort_values("Similitud", ascending=False).head(top).reset_index(drop=True), ""


# ---------------------------------------------------------------------------
# Cruce posicional (orden)
# ---------------------------------------------------------------------------
def compare_positional(old_df, new_df, columnas: List[str], opts: CompareOptions = None,
                       max_detalle=500) -> PositionalResult:
    """Compara fila a fila (fila N de A contra fila N de B) e identifica
    desplazamientos, inserciones y eliminaciones secuenciales."""
    opts = opts or CompareOptions()
    columnas = [c for c in columnas if c in old_df.columns and c in new_df.columns]
    if not columnas:
        return PositionalResult(detalle=pd.DataFrame())

    def firmas(df):
        norm = [_norm_text(df[c], opts).fillna(_VACIO) for c in columnas]
        s = norm[0]
        for p in norm[1:]:
            s = s + _SEP + p
        return s.tolist()

    fa, fb = firmas(old_df), firmas(new_df)
    filas_a, filas_b = list(old_df.index), list(new_df.index)
    matcher = SequenceMatcher(None, fa, fb, autojunk=False)

    iguales = desplazadas = distintas = solo_a = solo_b = 0
    detalle = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                if (i1 + k) == (j1 + k):
                    iguales += 1
                else:
                    desplazadas += 1
                    if len(detalle) < max_detalle:
                        detalle.append({
                            "Tipo": "Desplazada",
                            "Fila en Archivo 1": filas_a[i1 + k],
                            "Fila en Archivo 2": filas_b[j1 + k],
                            "Detalle": f"Mismo contenido en distinta posición (posición {i1 + k + 1} → {j1 + k + 1}).",
                        })
        elif tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                ia, jb = i1 + k, j1 + k
                hay_a, hay_b = ia < i2, jb < j2
                if hay_a and hay_b:
                    distintas += 1
                    tipo = "Contenido distinto en la misma posición"
                    texto = "Las filas ocupan la misma posición pero su contenido no coincide."
                elif hay_a:
                    solo_a += 1
                    tipo = "Solo en Archivo 1"
                    texto = f"Fila sin equivalente en la secuencia del Archivo 2 (posición {ia + 1})."
                else:
                    solo_b += 1
                    tipo = "Solo en Archivo 2"
                    texto = f"Fila sin equivalente en la secuencia del Archivo 1 (posición {jb + 1})."
                if len(detalle) < max_detalle:
                    detalle.append({
                        "Tipo": tipo,
                        "Fila en Archivo 1": filas_a[ia] if hay_a else "—",
                        "Fila en Archivo 2": filas_b[jb] if hay_b else "—",
                        "Detalle": texto,
                    })
        elif tag == "delete":
            for k in range(i1, i2):
                solo_a += 1
                if len(detalle) < max_detalle:
                    detalle.append({
                        "Tipo": "Solo en Archivo 1",
                        "Fila en Archivo 1": filas_a[k],
                        "Fila en Archivo 2": "—",
                        "Detalle": f"Fila eliminada respecto de la secuencia (posición {k + 1}).",
                    })
        elif tag == "insert":
            for k in range(j1, j2):
                solo_b += 1
                if len(detalle) < max_detalle:
                    detalle.append({
                        "Tipo": "Solo en Archivo 2",
                        "Fila en Archivo 1": "—",
                        "Fila en Archivo 2": filas_b[k],
                        "Detalle": f"Fila insertada en la secuencia (posición {k + 1}).",
                    })
    tabla = pd.DataFrame(detalle, columns=["Tipo", "Fila en Archivo 1", "Fila en Archivo 2", "Detalle"])
    # Las columnas de fila mezclan números y «—», así que se muestran como texto.
    for c in ("Fila en Archivo 1", "Fila en Archivo 2"):
        tabla[c] = tabla[c].astype("string")
    return PositionalResult(
        mismo_orden=(desplazadas == 0 and distintas == 0 and solo_a == 0 and solo_b == 0),
        iguales=iguales, desplazadas=desplazadas, distintas=distintas,
        solo_en_a=solo_a, solo_en_b=solo_b, detalle=tabla,
    )
