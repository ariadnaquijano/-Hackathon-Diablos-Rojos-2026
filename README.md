# Stuff+ ajustado por altitud — ISAC Hackathon 2026 · Diablos Rojos

Stuff+, Location+ y Pitching+ para la Liga Mexicana de Béisbol, con el movimiento de cada pitch llevado
a nivel del mar, y cuánto pierde cada pitch en el Estadio Alfredo Harp Helú (CDMX, 2,240 m).

**Resultados principales**

- En altitud extrema la recta pierde **13.0 puntos de Stuff+** (IC 95 %: 8.8 a 17.3), el sinker 13.3 y
  el cambio 9.7; la curva, 0.7. Contra la recta, la curva pierde menos con diferencia probada.
- El ajuste sigue la física: pasado a densidad del aire, el exponente de la IVB de la recta es **1.05**
  (1.02 a 1.07), dentro de lo que predice el efecto Magnus (1.00 a 1.11).
- Validado fuera de muestra: con pitchers que el modelo no vio, en la temporada 2026 y en altitud
  extrema sin verla al entrenar, donde Pitching+ baja **4.97 %** el error cuadrático contra el promedio
  por conteo (4.70 a 5.26).

## Por dónde empezar

| Para ver | Dónde |
|---|---|
| Los entregables 1 a 4, sin ejecutar nada | La carpeta de entrega (`index.html`); se genera con `python src/simulador.py --estatico` |
| Scores, perfil ideal y recomendaciones | [`reportes/entregables_1_a_3.html`](reportes/entregables_1_a_3.html) y [`docs/08`](docs/08_entregable_1_scores.md) a [`docs/10`](docs/10_entregable_3_recomendaciones.md) |
| Cada decisión, con sus alternativas descartadas | [`docs/decisiones.md`](docs/decisiones.md) (D-001 a D-044) |
| Las cifras del documento técnico y su origen | [`docs/07_guia_documento_tecnico.md`](docs/07_guia_documento_tecnico.md) |
| Términos de béisbol, física y modelado | [`docs/glosario.md`](docs/glosario.md) |

Los datos de la liga no están en el repositorio: el reglamento no permite compartirlos. Tampoco los
archivos con identificadores de pitchers (scores, fichas), que solo van en la carpeta de entrega.

## Estructura

```
├── src/                     código; todas las cifras de docs/ y reportes/ salen de aquí
│   └── plantillas/          HTML de los reportes, el simulador y las fichas
├── docs/                    un documento por etapa, la bitácora de decisiones y el glosario
├── reportes/                resúmenes en JSON y reportes HTML de cada etapa
├── referencias/             convocatoria oficial
├── location_plus_original/  primera versión del Location+ del equipo (referencia)
└── data/                    no se sube: datos de la liga y resultados con identificadores
```

## Etapas

| # | Etapa | Código (`src/`) | Documento | Reporte |
|---|---|---|---|---|
| 1 | Limpieza de datos | `limpieza.py` | `docs/01_limpieza.md` | `etapa_01_limpieza.html` |
| 2 | Variables: física, aire, arsenal, secuencia | `features.py` | `docs/02_features.md` | `etapa_02_features.html` |
| 3 | Valor de cada pitch (xRV) y modelos base | `target.py`, `modelos_base.py` | `docs/03_target.md` | `etapa_03_target.html` |
| 4 | Stuff+ por componentes, Location+ y Pitching+ | `stuff_componentes.py`, `modelo.py`, `modelo_v2.py` | `docs/04_*.md` | `etapa_04_modelo.html` |
| 5 | Arsenal y pérdida en altura | `arsenal.py`, `pasaporte_altitud.py` | `docs/05_*.md` | `etapa_05_arsenal_altitud.html` |
| 6 | Modelo oficial, validación, física y entregables | `location_ben.py`, `modelo_v3.py`, `validacion_estadio.py`, `fisica_*.py` | `docs/06_*.md`, `docs/08` a `docs/10` | `entregables_1_a_3.html` |

Las etapas 2 a 4 tienen un plan escrito antes de correr los modelos (`docs/0X_plan_*.md`), con reglas de
decisión fijadas de antemano; los resultados que no las pasaron también están documentados.

## Cómo correr el código

Requisitos: Python 3.12+ y, en Mac, `brew install libomp` (lo necesita XGBoost). Los archivos de la
liga van en `data/raw/`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd src

# Etapas 1 a 3: datos, variables y valor de cada pitch
python limpieza.py && python reporte_limpieza.py
python features.py && python reporte_features.py
python target.py && python modelos_base.py && python reporte_target.py

# Etapa 4: Stuff+ por componentes, afinado y proyección
python stuff_componentes.py
python modelo.py && python reporte_modelo.py
python afinado.py && python modelo_v2.py
python proyeccion.py

# Etapa 5: arsenal y altura
python arsenal.py && python pasaporte_altitud.py && python riesgo_altitud.py
python reporte_arsenal_altitud.py

# Etapa 6: modelo oficial (v3), validaciones y física
python location_ben.py && python location_ben.py --estadio
python modelo_v3.py
python validacion_estadio.py && python metricas_documento.py
python riesgo_contacto.py && python perfil_ideal.py
python fisica_densidad.py && python diferencias_tipo.py
python fisica_placebo.py && python altura_por_pitcher.py
python componentes_futuro.py

# Entregables
python entregable_scores.py && python reporte_entregables.py
python ficha.py
python simulador.py --estatico           # carpeta de entrega en data/publicar/
python verificar_simulador.py            # el simulador del navegador contra el de Python
```

La cadena completa tarda entre 1 y 2 horas en una laptop. El simulador calcula el Stuff+ en el
navegador con los árboles del modelo; `verificar_simulador.py` comprueba en 2,000 pitches al azar que
da lo mismo que Python.

Los análisis de apoyo (`exploracion_*.py`, `hipotesis_h4.py`, `evidencia_acarreo.py`,
`relacion_componentes.py`, `location_sin_conteo.py`) generan las cifras de sus documentos y no hacen
falta para los entregables.
