# Etapa 5 · Stuff+ por tipo de pitch (arsenal)

> **Estado:** probado con la regla D-033.
> **Evidencia:** `src/arsenal.py`; cifras en `reportes/etapa_05_arsenal.json`. La tabla por pitcher y
> tipo de pitch está en `data/processed/arsenal.parquet` (no se sube al repo).
> **Datos:** evaluación solo con los pares 2024 → 2025. 2026 entra a la tabla, no a la evaluación.

## Qué es

Cada pitch de cada pitcher con 100+ pitches en la temporada recibe:

- **Stuff+ dentro de su tipo:** una slider se compara contra las sliders de la liga. Escala 100, más
  alto es mejor, 10 puntos es una desviación entre pitchers.
- **Sus componentes** (D-027): P(swing), P(whiff | swing), P(foul | contacto) y P(strike cantado |
  toma). Dicen por qué funciona el pitch: genera swings y fallos, roba strikes o saca contacto débil.
- **Su uso:** porcentaje de los pitches del pitcher.

| Temporada | Pitches de pitcher | Rectas | Sliders | Sinkers | Cambios | Curvas | Cutters | Splitters |
|---|---|---|---|---|---|---|---|---|
| 2024 | 794 | 272 | 195 | 133 | 98 | 66 | 25 | 5 |
| 2025 | 854 | 295 | 198 | 162 | 93 | 70 | 32 | 4 |
| 2026 | 417 | 163 | 99 | 87 | 42 | 14 | 11 | 1 |

**Qué mueve el Stuff+ de un pitch:** correlación del Stuff+ con cada componente, 2024 / 2025 / 2026.

| Componente | r |
|---|---|
| P(whiff \| swing) | 0.72 / 0.67 / 0.73 |
| P(swing) | 0.52 / 0.54 / 0.58 |
| P(foul \| contacto) | 0.42 / 0.42 / 0.53 |
| P(strike cantado \| toma) | 0.11 / 0.22 / 0.15 |

El whiff es lo que más separa un buen pitch de uno malo.

## Resultados (334 pares pitcher–pitch de 2024 → 2025, 174 pitchers)

### Se repite mucho más que el resultado

| Valor del mismo pitch | r de 2024 a 2025 | IC 95 % |
|---|---|---|
| xRV total | 0.17 | 0.05 a 0.28 |
| xRV sin contacto (D-032) | 0.44 | 0.35 a 0.53 |
| **Stuff+** | **0.85** | 0.81 a 0.88 |
| P(whiff \| swing) | 0.85 | 0.81 a 0.89 |
| P(strike cantado \| toma) | 0.86 | 0.82 a 0.89 |

Por tipo, el Stuff+ se repite entre 0.82 (rectas) y 0.89 (cambios y sinkers).

### Predice, pero no mejor que la historia del pitch

| Predictor de 2024 | r con el xRV sin contacto de 2025 | IC 95 % | Diferencia contra la historia |
|---|---|---|---|
| Historia sin contacto del pitch | 0.44 | 0.35 a 0.53 | — |
| Stuff+ del pitch | 0.22 | 0.10 a 0.33 | −0.34 a −0.10 (**peor**) |

| Predictor de 2024 | r con el xRV total de 2025 | IC 95 % | Diferencia contra la historia |
|---|---|---|---|
| Historia total del pitch | 0.17 | 0.05 a 0.28 | — |
| Stuff+ del pitch | 0.14 | 0.04 a 0.24 | −0.17 a +0.11 (empate) |

## Qué significa

1. **El Stuff+ por pitch sí mide algo real:** predice el resultado del año siguiente con un intervalo
   fuera de cero, y es el doble de estable que el mejor resultado observado.
2. **No reemplaza la historia de un pitch que ya tiene muestra.** Su valor está donde no hay historia:
   - un pitch nuevo o modificado;
   - un pitcher que llega a la liga;
   - un pitch con poca muestra.
   Ahí la historia no existe, y el Stuff+ solo necesita la forma del pitch, no sus resultados.
3. **Para el cuerpo técnico,** los componentes dicen qué hacer con cada pitch. Un pitch con whiff alto
   y strike cantado bajo sirve para terminar turnos, no para ponerse adelante.

## Límites

- Con 100+ pitches por tipo quedan fuera los pitches poco usados; los cutters y splitters tienen poca
  muestra.
- Las diferencias contra la recta usan el movimiento observado, así que no quedan del todo a nivel del
  mar. El efecto en la consistencia entre altitudes es pequeño (`docs/04_modelo.md`, sección 2).
