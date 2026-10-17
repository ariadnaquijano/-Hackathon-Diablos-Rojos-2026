# Etapa 6 · La física del aire: el exponente k en densidad

> **Decisión:** D-041. **Evidencia:** `src/fisica_densidad.py` → `reportes/etapa_06_fisica_densidad.json`.
> **Origen:** la auditoría señaló que la explicación de k > 1 ("la pelota llega antes") no alcanzaba.
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
| Presión a 2,240 m | 77.2 kPa (101.3 a nivel del mar) |
| **Densidad relativa del Harp Helú** | **0.785** (rango 0.76–0.81) |
| Frenado relativo medido (mediana 2024–2025) | 0.8445 |
| Coeficiente de arrastre relativo implícito | 1.08 (1.04–1.11) |

El frenado cae menos que la densidad: el coeficiente de arrastre sería ~8 % mayor con aire menos denso.
Es consistente con que la pelota quede en un número de Reynolds más bajo, donde el arrastre por unidad
de densidad sube; es una explicación plausible, no medida.

## k en densidad

k_ρ = k · ln(0.8445) ÷ ln(0.785) = 0.70 · k (rango 0.62–0.80 según temperaturas).

**Qué predice la física.** La fuerza de Magnus es proporcional a la densidad, y el movimiento es
½ · a · t². Con los datos, la recta sale a 92.1 mph y llega a 85.8 en altitud extrema, contra 91.6 y
83.9 a nivel del mar: tarda 1.3 % menos y tiene 2.6 % menos tiempo para moverse. Entonces
k_ρ = 1 + ln(t²) ÷ ln(ρ) = **1.11**.

| Tipo | Componente | k en frenado | **k en densidad** | IC 95 % | Rango por temperatura |
|---|---|---|---|---|---|
| **Liga** | movimiento total | 1.58 | **1.10** | | |
| Recta | IVB | 1.50 | **1.05** | 1.02–1.07 | 0.93–1.20 |
| Recta | HB | 1.64 | 1.14 | 1.10–1.18 | 1.02–1.31 |
| Sinker | IVB | 1.40 | **0.98** | 0.93–1.02 | 0.87–1.12 |
| Sinker | HB | 1.75 | 1.22 | 1.18–1.26 | 1.09–1.40 |
| Curva | HB | 1.67 | 1.16 | 1.08–1.26 | 1.03–1.33 |
| Cambio | IVB | 1.30 | 0.91 | 0.80–0.98 | 0.81–1.04 |
| Cambio | HB | 2.06 | **1.43** | 1.36–1.48 | 1.27–1.64 |
| Curva | IVB | 1.19 | 0.83 | 0.75–0.93 | 0.74–0.95 |
| Slider | HB | 1.22 | 0.85 | 0.78–0.94 | 0.76–0.97 |
| Slider | IVB | 0.68 | **0.47** | 0.42–0.53 | 0.42–0.54 |

**Lectura:**
- **La física cuadra donde más importa.** La recta y el sinker, los pitches que más dependen del efecto
  Magnus y los que más pierden en altura, quedan entre 0.98 y 1.22, alrededor de lo que predice la
  física (1.11). La liga completa da 1.10.
- **Excepciones, sin explicación probada:**
  - HB del cambio, 1.43: pierde más corrida de la que explica el Magnus solo. Hipótesis: los efectos
    de costura (*seam-shifted wake*), importantes en cambios y sinkers, dependen del régimen del flujo,
    que cambia con la densidad.
  - IVB de la slider, 0.47: su IVB promedio es casi cero (≈ 3 in), así que el cociente es inestable, y
    la slider de giro de bala recibe poca fuerza de Magnus.
- **El intervalo de temperatura pesa:** con supuestos extremos, la recta va de 0.93 a 1.20. La
  conclusión "k en densidad ≈ 1" se sostiene en todo el rango para recta y sinker.

## Límites

- No hay datos de clima ni de estadio: la densidad es un cálculo con supuestos, no una medición.
- "Altitud extrema" puede incluir más de un estadio de gran altura; la densidad del Harp Helú es la de
  2,240 m.
- El coeficiente de arrastre relativo es implícito (frenado ÷ densidad), no medido aparte.
