# app-cmdb

App en **Streamlit** para revisar y comparar archivos de Excel/CSV sin depender de campos fijos.

## Qué hace
- Detecta automáticamente columnas comunes entre dos archivos.
- Permite elegir dinámicamente la(s) columna(s) clave por carga.
- Compara columnas seleccionadas y separa resultados en:
  - Altas
  - Bajas
  - Modificados
  - Sin cambios
- Descarga un reporte consolidado en Excel.

## Requisitos
```bash
pip install -r requirements.txt
```

## Ejecutar
```bash
streamlit run app.py
```

## Uso rápido (asistente paso a paso)
1. **Configuración**: elija el modo (comparar, validar o limpiar) y el esquema de reglas.
2. **Carga de archivos**: suba Excel (.xlsx, .xlsm, .xls) o CSV (coma o punto y coma).
   - Si el libro tiene varias hojas, seleccione la que contiene los datos.
   - Revise los avisos preventivos: celdas combinadas, filas/columnas ocultas o agrupadas,
     encabezados vacíos o repetidos. Puede rellenar celdas combinadas, excluir filas/columnas
     ocultas o indicar en qué fila está el encabezado.
3. **Esquema de datos**: confirme el tipo de cada columna (Texto, Identificador, Email, Entero,
   Decimal, Fecha, Booleano). Los valores incompatibles se marcan en rojo antes de procesar.
4. **Resultados**: validación con filas/celdas incoherentes resaltadas en rojo; en comparación,
   la vista se actualiza al instante al cambiar la columna clave y las celdas modificadas se
   resaltan en rojo. Descargue el reporte en Excel o CSV.

## Comparación de archivos
- **Navegación por modos** en el menú lateral (comparar, validar, limpiar).
- **Duplicados sin pérdida**: si una clave se repite, los registros se emparejan 1 a 1 por orden
  de aparición (1ª con 1ª, 2ª con 2ª...). Ninguna fila se descarta; las claves con distinta
  cantidad de repeticiones se reportan en «Repetidos» con los registros que quedan sin pareja.
- **Glosario de estados**: 🟢 Altas, 🔴 Bajas, 🟡 Modificaciones, ⚪ Sin cambios, con tooltips.
- **Inclusión del Archivo 1 en el Archivo 2**: indicador SÍ / PARCIAL / NO con el porcentaje de
  cobertura exacta (registros idénticos) y por clave.
- **Doble cruce**: por clave (sin importar el orden) y posicional (fila N contra fila N), que
  detecta filas desplazadas, insertadas o eliminadas en la secuencia.
- **Detalle carácter a carácter** con el tipo de cada diferencia: mayúsculas/minúsculas,
  tildes/acentos, espacios, formato de fecha, numérica o texto distinto.
- **Tolerancias configurables** antes de comparar: margen numérico (±), formato de fecha/hora,
  mayúsculas, tildes, espacios, columnas volátiles a excluir y coincidencia difusa
  (Jaro-Winkler o Levenshtein) para sugerir equivalencias entre altas y bajas.

## Estructura del proyecto
```
app.py                  Orquestación del asistente (pasos, estado y pantallas)
ui/styles.py            Paleta de colores y hoja de estilos CSS
ui/components.py        Componentes visuales reutilizables (tarjetas, tablas con color, gráficos)
data_loader.py          Lectura de archivos, selección de hoja, revisión preventiva y errores claros
data_cleaning.py        Limpieza estructural y normalización de texto
schema_mapper.py        Detección y aplicación de tipos de datos sin pérdida de formato
comparator.py           Motor de comparación (duplicados 1:1, tolerancias, inclusión, cruce posicional)
diffing.py              Similitud de texto, tipo de diferencia y resaltado por carácter
validators.py           Reglas de negocio por esquema
validation_engine.py    Métricas genéricas de calidad (nulos, score)
reporting.py            Perfil de columnas y exportación a Excel
database.py             Acceso a SQLite (maestros y histórico)
tests/                  Pruebas del núcleo y de la interfaz
```
Los módulos de lógica no importan Streamlit, así que pueden probarse y reutilizarse fuera de la app.

## Pruebas
```bash
python -m tests.run_all
```
Cubren la carga de archivos (CSV con codificación ANSI, Excel multihoja con celdas combinadas y
filas ocultas), la detección de tipos y del separador decimal, el motor de comparación
(duplicados, tolerancias, inclusión, orden) y el recorrido completo del asistente en los tres modos.

Revisión rápida de estilo (imports sin usar, funciones largas, `except:` desnudos):
```bash
python tests/revisar_estilo.py
```

## Módulos
- `data_loader.py`: lectura de archivos, selección de hoja, revisión preventiva y mensajes de error en lenguaje natural.
- `schema_mapper.py`: detección y aplicación de tipos de datos sin pérdida de formato.
- `comparator.py`: motor de comparación (duplicados 1:1, tolerancias, inclusión, cruce posicional).
- `diffing.py`: similitud de texto, clasificación del tipo de diferencia y resaltado por carácter.
- `validators.py`: reglas de negocio por esquema (Licencias TI, Dominios, Certificados).
