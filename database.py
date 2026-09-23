import sqlite3
from pathlib import Path

import pandas as pd

import streamlit as st
 
class DatabaseManager:

    def __init__(self, db_path="cmdb_quality.db"):

        # Use one stable database location regardless of the terminal working directory.
        self.db_path = str(Path(db_path) if Path(db_path).is_absolute()
                           else Path(__file__).resolve().parent / db_path)

        self.init_database()

    def init_database(self):

        """Inicializa las tablas necesarias"""

        conn = sqlite3.connect(self.db_path)

        cursor = conn.cursor()

        # Tabla de históricos de validación

        cursor.execute('''

            CREATE TABLE IF NOT EXISTS historico_validaciones (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                esquema TEXT NOT NULL,

                archivo_anterior TEXT,

                archivo_nuevo TEXT,

                fecha_validacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                score_calidad REAL,

                total_registros INTEGER,

                errores_encontrados INTEGER,

                advertencias INTEGER,

                detalles TEXT

            )

        ''')

        # Tabla para almacenar resultados de validación

        cursor.execute('''

            CREATE TABLE IF NOT EXISTS resultados_validacion (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                historico_id INTEGER,

                tipo_validacion TEXT,

                registro_id TEXT,

                campo TEXT,

                error TEXT,

                FOREIGN KEY (historico_id) REFERENCES historico_validaciones(id)

            )

        ''')

        # Tablas maestras usadas por las validaciones de integridad referencial
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS proveedores (
                razon_social TEXT PRIMARY KEY,
                nit TEXT,
                contacto TEXT,
                email TEXT,
                telefono TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aplicaciones (
                nombre TEXT PRIMARY KEY,
                version TEXT,
                entorno TEXT,
                responsable TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                nombre TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                area TEXT,
                cargo TEXT
            )
        ''')

        conn.commit()

        conn.close()

    def insertar_proveedor(self, razon_social, nit=None, contacto=None, email=None, telefono=None):

        """Inserta o actualiza un proveedor"""

        conn = sqlite3.connect(self.db_path)

        cursor = conn.cursor()

        cursor.execute('''

            INSERT OR REPLACE INTO proveedores (razon_social, nit, contacto, email, telefono)

            VALUES (?, ?, ?, ?, ?)

        ''', (razon_social, nit, contacto, email, telefono))

        conn.commit()

        conn.close()

    def obtener_proveedores(self):

        """Obtiene lista de proveedores"""

        conn = sqlite3.connect(self.db_path)

        df = pd.read_sql_query("SELECT razon_social FROM proveedores ORDER BY razon_social", conn)

        conn.close()

        return df['razon_social'].tolist() if not df.empty else []

    def insertar_aplicacion(self, nombre, version=None, entorno=None, responsable=None):

        """Inserta o actualiza una aplicación"""

        conn = sqlite3.connect(self.db_path)

        cursor = conn.cursor()

        cursor.execute('''

            INSERT OR REPLACE INTO aplicaciones (nombre, version, entorno, responsable)

            VALUES (?, ?, ?, ?)

        ''', (nombre, version, entorno, responsable))

        conn.commit()

        conn.close()

    def obtener_aplicaciones(self):

        """Obtiene lista de aplicaciones"""

        conn = sqlite3.connect(self.db_path)

        df = pd.read_sql_query("SELECT nombre FROM aplicaciones ORDER BY nombre", conn)

        conn.close()

        return df['nombre'].tolist() if not df.empty else []

    def insertar_usuario(self, nombre, email, area=None, cargo=None):

        """Inserta o actualiza un usuario"""

        conn = sqlite3.connect(self.db_path)

        cursor = conn.cursor()

        cursor.execute('''

            INSERT OR REPLACE INTO usuarios (nombre, email, area, cargo)

            VALUES (?, ?, ?, ?)

        ''', (nombre, email, area, cargo))

        conn.commit()

        conn.close()

    def obtener_usuarios(self):

        """Obtiene lista de usuarios"""

        conn = sqlite3.connect(self.db_path)

        df = pd.read_sql_query("SELECT nombre, email FROM usuarios ORDER BY nombre", conn)

        conn.close()

        return df.to_dict('records') if not df.empty else []

    def guardar_historico(self, esquema, archivo_anterior, archivo_nuevo, score_calidad, 

                          total_registros, errores_encontrados, advertencias, detalles):

        """Guarda un histórico de validación"""

        conn = sqlite3.connect(self.db_path)

        cursor = conn.cursor()

        cursor.execute('''

            INSERT INTO historico_validaciones 

            (esquema, archivo_anterior, archivo_nuevo, score_calidad, total_registros, 

             errores_encontrados, advertencias, detalles)

            VALUES (?, ?, ?, ?, ?, ?, ?, ?)

        ''', (esquema, archivo_anterior, archivo_nuevo, score_calidad, 

              total_registros, errores_encontrados, advertencias, detalles))

        historico_id = cursor.lastrowid

        conn.commit()

        conn.close()

        return historico_id

    def obtener_historicos(self, limit=10):

        """Obtiene el histórico de validaciones"""

        conn = sqlite3.connect(self.db_path)

        df = pd.read_sql_query(f'''

            SELECT id, esquema, fecha_validacion, score_calidad, total_registros, 

                   errores_encontrados, advertencias

            FROM historico_validaciones 

            ORDER BY fecha_validacion DESC 

            LIMIT {limit}

        ''', conn)

        conn.close()

        return df

    def cargar_datos_referencia(self):

        """Carga datos de ejemplo para pruebas"""

        # Proveedores de ejemplo

        proveedores_ejemplo = [

            ("Microsoft", "123456789", "Juan Perez", "juan@microsoft.com", "555-0101"),

            ("Google", "987654321", "Maria Gomez", "maria@google.com", "555-0102"),

            ("AWS", "456789123", "Carlos Lopez", "carlos@aws.com", "555-0103"),

            ("DigiCert", "789123456", "Ana Martinez", "ana@digicert.com", "555-0104")

        ]

        for prov in proveedores_ejemplo:

            self.insertar_proveedor(*prov)

        # Aplicaciones de ejemplo

        aplicaciones_ejemplo = [

            ("SAP ERP", "2023.1", "Producción", "Juan Perez"),

            ("Salesforce", "Winter 24", "Producción", "Maria Gomez"),

            ("Active Directory", "2022", "Producción", "Carlos Lopez")

        ]

        for app in aplicaciones_ejemplo:

            self.insertar_aplicacion(*app)

        # Usuarios de ejemplo

        usuarios_ejemplo = [

            ("Juan Perez", "juan.perez@empresa.com", "TI", "Admin"),

            ("Maria Gomez", "maria.gomez@empresa.com", "Infraestructura", "Senior"),

            ("Carlos Lopez", "carlos.lopez@empresa.com", "Seguridad", "Lead")

        ]

        for user in usuarios_ejemplo:

            self.insertar_usuario(*user)

    def limpiar_proveedores_aplicaciones(self):
        """Elimina todos los registros de proveedores y aplicaciones sin afectar otras tablas."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Borrar contenidos, conservar las tablas
        try:
            cursor.execute('DELETE FROM proveedores')
        except Exception:
            pass
        try:
            cursor.execute('DELETE FROM aplicaciones')
        except Exception:
            pass
        conn.commit()
        conn.close()
 
# Inicializar base de datos

@st.cache_resource

def init_db():

    db = DatabaseManager()

    # Re-run the idempotent schema creation for cached Streamlit resources.
    db.init_database()

    return db
 