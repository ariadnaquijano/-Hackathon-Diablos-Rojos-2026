# Stuff+ ajustado por altitud — ISAC Hackathon 2026 · Diablos Rojos

Construimos un modelo Stuff+ calibrado para la Liga Mexicana de Béisbol que explica
**qué tan bueno es cada pitch en el Harp Helú (2,240 m)** y **qué debe hacer el club con esa
información**: a quién fichar, cómo planear el juego en casa y cómo ajustar a cada pitcher.

## Dónde estamos

El modelo oficial es la **versión 3** (`docs/decisiones.md`, D-040): Stuff+ por componentes con la
forma llevada a nivel del mar, el Location+ del equipo predicho a nivel del mar y Pitching+ como suma
pesada de los dos. Los entregables 1 a 4 están hechos; el 5 (documento técnico) lo escribe el equipo
con la guía `docs/07_guia_documento_tecnico.md`.

| # | Entregable de la convocatoria | Dónde está |
|---|---|---|
| 1 | Scores por pitch, pitcher y arsenal | `docs/08_entregable_1_scores.md`; archivos en `data/entregables/` (no se suben) |
| 2 | Perfil físico ideal | `docs/09_entregable_2_perfil_ideal.md` |
| 3 | Recomendaciones operativas | `docs/10_entregable_3_recomendaciones.md` |
| 1–3 | Reporte visual de los tres | `reportes/entregables_1_a_3.html` |
| 4 | Dashboard simulador y fichas de pitchers | `python src/simulador.py` → http://127.0.0.1:8050 |
| 5 | Documento técnico (6–10 páginas) | Guía: `docs/07_guia_documento_tecnico.md` |

## Demo en 3 comandos

Requisitos: Python 3.12+, los datos en `data/raw/` (ver "Datos") y, en Mac, `brew install libomp`
(lo necesita XGBoost).

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
bash -c 'cd src && for s in limpieza features target modelos_base modelo modelo_v2 arsenal pasaporte_altitud location_ben modelo_v3 ficha entregable_scores; do python $s.py || exit 1; done'
python src/simulador.py   # la primera vez entrena sus modelos (unos 10 minutos) y abre el servidor
```

Luego abre http://127.0.0.1:8050 (simulador) y http://127.0.0.1:8050/fichas (fichas de pitchers).
La cadena tarda entre 1 y 2 horas en una laptop, sobre todo por los modelos de la etapa 4 y el
Location+. Solo arma lo que necesitan el simulador y las fichas: los resúmenes de los entregables 2 y
3, las validaciones y los reportes ya vienen en `reportes/`. Para regenerarlos, corre la sección
completa de "Cómo correr el código".

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
6. [`docs/02_features.md`](docs/02_features.md) — variables del modelo (etapa 2).
7. [`docs/retroalimentacion_experto.md`](docs/retroalimentacion_experto.md) — lo que nos dijo un lanzador y qué cambió.
8. [`docs/hipotesis_h4.md`](docs/hipotesis_h4.md) — H4: ¿el spin rate basta para predecir un buen pitch? (reporte: `reportes/h4_spin_rate.html`).
9. [`docs/03_target.md`](docs/03_target.md) — target de carreras esperadas y modelos base (etapa 3; plan en `docs/03_plan_target.md`).
10. [`docs/04_modelo.md`](docs/04_modelo.md) — el modelo y su evaluación en 2026 (etapa 4; afinado en `docs/04_afinado.md`).
11. [`docs/05_arsenal.md`](docs/05_arsenal.md) y [`docs/05_pasaporte_altitud.md`](docs/05_pasaporte_altitud.md) — arsenal y altitud (etapa 5).
12. [`docs/06_location_ben.md`](docs/06_location_ben.md) — el Location+ del equipo en el modelo oficial (v3).
    También [`docs/06_fisica_densidad.md`](docs/06_fisica_densidad.md): la física del aire, con k en densidad.
13. [`docs/07_guia_documento_tecnico.md`](docs/07_guia_documento_tecnico.md) — guía técnica para el documento final.
14. [`docs/08_entregable_1_scores.md`](docs/08_entregable_1_scores.md), [`docs/09`](docs/09_entregable_2_perfil_ideal.md) y [`docs/10`](docs/10_entregable_3_recomendaciones.md) — entregables 1 a 3.

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

| # | Etapa | Documento | Reporte |
|---|---|---|---|
| 0 | Exploración y validación del enfoque | `docs/00_contexto_y_approach.md` | — |
| 1 | Limpieza de datos | `docs/01_limpieza.md` | `reportes/etapa_01_limpieza.html` |
| 2 | Features (física, arsenal, aire, secuencia) | `docs/02_features.md` | `reportes/etapa_02_features.html` |
| 3 | Target xRunValue y modelos base | `docs/03_target.md` | `reportes/etapa_03_target.html` |
| 4 | Modelo: Stuff+ por componentes, Location+, Pitching+, proyección y afinado | `docs/04_*.md` | `reportes/etapa_04_modelo.html` |
| 5 | Arsenal y pasaporte de altitud | `docs/05_arsenal.md`, `docs/05_pasaporte_altitud.md` | `reportes/etapa_05_arsenal_altitud.html` |
| 6 | Location+ del equipo (v3), validación por estadio, ficha y entregables | `docs/06_*.md`, `docs/08` a `docs/10` | `reportes/entregables_1_a_3.html` |

## Cómo correr el código

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # en Mac, antes: brew install libomp

# Coloca los archivos del hackathon en data/raw/ (no vienen en el repo)
cd src

# Etapas 1 a 3: datos, features y target
python limpieza.py && python reporte_limpieza.py
python features.py && python reporte_features.py
python target.py && python modelos_base.py && python reporte_target.py

# Etapa 4: modelo (v1, afinado v2 y proyección)
python stuff_componentes.py            # Stuff+ por componentes contra las bases (2024 → 2025)
python modelo.py && python reporte_modelo.py
python afinado.py && python modelo_v2.py
python proyeccion.py

# Etapa 5: arsenal y altitud
python arsenal.py && python pasaporte_altitud.py && python riesgo_altitud.py
python reporte_arsenal_altitud.py

# Etapa 6: Location+ del equipo (modelo oficial v3) y validaciones
python location_ben.py && python location_ben.py --estadio
python modelo_v3.py
python validacion_estadio.py && python metricas_documento.py
python riesgo_contacto.py && python perfil_ideal.py
python fisica_densidad.py               # el exponente k en densidad del aire (D-041)
python diferencias_tipo.py              # diferencias de pérdida entre tipos de pitch (D-042)

# Entregables y herramientas
python entregable_scores.py && python reporte_entregables.py
python ficha.py
python simulador.py                    # http://127.0.0.1:8050 y /fichas
```

Los análisis de apoyo (`exploracion_*.py`, `hipotesis_h4.py`, `evidencia_acarreo.py`,
`relacion_componentes.py`, `location_sin_conteo.py`) generan las cifras de sus documentos y no son
necesarios para la demo. `location_plus.py`, `location_plus_xgb.py` y `run_value.py` en la raíz son los
originales del Location+ de Ben (PR #2); el modelo oficial los usa a través de `src/location_ben.py`.

## Datos

Los datos son propiedad de ISAC y Diablos Rojos. Solo se usan para la competencia, **no se suben
al repositorio ni se comparten**; podemos presentar resultados, no los datos.
Cada integrante debe tener su propia copia en `data/raw/`.

Las bases originales están en la carpeta compartida del equipo:
https://drive.google.com/drive/folders/1C_YUOpZP76lR73yBdwp5ikA3oo4Z2YfC?usp=sharing
Descarga `stuff_model_df.parquet` y `stuff_plus_data_dictionary.csv` a `data/raw/`.
