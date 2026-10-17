# Etapa 6 · La física del aire: el exponente k en densidad

> **Decisión:** D-041 (corregida tras la segunda auditoría). **Evidencia:** `src/fisica_densidad.py` →
> `reportes/etapa_06_fisica_densidad.json`.
> **El modelo no cambia:** la traducción a nivel del mar usa el frenado medido y su k juntos.

## El problema

Medimos el aire de cada juego con el **frenado de las rectas** (`air_ratio`), no con la densidad. El
frenado es densidad × coeficiente de arrastre (ρ · Cd). Por eso nuestro k (1.5 en la recta, 1.58 en la
liga) no se puede leer como "el movimiento cae más rápido que la densidad".

## La densidad del Harp Helú

Atmósfera estándar y ley de los gases ideales (ρ = p ÷ R·T). Sin datos de clima ni de estadio, se
suponen temperaturas de juego: 24–32 °C en estadios a nivel del mar y 14–24 °C en la CDMX. La humedad
mueve la densidad menos de 1 %.

| | Valor |
|---|---|
| Presión a 2,240 m (atmósfera estándar) | 77.2 kPa; la presión típica real de la CDMX ronda 78 kPa |
| **Densidad relativa del Harp Helú** | **0.785** (rango 0.76–0.81 por temperatura) |
| Frenado relativo medido (mediana 2024–2025) | 0.8445 |
| Frenado ÷ densidad (coeficiente de arrastre relativo implícito) | 1.08 (1.04–1.11) |

El frenado cae menos que la densidad. Hay cuatro explicaciones posibles y no podemos separarlas:

1. "Altitud extrema" incluye estadios algo más bajos que el Harp Helú, con más densidad.
2. Las temperaturas supuestas.
3. La calibración del TrackMan, que puede ser distinta en cada estadio.
4. Un coeficiente de arrastre mayor con aire menos denso. Esta es la menos probable: las mediciones
   de túnel de viento muestran un arrastre casi plano entre 60 y 100 mph.

## Qué predice la física

El movimiento es ½ · a · t², con la aceleración de Magnus ∝ ρ · v² · C_L y v · t = distancia. Con los
datos, la recta sale a 92.1 mph y llega a 85.8 en altitud extrema, contra 91.6 y 83.9 a nivel del mar:
**tarda 1.3 % menos** en llegar (y t² baja 2.6 %).

| Supuesto sobre el coeficiente de Magnus (C_L) | Movimiento ∝ | k en densidad predicho |
|---|---|---|
| C_L constante | ρ | 1.00 |
| **C_L ∝ giro ÷ velocidad** (spin bajo, lo usual en pitcheo) | ρ · t | **1.05** |
| La aceleración no depende de la velocidad (cota superior) | ρ · t² | 1.11 |

**Rango predicho: 1.00 a 1.11.**

## k en densidad

k_ρ = k · ln(0.8445) ÷ ln(0.785) = 0.70 · k (0.62–0.80 según temperaturas).

| Tipo | Componente | k en frenado | **k en densidad** | IC 95 % del k | Rango por temperatura |
|---|---|---|---|---|---|
| **Liga** | movimiento total | 1.58 | **1.10** | | |
| Liga | IVB | 1.33 | 0.93 | | |
| Liga | HB | 1.67 | 1.17 | | |
| Recta | IVB | 1.50 | **1.05** | 1.02–1.07 | 0.93–1.20 |
| Recta | HB | 1.64 | 1.14 | 1.10–1.18 | 1.02–1.31 |
| Sinker | IVB | 1.40 | 0.98 | 0.93–1.02 | 0.87–1.12 |
| Sinker | HB | 1.75 | 1.22 | 1.18–1.26 | 1.09–1.40 |
| Cambio | IVB | 1.30 | 0.91 | 0.80–0.98 | 0.81–1.04 |
| Cambio | HB | 2.06 | 1.43 | 1.36–1.48 | 1.27–1.64 |
| Curva | IVB | 1.19 | 0.83 | 0.75–0.93 | 0.74–0.95 |
| Curva | HB | 1.67 | 1.16 | 1.08–1.26 | 1.03–1.33 |
| Slider | IVB | 0.68 | 0.47 | 0.42–0.53 | 0.42–0.54 |
| Slider | HB | 1.22 | 0.85 | 0.78–0.94 | 0.76–0.97 |

El IC 95 % escala solo la incertidumbre de k; la de la densidad va aparte, en el rango por
temperatura.

**Lectura:**
- **El movimiento total de la liga (1.10) y la IVB de la recta (1.05) caen dentro del rango que
  predice la física.** La IVB de la recta es el "ride", lo que más pierde valor en altura.
- **Patrón que no explica la física: el movimiento horizontal cae más que el vertical en los cinco
  tipos** (liga: HB 1.17 contra IVB 0.93). El efecto Magnus escala los dos componentes igual, así que
  una brecha sistemática apunta a otra cosa. **El placebo de D-043 descarta que sea algo del Harp
  Helú:** la brecha aparece igual comparando altitud media contra nivel del mar (+0.33) que altitud
  extrema contra nivel del mar (+0.35). Candidatos que quedan, sin probar: el marco de referencia del
  movimiento horizontal o los efectos de costura (*seam-shifted wake*), que dependen del régimen del
  flujo. El HB del cambio (1.43) es el caso más extremo de este patrón.
- **IVB de la slider (0.47):** su IVB promedio es casi cero (≈ 3 in), así que el cociente es inestable.
  Que sea de giro de bala, con poca fuerza de Magnus, es una hipótesis.
- **La temperatura pesa:** con supuestos extremos, la IVB de la recta va de 0.93 a 1.20. Ese rango no
  distingue entre 1.00 y 1.11, pero sí descarta el k de 1.5 en frenado como lectura en densidad.

## Límites

- No hay datos de clima ni de estadio: la densidad es un cálculo con supuestos, no una medición.
- El tiempo de vuelo usa medianas de toda la liga en cada altitud, no el mismo pitcher en las dos; la
  velocidad de salida difiere 0.5 mph entre altitudes por la mezcla de pitchers.
- El instrumento de k es la categoría de altitud × temporada. **Placebo (D-043):** el k estimado con
  altitud media sale entre 5 y 9 % mayor que con altitud extrema (liga 1.63 contra 1.56). Puede ser
  calibración propia de cada estadio o que un solo k sea una aproximación; no se pueden separar. Para
  el modelo pesa poco: usar el k de extrema cambia el movimiento traducido de la recta en 0.3 %.
