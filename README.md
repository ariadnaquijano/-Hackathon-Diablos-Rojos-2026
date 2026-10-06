# Stuff+ ajustado por altitud — ISAC Hackathon 2026 · Diablos Rojos

Construimos un modelo Stuff+ calibrado para la Liga Mexicana de Béisbol que explica
**qué tan bueno es cada pitch en el Harp Helú (2,240 m)** y **qué debe hacer el club con esa
información**: a quién fichar, cómo planear el juego en casa y cómo ajustar a cada pitcher.

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

## Fechas que mandan

| Fecha | Hito |
|---|---|
| 2026-10-12 | Cierre de registro |
| **2026-10-22** | **Entrega del proyecto** |
| 2026-11-02 | Anuncio de finalistas |
| 2026-11-11 | Final (entrevista de 10 min con el jurado) |

## Cómo leer este repositorio

Lee los documentos en este orden; cada uno se apoya en el anterior.

1. [`docs/00_contexto_y_approach.md`](docs/00_contexto_y_approach.md) — el reto, qué nos piden y por qué elegimos este enfoque.
2. [`docs/glosario.md`](docs/glosario.md) — todos los términos de béisbol, física y modelado en lenguaje simple.
3. [`docs/convenciones.md`](docs/convenciones.md) — cómo escribimos código, documentos y commits.
4. [`docs/decisiones.md`](docs/decisiones.md) — bitácora de cada decisión, con alternativas descartadas.
5. [`docs/01_limpieza.md`](docs/01_limpieza.md) — limpieza de datos (etapa 1).

## Estructura

```
├── README.md                ← estás aquí
├── docs/                    ← fuente de verdad: una guía .md por etapa
├── reportes/                ← un HTML visual por etapa (se genera al cerrarla)
├── src/                     ← código reproducible; todo número de los docs sale de aquí
├── referencias/             ← convocatoria oficial y literatura
└── data/                    ← NUNCA se sube a git (el reglamento prohíbe compartir los datos)
    ├── raw/                 ← archivos originales, no se modifican jamás
    ├── interim/             ← resultados intermedios
    └── processed/           ← dataset limpio listo para modelar
```

## Etapas

| # | Etapa | Estado | Documento | Reporte |
|---|---|---|---|---|
| 0 | Exploración y validación del enfoque | ✅ Hecha | `docs/00_contexto_y_approach.md` | — |
| 1 | Limpieza de datos | ✅ Hecha | `docs/01_limpieza.md` | `reportes/etapa_01_limpieza.html` |
| 2 | Features (física, arsenal, densidad del aire) | 📝 Plan aprobado | `docs/02_plan_features.md` | `reportes/etapa_02_decisiones.html` |
| 3 | Target xRunValue y baseline | ⏳ | — | — |
| 4 | Modelo de dos etapas (forma → resultado) | ⏳ | — | — |
| 5 | Validación (pitcher, temporada, altitud) | ⏳ | — | — |
| 6 | Herramientas: pasaporte, índice Magnus, punto de mira | ⏳ | — | — |
| 7 | Dashboard | ⏳ | — | — |
| 8 | Documento técnico y entrevista | ⏳ | — | — |

## Cómo correr el código

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Coloca los archivos del hackathon en data/raw/ (no vienen en el repo)
python src/exploracion_preliminar.py   # cifras de docs/00
python src/perfil_calidad_datos.py     # mediciones que justifican las reglas de limpieza
python src/limpieza.py                 # etapa 1: genera data/processed/ y el resumen
python src/reporte_limpieza.py         # etapa 1: genera reportes/etapa_01_limpieza.html
python src/exploracion_etapa_02.py     # evidencia del plan de features
```

## Datos

Los datos son propiedad de ISAC y Diablos Rojos. Solo se usan para la competencia, **no se suben
al repositorio ni se comparten**; podemos presentar resultados, no los datos.
Cada integrante debe tener su propia copia en `data/raw/`.

Las bases originales están en la carpeta compartida del equipo:
https://drive.google.com/drive/folders/1C_YUOpZP76lR73yBdwp5ikA3oo4Z2YfC?usp=sharing
Descarga `stuff_model_df.parquet` y `stuff_plus_data_dictionary.csv` a `data/raw/`.
