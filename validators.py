"""Reglas de validación por esquema (Licencias TI, Dominios, Certificados)."""
import re
import ipaddress
from datetime import datetime
import unicodedata

import pandas as pd


def _num(row, col):
    """Valor numérico de una celda, o None si está vacía o no es número."""
    value = pd.to_numeric(row.get(col), errors="coerce")
    return None if pd.isna(value) else float(value)


# Función de validación para Licencias TI (con integridad referencial)
def validate_licencias(df, db):
    errors = []
    warnings = []
    # Obtener datos de referencia
    proveedores_validos = set(db.obtener_proveedores())
    aplicaciones_validas = set(db.obtener_aplicaciones())
    usuarios_validos = {str(u['email']).lower() for u in db.obtener_usuarios()}
    # Listas de valores permitidos
    paises_permitidos = ['Colombia', 'Perú', 'Chile', 'tranversal']
    tipo_lic_permitidos = ['Hardware', 'Software', 'Soporte', 'Nube']
    tipo_vigencia_permitidos = ['Activo', 'Por Renovar', 'Por vencer', 'Vencido', 'Inactivo']
    tipo_usuario_permitidos = ['Equipos de Computo', 'Celulares', 'Personas', 'Cuentas']
    tipo_entorno_permitidos = ['Producción', 'Pruebas', 'Certificación', 'Todos los Anteriores', 'No Aplica']
    estado_permitidos = ['Vigente', 'Vencida', 'Finalizada']
    moneda_permitidos = ['USD', 'UF', 'COP', 'CLP', 'PEN', 'EUR', 'Varias monedas']
    for idx, row in df.iterrows():    
        # Validar Producto asociado
        if pd.notna(row.get('Producto asociado')):
            if row['Producto asociado'] not in aplicaciones_validas:
                warnings.append(f"Fila {idx}: Producto asociado '{row['Producto asociado']}' no existe en aplicaciones")
        # Validar Responsable/Correo
        if pd.notna(row.get('Responsable / Correo')):
            correo = str(row['Responsable / Correo']).strip()
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, correo):
                warnings.append(f"Fila {idx}: Formato de correo inválido: {correo}")
            elif correo.lower() not in usuarios_validos:
                warnings.append(f"Fila {idx}: Responsable '{correo}' no existe en usuarios")
        # Validar País
        if pd.notna(row.get('Pais')) and row['Pais'] not in paises_permitidos:
            errors.append(f"Fila {idx}: País '{row['Pais']}' no permitido")
        # Validar cantidades
        total = _num(row, 'Cantidad Total')
        asignadas = _num(row, 'Cantidad Asignadas')
        disponible = _num(row, 'Cantidad Disponible')
        if total is not None and total < 0:
            errors.append(f"Fila {idx}: Cantidad Total no puede ser negativa")
        if asignadas is not None and asignadas < 0:
            errors.append(f"Fila {idx}: Cantidad Asignadas no puede ser negativa")
        if total is not None and asignadas is not None:
            if asignadas > total:
                errors.append(f"Fila {idx}: Cantidad Asignadas ({asignadas:g}) > Cantidad Total ({total:g})")
            disponible_esperado = total - asignadas
            if disponible is not None and abs(disponible - disponible_esperado) > 0.01:
                warnings.append(f"Fila {idx}: Cantidad Disponible ({disponible:g}) no coincide con cálculo ({disponible_esperado:g})")
        # Validar fechas
        if all(pd.notna(row.get(col)) for col in ['Fecha Compra', 'Fecha Vencimiento']):
            try:
                fecha_compra = pd.to_datetime(row['Fecha Compra'])
                fecha_vencimiento = pd.to_datetime(row['Fecha Vencimiento'])
                if fecha_compra > fecha_vencimiento:
                    errors.append(f"Fila {idx}: Fecha Compra es posterior a Fecha Vencimiento")
            except (ValueError, TypeError):
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
            except (ValueError, TypeError):
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
                dias_archivo = _num(row, 'Dias Restantes')
                if dias_archivo is not None and abs(dias_archivo - dias_restantes) > 1:
                    warnings.append(f"Fila {idx}: Días Restantes ({dias_archivo:g}) no coincide con cálculo ({dias_restantes})")
            except (ValueError, TypeError):
                warnings.append(f"Fila {idx}: Formato de fecha inválido en Fecha Vencimiento")
        # Validar URL
        if pd.notna(row.get('Enlace Certificado')):
            url_pattern = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
            if not re.match(url_pattern, str(row['Enlace Certificado'])):
                warnings.append(f"Fila {idx}: URL inválida en Enlace Certificado")
    return errors, warnings


CUENTAS_FIELDS = {
    "nombre": ("Nombre cuenta", "Nombre de cuenta", "Cuenta"),
    "usuario": ("Usuario", "Username", "Nombre usuario"),
    "estado": ("Estado",),
    "ticket_creacion": ("Ticket de Creación de Usuario", "Ticket Creacion Usuario", "Ticket de Creacion de Usuario"),
    "ticket_retiro": ("Ticket de Retiro de usuario", "Ticket Retiro Usuario", "Ticket de Retiro Usuario"),
    "novedad": ("Novedad",),
    "criticidad": ("Criticidad SI", "Criticidad"),
    "datos_personales": ("Datos Personales", "Datos personales"),
    "pais": ("País", "Pais"),
    "password": ("Password Inicial", "Contraseña Inicial", "Contrasena Inicial"),
    "descripcion": ("Descripción", "Descripcion"),
    "usuario_2026": ("usuario 2026", "Usuario 2026"),
    "disponibilidad": ("Disponibilidad",),
    "confidencialidad": ("Confidencialidad",),
    "integridad": ("Integridad",),
}

CUENTAS_WEIGHTS = {"alto": 0.40, "medio": 0.35, "bajo": 0.25}
CUENTAS_ENUMS = {
    "estado": {"ACTIVO", "INACTIVO", "SUSPENDIDO", "RETIRADO"},
    "novedad": {"CREACION", "MODIFICACION", "RETIRO", "SIN NOVEDAD"},
    "criticidad": {"ALTA", "MEDIA", "BAJA", "CRITICA"},
    "cia": {"ALTO", "MEDIO", "BAJO", "1", "2", "3"},
}
CUENTAS_TICKET_RE = re.compile(r"^TK-[0-9]{6,}$", re.IGNORECASE)
CUENTAS_USUARIO_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
CUENTAS_COUNTRIES = {"CO", "COL", "COLOMBIA", "PA", "PANAMA", "PE", "PER", "PERU", "PERÚ",
                     "CL", "CHL", "CHILE", "MX", "MEX", "MEXICO", "MÉXICO", "US", "USA", "ESTADOS UNIDOS"}


def _canonical(value):
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _cuentas_columns(df):
    by_name = {_canonical(c): c for c in df.columns}
    found = {}
    for key, alternatives in CUENTAS_FIELDS.items():
        for alternative in alternatives:
            if _canonical(alternative) in by_name:
                found[key] = by_name[_canonical(alternative)]
                break
    return found


def _present(value):
    return pd.notna(value) and str(value).strip() != ""


def _text(value):
    return str(value).strip()


def _valid_boolean_or_mask(value):
    if isinstance(value, bool):
        return True
    return _text(value).upper() in {"TRUE", "FALSE", "VERDADERO", "FALSO", "SI", "SÍ", "NO", "1", "0"} or bool(re.match(r"^[A-Za-z0-9_./-]+$", _text(value)))


def _valid_cia(value):
    return _text(value).upper() in CUENTAS_ENUMS["cia"]


def _add_missing(errors, row_idx, label):
    errors.append(f"Fila {row_idx}: {label} es obligatorio para el esquema Cuentas")


def validate_cuentas(df, db=None):
    """Valida cuentas por criticidad y devuelve errores y advertencias."""
    errors, warnings = [], []
    columns = _cuentas_columns(df)
    missing_columns = [label for key, label in (
        ("nombre", "Nombre cuenta"), ("usuario", "Usuario"), ("estado", "Estado")) if key not in columns]
    for label in missing_columns:
        errors.append(f"Columna obligatoria ausente: {label}")
    if missing_columns:
        return errors, warnings

    duplicate_users = df[columns["usuario"]].astype("string").str.strip().duplicated(keep=False)
    for idx in df.index[duplicate_users.fillna(False)]:
        errors.append(f"Fila {idx}: Usuario '{df.at[idx, columns['usuario']]}' está repetido; debe ser único")

    for idx, row in df.iterrows():
        nombre = row[columns["nombre"]]
        usuario = row[columns["usuario"]]
        estado = _text(row[columns["estado"]]).upper() if _present(row[columns["estado"]]) else ""

        if not _present(nombre):
            _add_missing(errors, idx, "Nombre cuenta")
        else:
            nombre_text = _text(nombre)
            if not 3 <= len(nombre_text) <= 100:
                errors.append(f"Fila {idx}: Nombre cuenta debe tener entre 3 y 100 caracteres")
            if not re.match(r"^[\wÀ-ÿ]", nombre_text) or not re.match(r".*[\wÀ-ÿ]$", nombre_text):
                errors.append(f"Fila {idx}: Nombre cuenta no puede iniciar ni terminar con caracteres especiales")

        if not _present(usuario):
            _add_missing(errors, idx, "Usuario")
        elif not CUENTAS_USUARIO_RE.fullmatch(_text(usuario)):
            errors.append(f"Fila {idx}: Usuario debe ser alfanumérico y no contener espacios")

        if not _present(row[columns["estado"]]):
            _add_missing(errors, idx, "Estado")
        elif estado not in CUENTAS_ENUMS["estado"]:
            errors.append(f"Fila {idx}: Estado '{row[columns['estado']]}' no permitido")

        for key, label in (("ticket_creacion", "Ticket de Creación de Usuario"), ("ticket_retiro", "Ticket de Retiro de usuario")):
            if key not in columns:
                continue
            value = row[columns[key]]
            required = (key == "ticket_creacion" and estado != "RETIRADO") or (key == "ticket_retiro" and estado == "RETIRADO")
            if required and not _present(value):
                errors.append(f"Fila {idx}: {label} es obligatorio para el estado {estado}")
            elif _present(value) and not CUENTAS_TICKET_RE.fullmatch(_text(value)):
                errors.append(f"Fila {idx}: {label} debe cumplir el patrón TK-000000")

        if "novedad" in columns and _present(row[columns["novedad"]]) and _text(row[columns["novedad"]]).upper() not in CUENTAS_ENUMS["novedad"]:
            warnings.append(f"Fila {idx}: Novedad '{row[columns['novedad']]}' no está permitida")
        if "criticidad" in columns and _present(row[columns["criticidad"]]) and _text(row[columns["criticidad"]]).upper() not in CUENTAS_ENUMS["criticidad"]:
            warnings.append(f"Fila {idx}: Criticidad SI '{row[columns['criticidad']]}' no está permitida")
        if "datos_personales" in columns and _present(row[columns["datos_personales"]]) and not _valid_boolean_or_mask(row[columns["datos_personales"]]):
            warnings.append(f"Fila {idx}: Datos Personales debe ser lógico o una máscara de protección válida")
        if "pais" in columns and _present(row[columns["pais"]]) and _text(row[columns["pais"]]).upper() not in CUENTAS_COUNTRIES:
            warnings.append(f"Fila {idx}: País '{row[columns['pais']]}' no corresponde a un código o catálogo válido")
        if "password" in columns and _present(row[columns["password"]]) and len(_text(row[columns["password"]])) < 8:
            warnings.append(f"Fila {idx}: Password Inicial debe tener al menos 8 caracteres")
        if "descripcion" in columns and _present(row[columns["descripcion"]]) and len(_text(row[columns["descripcion"]])) > 500:
            warnings.append(f"Fila {idx}: Descripción no puede superar 500 caracteres")
        for key, label in (("disponibilidad", "Disponibilidad"), ("confidencialidad", "Confidencialidad"), ("integridad", "Integridad")):
            if key in columns and _present(row[columns[key]]) and not _valid_cia(row[columns[key]]):
                warnings.append(f"Fila {idx}: {label} debe ser ALTO, MEDIO, BAJO o 1, 2, 3")

    groups = {
        "alto": [("nombre", 0.0), ("usuario", 0.0), ("estado", 0.0)],
        "medio": [("ticket_creacion", 0.0), ("ticket_retiro", 0.0), ("novedad", 0.0), ("criticidad", 0.02), ("datos_personales", 0.05)],
        "bajo": [("pais", 0.10), ("password", 1.0), ("descripcion", 0.20), ("usuario_2026", 0.15), ("disponibilidad", 0.10), ("confidencialidad", 0.10), ("integridad", 0.10)],
    }
    for group, fields in groups.items():
        for key, tolerance in fields:
            if key not in columns or df.empty:
                continue
            null_ratio = (~df[columns[key]].map(_present)).mean()
            if null_ratio > tolerance:
                target = errors if group == "alto" or (group == "medio" and key in {"ticket_creacion", "ticket_retiro"}) else warnings
                target.append(f"Columna {columns[key]}: porcentaje de nulos {null_ratio:.1%} supera la tolerancia de {tolerance:.0%}")
    return errors, warnings


def cuentas_quality_score(df):
    """Calcula el índice ponderado de Cuentas con pesos 40%, 35% y 25%."""
    columns = _cuentas_columns(df)
    if df.empty:
        return 0.0
    groups = {
        "alto": ["nombre", "usuario", "estado"],
        "medio": ["ticket_creacion", "ticket_retiro", "novedad", "criticidad", "datos_personales"],
        "bajo": ["pais", "password", "descripcion", "usuario_2026", "disponibilidad", "confidencialidad", "integridad"],
    }
    scores = []
    for group, fields in groups.items():
        field_scores = []
        for key in fields:
            if key not in columns:
                continue
            present = df[columns[key]].map(_present)
            field_scores.append(float(present.mean()) * 100)
        if field_scores:
            scores.append(CUENTAS_WEIGHTS[group] * (sum(field_scores) / len(field_scores)))
    return round(sum(scores), 2) if scores else 0.0


USUARIO_FIELDS = {
    "nombre": ("Nombre", "Nombre usuario", "Nombre completo"),
    "estado": ("Estado",),
    "email": ("Correo Email", "Correo electrónico", "Correo electronico", "Email", "Correo"),
    "identificacion": ("Identificación", "Identificacion", "Documento", "Número de identificación", "Numero de identificacion"),
    "tipo_identificacion": ("Tipo de Identificación", "Tipo de Identificacion", "Tipo Documento"),
    "empresa": ("Empresa Propietaria", "Empresa propietaria", "Empresa"),
    "ticket_ingreso": ("Ticket de Ingreso", "Ticket Ingreso", "Ticket de Creación", "Ticket Creacion"),
    "ticket_retiro": ("Ticket de Retiro", "Ticket Retiro"),
    "telefono": ("Teléfono Principal", "Telefono Principal", "Teléfono", "Telefono"),
    "gerencia": ("Gerencia",),
    "cargo": ("Cargo",),
    "tipo_cargo": ("Tipo Cargo",),
    "lider": ("Líder Inmediato", "Lider Inmediato"),
    "grupo": ("Grupo",),
    "grupo_jira": ("Grupo Jira", "Grupo JIRA"),
    "tipo_usuario": ("Tipo Usuario",),
    "critico": ("Crítico", "Critico"),
    "pais": ("País", "Pais"),
    "direccion": ("Dirección", "Direccion"),
    "zip": ("ZIP", "Código Postal", "Codigo Postal"),
    "telefono_alternativo": ("Teléfono Alternativo", "Telefono Alternativo"),
    "nombre_contacto": ("Nombre Contacto",),
    "notificacion": ("Notificación", "Notificacion"),
    "segmentacion": ("Segmentación", "Segmentacion"),
    "nivel": ("Nivel",),
    "id_sistema": ("ID de Sistema", "Id Sistema"),
    "id_cmdb": ("ID CMDB", "Id CMDB"),
    "notas_contacto": ("Notas de Contacto", "Notas Contacto"),
    "descripcion": ("Descripción", "Descripcion"),
}
USUARIO_ENUMS = {
    "estado": {"ACTIVO", "INACTIVO", "SUSPENDIDO", "RETIRADO"},
    "tipo_identificacion": {"CC", "CE", "PASAPORTE", "NIT", "PEP"},
}
USUARIO_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
USUARIO_TICKET_RE = re.compile(r"^TK-[0-9]{6,}$", re.IGNORECASE)
USUARIO_PHONE_RE = re.compile(r"^\+?[0-9]+$")


def _usuario_columns(df):
    by_name = {_canonical(c): c for c in df.columns}
    found = {}
    for key, alternatives in USUARIO_FIELDS.items():
        for alternative in alternatives:
            if _canonical(alternative) in by_name:
                found[key] = by_name[_canonical(alternative)]
                break
    return found


def _usuario_text_valid(value):
    return _present(value)


def _usuario_optional_value_valid(key, value):
    """Validación básica de campos administrativos solo cuando tienen valor."""
    if not _present(value):
        return True
    text = _text(value)
    if key in {"zip", "id_sistema", "id_cmdb"}:
        return bool(re.fullmatch(r"[A-Za-z0-9._/-]+", text))
    if key == "telefono_alternativo":
        return bool(USUARIO_PHONE_RE.fullmatch(text))
    return isinstance(value, (str, int, float, bool))


def validate_usuario(df, db=None):
    """Valida el esquema Usuario en tres niveles de criticidad."""
    errors, warnings = [], []
    columns = _usuario_columns(df)
    critical = ["nombre", "estado", "email", "identificacion", "tipo_identificacion", "empresa"]
    missing_columns = [key for key in critical if key not in columns]
    for key in missing_columns:
        errors.append(f"Columna obligatoria ausente para Usuario: {USUARIO_FIELDS[key][0]}")
    if missing_columns:
        return errors, warnings

    for idx, row in df.iterrows():
        values = {key: row[columns[key]] for key in columns}
        state = _text(values["estado"]).upper() if _present(values["estado"]) else ""

        # Nivel alto: cualquier nulo o formato inválido invalida la fila.
        for key in critical:
            if not _present(values[key]):
                errors.append(f"Fila {idx}: {USUARIO_FIELDS[key][0]} es obligatorio (Nivel Alto)")
        if _present(values["estado"]) and state not in USUARIO_ENUMS["estado"]:
            errors.append(f"Fila {idx}: Estado '{values['estado']}' no permitido")
        if _present(values["email"]) and not USUARIO_EMAIL_RE.fullmatch(_text(values["email"])):
            errors.append(f"Fila {idx}: Correo Email '{values['email']}' no tiene un formato válido")
        if _present(values["identificacion"]) and not re.fullmatch(r"[A-Za-z0-9]+", _text(values["identificacion"])):
            errors.append(f"Fila {idx}: Identificación debe ser alfanumérica")
        if _present(values["tipo_identificacion"]):
            tipo = _text(values["tipo_identificacion"]).upper()
            if tipo not in USUARIO_ENUMS["tipo_identificacion"]:
                errors.append(f"Fila {idx}: Tipo de Identificación '{values['tipo_identificacion']}' no permitido")

        # Nivel medio: tickets dependen del estado; el resto es obligatorio para activos.
        if "ticket_ingreso" in columns:
            value = values["ticket_ingreso"]
            required = state in {"ACTIVO", "INACTIVO", "SUSPENDIDO"}
            if required and not _present(value):
                warnings.append(f"Fila {idx}: Ticket de Ingreso es obligatorio para el estado {state}")
            elif _present(value) and not USUARIO_TICKET_RE.fullmatch(_text(value)):
                warnings.append(f"Fila {idx}: Ticket de Ingreso debe cumplir el patrón TK-000000")
        if "ticket_retiro" in columns:
            value = values["ticket_retiro"]
            if state == "RETIRADO" and not _present(value):
                warnings.append(f"Fila {idx}: Ticket de Retiro es obligatorio para usuarios RETIRADOS")
            elif _present(value) and not USUARIO_TICKET_RE.fullmatch(_text(value)):
                warnings.append(f"Fila {idx}: Ticket de Retiro debe cumplir el patrón TK-000000")
        if "telefono" in columns and _present(values["telefono"]) and not USUARIO_PHONE_RE.fullmatch(_text(values["telefono"])):
            warnings.append(f"Fila {idx}: Teléfono Principal solo puede contener números y el signo +")
        active_fields = ["gerencia", "cargo", "tipo_cargo", "lider", "grupo", "grupo_jira", "tipo_usuario", "critico"]
        if state == "ACTIVO":
            for key in active_fields:
                if key in columns and not _present(values[key]):
                    warnings.append(f"Fila {idx}: {USUARIO_FIELDS[key][0]} es obligatorio para usuarios ACTIVO")

    # Umbral global de nulos del nivel medio: máximo 5% sobre todos sus campos.
    medium_fields = ["ticket_ingreso", "ticket_retiro", "telefono", "gerencia", "cargo", "tipo_cargo", "lider", "grupo", "grupo_jira", "tipo_usuario", "critico"]
    available_medium = [columns[key] for key in medium_fields if key in columns]
    if available_medium:
        null_ratio = (~df[available_medium].map(_present)).to_numpy().mean()
        if null_ratio > 0.05:
            warnings.append(f"Nivel Medio: porcentaje global de nulos {null_ratio:.1%} supera el máximo permitido de 5%")

    # Nivel bajo: los nulos no bloquean; solo se reportan errores cuando hay valor.
    low_fields = ["pais", "direccion", "zip", "telefono_alternativo", "nombre_contacto", "notificacion", "segmentacion", "nivel", "id_sistema", "id_cmdb", "notas_contacto", "descripcion"]
    available_low = [columns[key] for key in low_fields if key in columns]
    if available_low:
        null_ratio = (~df[available_low].map(_present)).to_numpy().mean()
        if null_ratio > 0.20:
            warnings.append(f"Nivel Bajo: porcentaje global de nulos {null_ratio:.1%} supera el máximo permitido de 20%")
    for key in low_fields:
        if key in columns:
            invalid = ~df[columns[key]].map(lambda value: _usuario_optional_value_valid(key, value))
            for idx in df.index[invalid.fillna(False)]:
                warnings.append(f"Fila {idx}: {USUARIO_FIELDS[key][0]} tiene un formato no válido")
    return errors, warnings


def usuario_quality_score(df):
    """Calcula la nota de Usuario por lote con pesos 40%, 35% y 25%.

    Cada campo aporta 1 si cumple su regla y 0 si está vacío o es inválido.
    """
    columns = _usuario_columns(df)
    if df.empty:
        return 0.0
    critical = ["nombre", "estado", "email", "identificacion", "tipo_identificacion", "empresa"]
    medium = ["ticket_ingreso", "ticket_retiro", "telefono", "gerencia", "cargo", "tipo_cargo", "lider", "grupo", "grupo_jira", "tipo_usuario", "critico"]
    low = ["pais", "direccion", "zip", "telefono_alternativo", "nombre_contacto", "notificacion", "segmentacion", "nivel", "id_sistema", "id_cmdb", "notas_contacto", "descripcion"]

    def valid_field(key, row):
        if key not in columns:
            return None
        value = row[columns[key]]
        if key in critical:
            if not _present(value):
                return False
            if key == "estado":
                return _text(value).upper() in USUARIO_ENUMS["estado"]
            if key == "email":
                return bool(USUARIO_EMAIL_RE.fullmatch(_text(value)))
            if key == "identificacion":
                return bool(re.fullmatch(r"[A-Za-z0-9]+", _text(value)))
            if key == "tipo_identificacion":
                return _text(value).upper() in USUARIO_ENUMS["tipo_identificacion"]
            return True
        state = _text(row[columns["estado"]]).upper() if "estado" in columns and _present(row[columns["estado"]]) else ""
        if key == "ticket_ingreso":
            return not state in {"ACTIVO", "INACTIVO", "SUSPENDIDO"} if not _present(value) else bool(USUARIO_TICKET_RE.fullmatch(_text(value)))
        if key == "ticket_retiro":
            return not state == "RETIRADO" if not _present(value) else bool(USUARIO_TICKET_RE.fullmatch(_text(value)))
        if key == "telefono":
            return _present(value) and bool(USUARIO_PHONE_RE.fullmatch(_text(value)))
        if key in {"gerencia", "cargo", "tipo_cargo", "lider", "grupo", "grupo_jira", "tipo_usuario", "critico"}:
            return _present(value) if state == "ACTIVO" else True
        return _usuario_optional_value_valid(key, value)

    def group_score(fields):
        available = [key for key in fields if key in columns]
        if not available:
            return 0.0
        values = [[valid_field(key, row) for key in available] for _, row in df.iterrows()]
        return float(pd.DataFrame(values, index=df.index).fillna(False).to_numpy().mean() * 100)

    return round(0.40 * group_score(critical) + 0.35 * group_score(medium) + 0.25 * group_score(low), 2)


INFRA_FIELDS = {
    "hostname": ("Nombre Servidor", "Hostname", "Nombre del Servidor"),
    "marca": ("Marca",),
    "modelo": ("Modelo",),
    "so": ("Sistema Operativo", "Sistema operativo", "SO"),
    "firmware": ("Firmware UEFI", "Firmware"),
    "ip": ("IP Relacionada", "IP", "Dirección IP", "Direccion IP"),
    "serial": ("Serial", "Número de Serie", "Numero de Serie", "UUID"),
    "ambiente": ("Ambiente", "Entorno"),
    "datacenter": ("DataCenter", "Data Center", "Datacenter"),
    "servicios": ("Servicios", "Servicio"),
    "estado": ("Estado",),
    "descripcion": ("Descripción", "Descripcion"),
    "cpu": ("CPU", "Procesadores", "Cantidad CPU"),
    "discos": ("Discos", "Cantidad Discos"),
    "espacio": ("Espacio Discos", "Espacio Disco", "Almacenamiento"),
    "ram": ("Memoria RAM", "RAM", "Memoria"),
    "mac": ("Dirección MAC", "Direccion MAC", "MAC"),
    "antivirus": ("Antivirus",),
    "agentes": ("Agentes Instalados", "Agentes"),
    "soporte": ("Cuenta con Soporte", "Tiene Soporte"),
    "vencimiento_soporte": ("Fecha Vencimiento Soporte", "Vencimiento Soporte"),
    "parchable": ("SO Parchable", "Sistema Operativo Parchable"),
    "ultimo_parchado": ("Fecha Último Parchado", "Fecha Ultimo Parchado", "Último Parchado"),
    "integridad": ("Integridad",),
    "disponibilidad": ("Disponibilidad",),
    "confidencialidad": ("Confidencialidad",),
    "criticidad": ("Criticidad SI", "Criticidad"),
    "obsolescencia": ("Obsolescencia",),
    "proveedor": ("Proveedor",),
    "area": ("Área Responsable", "Area Responsable"),
    "custodio": ("Custodio",),
    "empresa": ("Empresa Propietaria", "Empresa propietaria", "Empresa"),
    "tipo_servidor": ("Tipo Servidor", "Tipo de Servidor"),
    "segmento": ("Segmento Red", "Segmento de Red"),
    "aplicacion": ("Aplicación", "Aplicacion"),
    "lider": ("Líder Responsable", "Lider Responsable"),
    "novedad": ("Novedad",),
    "os_build": ("OS Build", "Build SO"),
    "tickets": ("Tickets", "Ticket"),
    "nombre_cmdb": ("Nombre CMDB",),
    "rack": ("Rack",),
    "ubicacion": ("Ubicación Física", "Ubicacion Fisica", "Ubicación"),
    "dns": ("Nombre DNS", "DNS"),
    "rol": ("Rol del Servidor", "Rol Servidor"),
    "servicios_negocio": ("Servicios de Negocio",),
    "cluster": ("Cluster", "Clúster"),
    "virtualizador": ("Virtualizador",),
    "cambio": ("Control de Cambios", "Control Cambios"),
    "servidor_fisico": ("Servidor Físico Relacionado", "Servidor Fisico Relacionado"),
    "licencia": ("Licencia",),
    "certificados": ("Certificados",),
}
INFRA_ENUMS = {
    "ambiente": {"PRODUCCION", "DESARROLLO", "PRUEBAS", "STAGING"},
    "estado": {"ACTIVO", "INACTIVO", "MANTENIMIENTO", "RETIRADO"},
    "cia": {"ALTA", "MEDIA", "BAJA", "CRITICA", "SI", "NO"},
}
INFRA_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")
INFRA_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _infra_columns(df):
    by_name = {_canonical(c): c for c in df.columns}
    found = {}
    for key, alternatives in INFRA_FIELDS.items():
        for alternative in alternatives:
            if _canonical(alternative) in by_name:
                found[key] = by_name[_canonical(alternative)]
                break
    return found


def _infra_number(value):
    if not _present(value):
        return None
    number = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(number) else float(number)


def _infra_date(value):
    if not _present(value) or not INFRA_DATE_RE.fullmatch(_text(value)):
        return False
    try:
        datetime.strptime(_text(value), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_infraestructura(df, db=None):
    """Valida servidores de infraestructura por criticidad."""
    errors, warnings = [], []
    columns = _infra_columns(df)
    critical = ["hostname", "marca", "modelo", "so", "firmware", "ip", "serial", "ambiente", "datacenter", "servicios", "estado", "descripcion"]
    missing_columns = [key for key in critical if key not in columns]
    for key in missing_columns:
        errors.append(f"Columna obligatoria ausente para Infraestructura: {INFRA_FIELDS[key][0]}")
    if missing_columns:
        return errors, warnings

    for idx, row in df.iterrows():
        values = {key: row[columns[key]] for key in columns}
        hostname = _text(values["hostname"]) if _present(values["hostname"]) else ""
        state = _text(values["estado"]).upper() if _present(values["estado"]) else ""
        environment = _text(values["ambiente"]).upper() if _present(values["ambiente"]) else ""

        # Nivel alto: cualquier nulo o formato inválido invalida el servidor.
        for key in critical:
            if not _present(values[key]):
                errors.append(f"Fila {idx}: {INFRA_FIELDS[key][0]} es obligatorio (Nivel Alto)")
        if hostname and (re.search(r"\s", hostname) or not re.fullmatch(r"[A-Za-z0-9._-]+", hostname)):
            errors.append(f"Fila {idx}: Nombre Servidor debe ser alfanumérico y no contener espacios")
        if environment and environment not in INFRA_ENUMS["ambiente"]:
            errors.append(f"Fila {idx}: Ambiente '{values['ambiente']}' no permitido")
        if state and state not in INFRA_ENUMS["estado"]:
            errors.append(f"Fila {idx}: Estado '{values['estado']}' no permitido")
        if _present(values["ip"]):
            try:
                ipaddress.ip_address(_text(values["ip"]))
            except ValueError:
                errors.append(f"Fila {idx}: IP Relacionada no tiene un formato IPv4 o IPv6 válido")

        # Nivel medio: datos técnicos y condiciones operativas.
        for key in ("cpu", "discos", "espacio", "ram"):
            if key in columns and (_infra_number(values[key]) is None or _infra_number(values[key]) <= 0):
                warnings.append(f"Fila {idx}: {INFRA_FIELDS[key][0]} debe ser numérico y mayor que cero")
        if "mac" in columns and _present(values["mac"]) and not INFRA_MAC_RE.fullmatch(_text(values["mac"])):
            warnings.append(f"Fila {idx}: Dirección MAC no tiene formato válido")
        for key in ("antivirus", "agentes"):
            if key in columns and not _present(values[key]):
                warnings.append(f"Fila {idx}: {INFRA_FIELDS[key][0]} no puede estar vacío")
        if "soporte" in columns and _text(values["soporte"]).upper() in {"SI", "SÍ"}:
            if "vencimiento_soporte" not in columns or not _infra_date(values.get("vencimiento_soporte")):
                warnings.append(f"Fila {idx}: Fecha Vencimiento Soporte es obligatoria y debe usar YYYY-MM-DD")
        if "parchable" in columns and _text(values["parchable"]).upper() in {"SI", "SÍ"}:
            if "ultimo_parchado" not in columns or not _infra_date(values.get("ultimo_parchado")):
                warnings.append(f"Fila {idx}: Fecha Último Parchado debe usar YYYY-MM-DD cuando SO Parchable es SÍ")
        for key in ("integridad", "disponibilidad", "confidencialidad", "criticidad", "obsolescencia"):
            if key in columns and _present(values[key]) and _text(values[key]).upper() not in INFRA_ENUMS["cia"]:
                warnings.append(f"Fila {idx}: {INFRA_FIELDS[key][0]} tiene un valor no permitido")
        medium_text = ("proveedor", "area", "custodio", "empresa", "tipo_servidor", "segmento", "aplicacion", "lider", "novedad", "os_build", "tickets")
        for key in medium_text:
            if key in columns and not _present(values[key]):
                warnings.append(f"Fila {idx}: {INFRA_FIELDS[key][0]} no puede estar vacío")

        # Nivel bajo: nomenclatura y relaciones solo cuando tienen valor.
        if "nombre_cmdb" in columns and _present(values["nombre_cmdb"]):
            server_type = _text(values.get("tipo_servidor", "")).upper()
            prefix = "SF_" if "FIS" in server_type else "SV_" if "VIR" in server_type else None
            if prefix and not _text(values["nombre_cmdb"]).upper().startswith(prefix):
                warnings.append(f"Fila {idx}: Nombre CMDB debe iniciar con {prefix} para el tipo de servidor indicado")
            elif not re.fullmatch(r"(?:SV|SF)_[A-Za-z0-9._-]+", _text(values["nombre_cmdb"]), re.IGNORECASE):
                warnings.append(f"Fila {idx}: Nombre CMDB debe iniciar con SV_ o SF_")
        low_fields = ("rack", "ubicacion", "dns", "rol", "servicios_negocio", "cluster", "virtualizador", "cambio", "servidor_fisico", "licencia", "certificados")
        for key in low_fields:
            if key in columns and _present(values[key]) and not re.fullmatch(r"[A-Za-z0-9ÁÉÍÓÚáéíóúÑñ ._:/-]+", _text(values[key])):
                warnings.append(f"Fila {idx}: {INFRA_FIELDS[key][0]} tiene un formato de texto no válido")

    medium_fields = [key for key in ("cpu", "discos", "espacio", "ram", "mac", "antivirus", "agentes", "vencimiento_soporte", "ultimo_parchado", "integridad", "disponibilidad", "confidencialidad", "criticidad", "obsolescencia", "proveedor", "area", "custodio", "empresa", "tipo_servidor", "segmento", "aplicacion", "lider", "novedad", "os_build", "tickets") if key in columns]
    low_fields = [key for key in ("nombre_cmdb", "rack", "ubicacion", "dns", "rol", "servicios_negocio", "cluster", "virtualizador", "cambio", "servidor_fisico", "licencia", "certificados") if key in columns]
    if medium_fields:
        null_ratio = (~df[[columns[key] for key in medium_fields]].map(_present)).to_numpy().mean()
        if null_ratio > 0.05:
            warnings.append(f"Nivel Medio: porcentaje global de nulos {null_ratio:.1%} supera el máximo permitido de 5%")
    if low_fields:
        null_ratio = (~df[[columns[key] for key in low_fields]].map(_present)).to_numpy().mean()
        if null_ratio > 0.20:
            warnings.append(f"Nivel Bajo: porcentaje de nulos {null_ratio:.1%} supera el máximo permitido de 20%")
    return errors, warnings


def infraestructura_quality_score(df):
    """Calcula la nota de Infraestructura con pesos 50%, 35% y 15%."""
    columns = _infra_columns(df)
    if df.empty:
        return 0.0
    critical = ["hostname", "marca", "modelo", "so", "firmware", "ip", "serial", "ambiente", "datacenter", "servicios", "estado", "descripcion"]
    medium = ["cpu", "discos", "espacio", "ram", "mac", "antivirus", "agentes", "vencimiento_soporte", "ultimo_parchado", "integridad", "disponibilidad", "confidencialidad", "criticidad", "obsolescencia", "proveedor", "area", "custodio", "empresa", "tipo_servidor", "segmento", "aplicacion", "lider", "novedad", "os_build", "tickets"]
    low = ["nombre_cmdb", "rack", "ubicacion", "dns", "rol", "servicios_negocio", "cluster", "virtualizador", "cambio", "servidor_fisico", "licencia", "certificados"]

    def completeness(fields):
        available = [columns[key] for key in fields if key in columns]
        if not available:
            return 0.0
        present = df[available].apply(lambda column: column.map(_present))
        return float(present.to_numpy().mean() * 100)

    return round(0.50 * completeness(critical) + 0.35 * completeness(medium) + 0.15 * completeness(low), 2)


VALIDADORES = {
    "Licencias TI": validate_licencias,
    "Dominios": validate_dominios,
    "Certificados": validate_certificados,
    "Cuentas": validate_cuentas,
    "Usuario": validate_usuario,
    "Infraestructura": validate_infraestructura,
}


def run_validation(esquema, df, db):
    validator = VALIDADORES.get(esquema)
    return validator(df, db) if validator else ([], [])


def validation_quality_score(esquema, df):
    if esquema == "Cuentas":
        return cuentas_quality_score(df)
    if esquema == "Usuario":
        return usuario_quality_score(df)
    if esquema == "Infraestructura":
        return infraestructura_quality_score(df)
    return None
