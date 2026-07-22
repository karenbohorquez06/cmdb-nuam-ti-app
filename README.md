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

## Uso rápido
1. Carga archivo base (anterior) y archivo nuevo (actual).
2. Selecciona las columnas clave según los archivos del momento.
3. Selecciona columnas a comparar.
4. Revisa métricas y tablas.
5. Descarga el reporte de comparación.
