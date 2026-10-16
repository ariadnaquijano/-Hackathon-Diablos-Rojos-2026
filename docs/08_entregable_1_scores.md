# Entregable 1 · Stuff+ por pitch, pitcher y arsenal

> **Evidencia:** `src/entregable_scores.py` → `reportes/etapa_06_scores.json` (sin identificadores).
> **Archivos para el envío** (con identificadores anónimos; no se suben al repo), en
> `data/entregables/`:
> - `scores_por_pitch.csv`: 631,068 pitches de 2024–2026.
> - `scores_por_pitcher.csv`: 818 pitcher-temporada con 300+ pitches.
> - `scores_por_arsenal.csv`: 2,065 pitcher-temporada-tipo con 100+ pitches.
>
> **Modelo:** versión 2 (D-035). 2024–2025 vienen de modelos que no vieron al pitcher; 2026, de
> modelos entrenados con 2024–2025.

## 1. Qué trae cada archivo

| Archivo | Columnas principales |
|---|---|
| Por pitch | `PitchUID`, pitcher, temporada, altitud, tipo; `stuff_plus`, `location_plus`, `pitching_plus`, `stuff_plus_harp`; los valores en carreras (`stuff`, `location`, `pitching`) y el xRV real |
| Por pitcher | Stuff+, Location+, Pitching+, `stuff_plus_harp_estimado`, riesgo en altura y cobertura, % de rolling, arquetipo de arsenal, componentes (swing, whiff, foul, strike cantado) |
| Por arsenal | Cada pitch del pitcher: uso, Stuff+ contra su tipo, `stuff_plus_harp`, pérdida en altura de su tipo, componentes |

**Escalas (detalle en `docs/07_guia_documento_tecnico.md`, sección 5):**

- **Por pitch:** Stuff+ = 100 − 10 × (valor − media) ÷ desviación entre pitches. Stuff+ se compara
  contra su tipo y temporada; Location+ y Pitching+, contra la temporada. Es el z(score) de la
  convocatoria, con el signo invertido porque menos carreras es mejor.
- **Por pitcher y por arsenal:** la escala de la ficha, con la desviación entre pitchers.
- **Harp Helú:** se resta la pérdida real promedio del tipo en altitud extrema (D-034). Para un
  pitcher, la de su mezcla (D-036).

## 2. Comparación de la CDMX contra los estadios a nivel del mar

El mismo pitcher con el mismo pitch en las dos altitudes (2024–2025, 50+ pitches por lado). La
pérdida es de xRV sin contacto, y los puntos están en la escala oficial del arsenal.

| Tipo | Pares | Pérdida en carreras por 100 | Delta de Stuff+ en el Harp Helú |
|---|---|---|---|
| Recta | 210 | 0.40 (0.27 a 0.53) | **−13.0** (−17.3 a −8.8) |
| Sinker | 97 | 0.32 (0.14 a 0.49) | **−13.3** (−20.5 a −6.1) |
| Cambio | 51 | 0.32 (0.09 a 0.58) | **−9.7** (−17.5 a −2.8) |
| Slider | 129 | 0.18 (−0.03 a 0.39) | −6.9 (−14.8 a +1.1) |
| Curva | 35 | 0.02 (−0.24 a 0.28) | −0.7 (−9.5 a +8.1) |

- **Pierden las que viven del efecto Magnus:** recta, sinker y cambio, con intervalo fuera de cero.
- **Slider y curva casi no pierden:** su intervalo toca cero.
- Cutter y splitter no tienen pares suficientes.
- **El modelo no castiga al pitcher por el aire:** el Stuff+ del mismo pitcher cambia 0.05 carreras
  por 100 entre altitudes; su resultado real, 0.57 (`docs/04_modelo.md`, sección 2). Por eso el
  Stuff+ sirve para comparar a un pitcher del Harp Helú con uno de la costa.

## 3. ¿Qué arsenal produce el Stuff+ más alto en el Harp Helú? (D-038)

Arquetipos por uso, fijados antes de correr (pitcher-temporada con 300+ pitches, 2024–2025):

| Arquetipo | Regla | Pitchers | Stuff+ a nivel del mar | **Stuff+ estimado en el Harp Helú** | Pitching+ |
|---|---|---|---|---|---|
| **Rompimiento** | slider + curva ≥ 40 % | 118 | 103.1 | **90.9** | 104.0 |
| Recta y sinker | recta + sinker ≥ 60 % | 203 | 103.7 | 86.8 | 98.2 |
| Mixto | el resto | 243 | 98.9 | 83.6 | 99.9 |
| Cambio o split | cambio + splitter ≥ 25 % | 76 | 96.8 | 81.0 | 100.2 |

**Respuesta:** el arsenal de **rompimiento** (slider o curva como 40 %+ de los pitches) es el que
conserva más Stuff+ en el Harp Helú. A nivel del mar tiene el mismo Stuff+ que el de recta y sinker
(103 contra 104), pero en la CDMX queda 4 puntos arriba. También tiene el mejor Pitching+.

**La prueba real, con pitchers que lanzaron 200+ pitches en cada altitud la misma temporada:**

| Arquetipo | Pitchers | Cambio real en altura (carreras por 100, sin contacto) |
|---|---|---|
| Rompimiento | 15 | +0.07 (−0.15 a +0.29) |
| Recta y sinker | 24 | **+0.30** (0.11 a 0.50) |
| Mixto | 48 | +0.28 (0.18 a 0.40) |
| Cambio o split | 9 | muestra insuficiente |

- Los pitchers de rompimiento pierden menos en lo real, que apunta al mismo lado. **La diferencia
  (−0.23) toca cero (−0.54 a +0.09)** porque hay pocos pitchers que lanzaron en las dos altitudes.
- **Cómo leer el "Stuff+ en el Harp Helú":** todos los pitchers bajan en la CDMX, porque se comparan
  contra la liga a nivel del mar. El pitcher mediano queda en 85. Lo que importa es el **orden**: un
  pitcher con 95 en el Harp Helú está en el 20 % más alto (p80 = 94).

## Límites

- La pérdida por tipo es el promedio de la liga. Para un pitcher específico el estimado ordena, pero
  no es exacto (D-036).
- La altitud viene en tres categorías, no por estadio.
- Los arquetipos son una clasificación fija; un pitcher en el límite puede caer en otro.
