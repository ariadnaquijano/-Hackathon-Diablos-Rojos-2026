# Etapa 4 · Plan: Stuff+, Location+ y Pitching+

> **Estado:** propuesta, pendiente de validar por el equipo.
> **Evidencia:** `src/exploracion_etapa_04.py`; cifras en `reportes/etapa_04_exploracion.json`.
> Predicciones de la exploración en `data/processed/predicciones_etapa_04_exploracion.parquet` (no
> se sube al repo).

## Qué queremos

Tres números por pitch y por pitcher, en escala 100 = promedio de la temporada:

- **Stuff+:** cuánto vale el pitch solo por su forma física (velocidad, movimiento a nivel del mar,
  release, extensión, diferencias contra su recta).
- **Location+:** cuánto vale solo por dónde llegó y en qué conteo.
- **Pitching+:** las dos cosas juntas, más la secuencia.

Cada uno solo cuenta si le gana a los modelos base (D-020) con intervalo que no toque cero.

## Lo que encontramos en la primera versión

Primera versión con gradient boosting y el target xRV neutral, sin afinar nada. Entrenada con
2024–2025 y evaluada en 2026. Todos los intervalos remuestrean pitchers completos.

### 1. El ajuste por altitud funciona (el hallazgo más fuerte)

Mismo pitcher, mismo tipo de pitch, en altitud extrema y a nivel del mar (368 pitchers, 710 pares
pitcher–pitch con al menos 50 pitches en cada lado):

| Versión | Extrema − mar (carreras por 100) | IC 95 % | Correlación entre altitudes | IC 95 % |
|---|---|---|---|---|
| **Stuff+ con forma a nivel del mar** | **0.074** | 0.064 a 0.085 | **0.923** | 0.910 a 0.934 |
| Stuff+ con movimiento observado | 0.304 | 0.288 a 0.320 | 0.740 | 0.701 a 0.773 |
| Stuff+ con `altitude_category` como variable | 0.452 | 0.433 a 0.472 | 0.695 | 0.652 a 0.732 |
| xRV real neutral (referencia) | 0.572 | 0.431 a 0.730 | 0.151 | 0.074 a 0.219 |

- Con la forma a nivel del mar, la brecha entre altitudes baja de 0.30 a 0.07 (diferencia de
  −0.25 a −0.22) y la correlación sube de 0.74 a 0.92 (diferencia de +0.15 a +0.22). Es la
  evidencia directa a favor de D-001: meter `altitude_category` como variable lo hace **peor**.
- **Cuidado al presentarlo:** parte de la consistencia viene de construcción: si las variables ya
  no cambian con el aire, la predicción tampoco. Lo que demuestra es que el Stuff+ deja de castigar
  a un pitcher por el estadio. **No** demuestra que el pitcher rinda igual: su xRV real sí empeora en
  altura (+0.57 por 100 pitches). Eso es el costo del estadio, y lo mide la versión local.

### 2. Por pitch, en 2026 (mejora del error contra la media de la liga)

| Modelo | Mejora | IC 95 % | Diferencia contra la lineal |
|---|---|---|---|
| Regresión lineal por tipo (base) | +0.107 % | 0.068 a 0.147 | — |
| Stuff+ forma a nivel del mar | +0.124 % | 0.090 a 0.160 | −0.018 a +0.053 (empate) |
| Stuff+ movimiento observado | +0.146 % | 0.111 a 0.182 | +0.009 a +0.069 |
| Stuff+ con `altitude_category` | +0.148 % | 0.112 a 0.187 | +0.012 a +0.074 |
| Location+ | +5.34 % | 4.99 a 5.67 | +4.90 a +5.56 |
| Pitching+ | +5.25 % | 4.91 a 5.55 | +4.82 a +5.44 |

La ubicación y el conteo deciden si un pitch es bola o strike; por eso explican mucho más por pitch.
Las versiones de Stuff+ sin ajuste ganan un poco por pitch. Nuestra hipótesis, sin probar: ven el
efecto del aire en el resultado, a costa de no ser comparables entre estadios.

### 3. Por pitcher, en 2026 (114 pitchers con 300+ pitches en ambos periodos)

| Modelo | r con su xRV real | IC 95 % | Error por 100 | Contra la lineal |
|---|---|---|---|---|
| Regresión lineal por tipo (base) | 0.454 | 0.293 a 0.596 | 0.649 | — |
| **Pitching+** | **0.473** | 0.323 a 0.598 | **0.609** | error −0.119 a +0.031 (no probado) |
| Stuff+ forma a nivel del mar | 0.347 | 0.184 a 0.496 | 0.697 | error +0.003 a +0.092 (**peor**) |
| Location+ | 0.270 | 0.111 a 0.409 | 0.719 | no |

### 4. A futuro: valor de 2024–2025 para predecir el 2026 de cada pitcher

Las predicciones de 2024–2025 vienen de modelos que no vieron a ese pitcher (5 pliegues por pitcher).

| Predictor | r con su 2026 real | IC 95 % | Error por 100 |
|---|---|---|---|
| **Su xRV de 2024–2025 encogido hacia la media** | **0.383** | 0.221 a 0.532 | **0.707** |
| Regresión lineal por tipo | 0.274 | 0.063 a 0.446 | 0.716 |
| Pitching+ | 0.165 | −0.060 a 0.379 | 0.770 |
| Stuff+ forma a nivel del mar | 0.155 | −0.049 a 0.345 | 0.753 |

**Hoy ningún modelo físico predice el año siguiente mejor que la historia del pitcher.** La regresión
lineal usa predicciones dentro de muestra en 2024–2025 (tiene pocos parámetros, pero es una ventaja
a su favor).

### Lectura honesta

- El gradient boosting de Stuff+ paró en 64–82 árboles: con el target de carreras por pitch casi no
  encuentra patrón más allá de lo que ve una regresión lineal.
- Lo que sí está probado: el ajuste por altitud y que la ubicación y el conteo pesan mucho por pitch.
- Lo que falta: un Stuff+ que le gane a la lineal y un valor que prediga el futuro mejor que la
  historia.

## Decisiones propuestas

### 1. 2026 ya no se usa para elegir nada (D-025)

Ya vimos los resultados de 2026. Si ahora ajustamos hasta ganar en 2026, el resultado estaría
inflado. Toda elección (variables, target, hiperparámetros) se hace **entrenando con 2024 y
evaluando en 2025**. 2026 se usa una sola vez al final, con el modelo ya congelado, y se reporta lo
que salga.

### 2. Tres caminos para Stuff+, elegidos en 2025

Se prueban por separado, con la misma evaluación por pitcher:

| Camino | Por qué podría ayudar |
|---|---|
| **Target menos ruidoso:** probabilidades de whiff, strike cantado, foul y valor esperado del contacto, combinadas con los pesos del conteo | Varios Stuff+ públicos de MLB modelan los componentes por separado: el valor final de un pitch es casi todo ruido; sus componentes, menos |
| **Más regularización o modelo por tipo de pitch** | Con 75 árboles el modelo general no separa bien una slider de una recta |
| **Combinar con la historia del pitcher** (encoger Stuff+ y su xRV pasado juntos) | La historia gana a futuro; la física ayuda donde no hay historia (64 de 178 pitchers de 2026) |

**Regla fijada antes de probar:** gana el camino con menor error por pitcher en 2025. Si ninguno le
gana a la lineal con intervalo fuera de cero, se reporta así y la lineal se queda como Stuff+.

### 3. Location+ y Pitching+

- Location+ se queda como está, con dos chequeos en 2025: que no use la forma del pitch y que su
  valor por pitcher sea estable entre mitades.
- Pitching+ sigue el camino que gane en Stuff+.

### 4. Escala 100

Stuff+ = 100 − 10 × (valor predicho − promedio de la temporada) ÷ desviación entre pitchers de ese
valor. Más alto es mejor para el pitcher, como en MLB.

## Entregables

- `src/modelo.py`: los tres modelos finales y sus valores por pitch y por pitcher.
- `docs/04_modelo.md` y `reportes/etapa_04_modelo.html`.

## Límites conocidos

- 114 pitchers en las pruebas por pitcher: se ven diferencias grandes, no pequeñas.
- 2026 es una temporada parcial (135 mil pitches).
- El ajuste por altitud se probó con la consistencia del mismo pitcher; no hay forma de observar al
  mismo pitch en dos aires a la vez.
