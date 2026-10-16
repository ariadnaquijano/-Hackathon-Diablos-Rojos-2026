# Etapa 4 · Modelo final: Stuff+, Location+ y Pitching+

> **Estado:** versión 1, congelada y evaluada una sola vez en 2026 (D-030). La versión 2 (D-035)
> solo cambia Location+ a árboles de 31 hojas; sus cifras están en `docs/04_afinado.md` y no cambian
> ninguna conclusión de este documento.
> **Evidencia:** `src/modelo.py`; cifras en `reportes/etapa_04_modelo.json`; reporte visual en
> `reportes/etapa_04_modelo.html` (`python src/reporte_modelo.py`).
> Los valores por pitcher están en `data/processed/valores_pitchers.parquet`, que no se sube al repo.

## El modelo

| Pieza | Qué es | Decisión |
|---|---|---|
| **Stuff+** | P(swing), P(whiff \| swing), P(foul \| contacto), P(strike cantado \| toma) y valor del batazo, solo con la forma a nivel del mar, combinados con el valor promedio de cada desenlace | D-027 |
| **Location+** | Ubicación en la zona y conteo, por tipo de pitch y mano | D-028 |
| **Pitching+** | 0.60 × Stuff + 1.06 × Location, en carreras (regresión del xRV de cada pitch) | D-029 |
| **Proyección** | xRV del año siguiente = 0.17 × xRV histórico + 0.13 × Pitching+ (pares 2024 → 2025) | D-030 |

- **Entrenamiento:** gradient boosting con 2024–2025. Los árboles se eligieron con un 20 % de pitchers
  no vistos: swing 502, whiff 418, strike 401, foul 98, batazo 22, Location+ 274.
- **Escala:** 100 − 10 × (valor − media de la temporada) ÷ desviación entre pitchers. Más alto es
  mejor; cada 10 puntos es una desviación.

## Resultados en 2026, una sola corrida

Los intervalos son de 95 % y remuestrean pitchers completos (1,000 repeticiones, semilla 2026).

### 1. Por pitch: los tres le ganan a las bases

| Modelo | Mejora contra la media | IC 95 % | Contra la lineal observada | Contra la lineal a nivel del mar |
|---|---|---|---|---|
| Lineal a nivel del mar | +0.08 % | 0.04 a 0.12 | −0.05 a −0.01 | — |
| Lineal observada | +0.11 % | 0.07 a 0.15 | — | +0.01 a +0.05 |
| **Stuff+** | **+0.15 %** | 0.11 a 0.20 | **+0.01 a +0.09** | **+0.04 a +0.11** |
| **Location+** | **+5.29 %** | 4.97 a 5.65 | +4.86 a +5.54 | +4.89 a +5.57 |
| **Pitching+** | **+5.37 %** | 5.03 a 5.75 | +4.93 a +5.64 | +4.96 a +5.66 |

En la exploración, el Stuff+ con forma a nivel del mar empataba con la lineal observada. El de
componentes **le gana a las dos bases con un intervalo fuera de cero**, aunque no usa información de la
altitud.

### 2. Ajuste por altitud: el Stuff+ no castiga al pitcher por el estadio

Mismo pitcher y mismo tipo de pitch, en altitud extrema y a nivel del mar (368 pitchers, 710 pares):

| Valor | Extrema − mar (carreras por 100) | IC 95 % | r entre altitudes | IC 95 % |
|---|---|---|---|---|
| xRV real (referencia) | 0.572 | 0.431 a 0.730 | 0.15 | 0.07 a 0.22 |
| **Stuff+** | **0.048** | 0.036 a 0.059 | **0.92** | 0.91 a 0.93 |
| Pitching+ | 0.089 | 0.055 a 0.127 | 0.71 | 0.67 a 0.74 |

- El xRV real empeora +0.57 carreras por 100 pitches en altura. El Stuff+ solo mueve 0.05; la brecha
  de la exploración era 0.07.
- Pitching+ es menos consistente entre altitudes (r 0.71 contra 0.92) porque la ubicación sí cambia
  de un estadio a otro.
- **Cuidado:** parte de la consistencia viene de construcción, porque las variables ya no cambian con
  el aire.

### 3. Por pitcher, misma temporada (178 pitchers con 300+ pitches en 2026)

| Modelo | r con su xRV real | IC 95 % | Error por 100 | Contra la lineal observada | Contra la lineal a nivel del mar |
|---|---|---|---|---|---|
| **Pitching+** | **0.45** | 0.32 a 0.56 | **0.689** | −0.113 a +0.038 | −0.138 a +0.010 |
| Lineal observada | 0.45 | 0.33 a 0.56 | 0.723 | — | −0.055 a −0.001 |
| Stuff+ | 0.42 | 0.29 a 0.56 | 0.738 | −0.042 a +0.066 | −0.067 a +0.041 |
| Lineal a nivel del mar | 0.41 | 0.27 a 0.54 | 0.750 | +0.001 a +0.055 | — |
| Location+ | 0.30 | 0.17 a 0.41 | 0.772 | −0.026 a +0.124 | −0.050 a +0.093 |

Las diferencias de las dos últimas columnas son de error por 100 pitches.

- Pitching+ tiene el menor error, pero ningún modelo le gana a las bases por pitcher con un intervalo
  fuera de cero: es **empate**.
- 2026 confirma D-026 fuera de muestra: la lineal observada le gana a la lineal a nivel del mar
  (error −0.055 a −0.001), porque ve el estadio.

### 4. A futuro: 2024–2025 para predecir el 2026 de cada pitcher (114 pitchers)

| Predictor de 2024–2025 | r con su xRV real de 2026 | IC 95 % | Error por 100 | Error contra la persistencia |
|---|---|---|---|---|
| **Persistencia encogida (base)** | **0.38** | 0.22 a 0.53 | **0.708** | — |
| Proyección: historia + Pitching+ | 0.34 | 0.17 a 0.50 | 0.715 | −0.004 a +0.021 |
| Lineal a nivel del mar | 0.29 | 0.09 a 0.47 | 0.715 | −0.042 a +0.058 |
| Lineal observada | 0.27 | 0.06 a 0.45 | 0.716 | −0.050 a +0.068 |
| Stuff+ | 0.21 | 0.03 a 0.38 | 0.739 | −0.016 a +0.081 |
| Pitching+ | 0.01 | −0.19 a +0.24 | 0.833 | +0.018 a +0.246 |
| Location+ | −0.08 | −0.28 a +0.14 | 0.854 | +0.046 a +0.258 |

- **Ningún modelo predice el año siguiente mejor que la historia del pitcher.** La proyección empata
  con ella y queda un poco abajo en el punto.
- Location+ no predice el año siguiente (r −0.08), y por eso Pitching+ tampoco. En 2024 → 2025 sí
  había dado 0.22. Es inestable: la ubicación de un año no anticipa los resultados del siguiente.
- Entre los componentes, **Stuff+ es el que más se acerca a predecir el futuro** (r 0.21, intervalo
  fuera de cero). Es lo que la literatura de MLB espera: la forma del pitch es la parte más estable de
  la habilidad.

### 5. La escala

| Temporada | Pitchers | Stuff+ p10 / p50 / p90 | Location+ p10 / p50 / p90 | Pitching+ p10 / p50 / p90 |
|---|---|---|---|---|
| 2024 | 320 | 89 / 101 / 113 | 86 / 101 / 111 | 86 / 101 / 112 |
| 2025 | 320 | 89 / 100 / 115 | 86 / 101 / 111 | 87 / 101 / 112 |
| 2026 | 178 | 88 / 100 / 115 | 91 / 103 / 116 | 90 / 103 / 115 |

- Por pitcher, Pitching+ queda casi igual a Location+ (r 0.91–0.93). Con Stuff+ la correlación es
  0.24–0.43.
- Los pesos se ajustaron por pitch, y ahí la ubicación y el conteo mueven mucho más el valor. Entre
  pitchers, la diferencia de ubicación es más grande que la de forma.

## Conclusiones

**Lo que está probado (intervalo fuera de cero en 2026, con un modelo congelado):**

1. **El ajuste por altitud funciona.** El Stuff+ del mismo pitcher cambia 0.05 carreras por 100 entre
   la altitud extrema y el nivel del mar, mientras su resultado real cambia 0.57. Es la respuesta
   central al reto: comparar a un pitcher del Harp Helú con uno de la costa sin castigarlo por el aire.
2. **Stuff+ le gana a la regresión lineal por pitch**, tanto a la observada como a la de nivel del mar,
   sin usar la altitud.
3. **Location+ y Pitching+ explican el 5.3 % del error por pitch**, contra 0.1 % de la mejor base.

**Lo que empata:** por pitcher en la misma temporada, Pitching+ tiene el menor error, pero no le gana a
las bases con un intervalo fuera de cero.

**Lo que no logramos:** predecir el año siguiente mejor que la historia del pitcher. La proyección
empata y Location+ no predice.

## Qué significa para el club

- **Para evaluar y comparar pitchers entre estadios:** Stuff+.
  - Es estable: r 0.83 de 2024 a 2025 en 146 pitchers, contra 0.18 del xRV real.
  - No depende del parque.
  - Es el que más se acerca a anticipar el futuro.
- **Para entender cómo le fue a un pitcher en una temporada:** Pitching+, desglosado en Stuff+ y
  Location+.
- **Para proyectar el año siguiente:** la historia del pitcher encogida hacia la media sigue siendo lo
  mejor. Para un pitcher sin historia en la liga (64 de 178 en 2026), Stuff+ es lo único disponible, y
  predice algo (r 0.21).

## Límites

- 2026 es una temporada parcial: 178 pitchers por pitcher y 114 a futuro. Solo se ven diferencias
  grandes.
- Las predicciones a futuro de 2024–2025 vienen de modelos que vieron 2024–2025 de otros pitchers. No
  hay fuga del mismo pitcher, pero sí del ambiente de la liga.
- La decisión D-026 se tomó después de ver 2025. Por eso se reportan las dos bases.
- El Stuff+ por tipo de pitch (arsenal) y la versión local (el costo del estadio) se construyen en la
  siguiente etapa.
