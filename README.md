# Hackathon-Diablos-Rojos-2026

Las bases originales están en https://drive.google.com/drive/folders/1C_YUOpZP76lR73yBdwp5ikA3oo4Z2YfC?usp=sharing 

## En lo que estamos trabajando ahora...
**Próxima reunión**: Martes 6 de octubre, 3:00 pm

### 1. Revisión inicial de los datos
- Revisar la estructura general del dataset.
- Consultar el diccionario de variables.
- Identificar valores faltantes, variables relevantes y posibles problemas de calidad.
- Definir qué limpieza mínima es necesaria para comenzar los análisis (SIN HACERLLA!!)

### 2. Análisis preliminar de las hipótesis
Trabajaremos en un análisis sencillo, principalmente estadístico, de las hipótesis dadas para el proyecto.
**No vamos a demostrar definitivamente las hipótesis**, solo queremos identificar patrones y relaciones para decidir qué análisis vale la pena desarrollar más adelante. Trabajaremos sobre el dataset original.

* H1: La baja densidad reduce el movimiento inducido por spin - Max
* H2: Los pitcheos basados en diferencial de velocidad ganan valor relativo - Ben
* H3: Los groundball pitchers son más valiosos en altitud - Ari
* H4: El spin rate por sí solo resulta insuficiente como predictor de Stuff+ - Alexis 

## Local Stuff+ implementation

A standalone XGBoost training pipeline is available in `stuffplus/`.
See [setup and commands](README_STUFFPLUS.md) and the
[complete English model and meeting guide](docs/STUFFPLUS_MODEL_GUIDE.md).
It produces pitcher/type summaries and altitude movement scenarios from the cleaned
Parquet file. The first run is experimental: XGBoost did not outperform the linear
physical baseline. The guide includes the measured results and interpretation limits.

