# 02 · Features

> **Estado:** hecha.
> **Entrada:** `data/processed/pitches_limpios.parquet`.
> **Salida:** `data/processed/features.parquet` (635,002 pitches, 145 columnas).
> **Código:** `src/features.py`.
> **Cifras:** todas salen de `reportes/etapa_02_resumen.json`, generado por `src/features.py`.
> **Plan y decisiones previas:** `docs/02_plan_features.md` y `reportes/etapa_02_decisiones.html`.

## Resumen en 30 segundos

- Medimos el **aire de cada juego** con el frenado de las rectas: 2,122 de 2,125 juegos tienen su
  propia medida.
- Estimamos **cuánto cambia el movimiento con el aire** para cada tipo de pitch, corrigiendo un sesgo
  estadístico (atenuación). Con eso convertimos cada pitch a su forma equivalente a nivel del mar:
  el mismo pitcher queda con casi la misma forma en altura y a nivel del mar.
- Reclasificamos 1,342 pitches mal etiquetados, construimos el ángulo de llegada relativo, las
  diferencias contra la recta principal y la zona.
- **Encontramos que el dataset sí trae el orden de los pitches** (en el orden de las filas). Con eso
  reconstruimos 165,649 turnos al bat, el pitch anterior, el tunneling, el conteo de pitches, la
  vuelta al orden y quién abre y quién releva.

## 1. Aire del juego (`air_ratio`)

`air_ratio` = frenado mediano de las rectas del juego ÷ frenado mediano a nivel del mar en esa
temporada. 1.0 = nivel del mar.

| Altitud | Juegos | p10 | Mediana | p90 |
|---|---|---|---|---|
| Extreme (2024) | 223 | 0.82 | 0.85 | 0.90 |
| Extreme (2025) | 237 | 0.81 | 0.84 | 0.88 |
| Extreme (2026) | 142 | 0.79 | 0.84 | 0.90 |
| Medium (2024) | 204 | 0.85 | 0.89 | 0.96 |
| Medium (2025) | 213 | 0.84 | 0.88 | 0.95 |
| Medium (2026) | 91 | 0.87 | 0.91 | 0.95 |
| No Altitude (todas) | 1,002 | ~0.95 | 1.00 | ~1.06 |

- **Por qué por temporada:** el frenado sube un poco cada año en todas las altitudes (pelota o
  calibración). Dividir entre el nivel del mar de la misma temporada lo neutraliza.
- **Juegos con pocas rectas** (3 de 2,125): usan la mediana de su categoría y temporada.
- Los 10 juegos sin categoría de altitud tienen un aire mediano de 0.83 a 0.86: casi seguro son juegos en altura.

## 2. Cuánto cambia el movimiento con el aire (exponente k)

Modelo: movimiento ∝ `air_ratio`^k. Comparamos cada pitcher contra sí mismo, con el mismo pitch, en
salidas con distinto aire.

**El problema que corregimos (decisión D-016).** El aire de cada juego se mide con ruido. En
estadística, el ruido en la variable explicativa achica la pendiente (*atenuación*): la primera
estimación decía k = 1.37 y dejaba al mismo pitcher con ~1 in menos de movimiento después de
convertir. Lo corregimos con una **variable instrumental**: usamos solo la parte del aire que explica
la categoría de altitud y temporada, que se mide con mucha precisión.

| Tipo | k vertical (IVB) | k horizontal (HB) | Pitchers |
|---|---|---|---|
| Liga, movimiento total | 1.58 (IC 95 % 1.55–1.61) | | 1,035 |
| Four-Seam | 1.50 (1.47–1.53) | 1.64 (1.57–1.70) | ~920 |
| Sinker | 1.40 (1.34–1.46) | 1.75 (1.70–1.80) | ~690 |
| Changeup | 1.30 (1.15–1.41) | 2.06 (1.95–2.13) | ~600 |
| Curveball | 1.19 (1.08–1.33) | 1.67 (1.55–1.80) | ~450 |
| Cutter | 1.28 (1.16–1.41) | *usa el de la liga, 1.67* | 301 / 88 |
| Slider | 0.68 (0.60–0.76) | 1.22 (1.11–1.35) | ~600 |
| Splitter | *usa el de la liga, 1.33* | *usa el de la liga, 1.67* | 69–79 |

Un tipo usa su propio k si tiene al menos 100 pitchers; si no, el de la liga. Los intervalos son
bootstrap de 200 remuestreos por pitcher.

**Lectura beisbolística:** k > 1 significa que el movimiento cae más que la densidad del aire. Tiene
sentido: con menos aire hay menos fuerza de Magnus *y* la pelota llega antes, así que tiene menos
tiempo para moverse. El movimiento horizontal del cambio es el más sensible (k = 2.06). La slider es
la menos sensible en vertical (0.68), coherente con que su movimiento depende poco del spin.

**Validación (mismo pitcher, mismo pitch, altitud extrema menos nivel del mar):**

| Pitch | Pares | Δ IVB observado → a nivel del mar | Δ HB observado → a nivel del mar |
|---|---|---|---|
| Four-Seam | 403 | −3.83 → **+0.11** in | −2.82 → −0.50 in |
| Sinker | 203 | −2.66 → **−0.12** in | −4.05 → **−0.04** in |
| Slider | 300 | −0.71 → −0.48 in | +0.65 → **−0.04** in |
| Changeup | 138 | −2.06 → −0.71 in | −4.22 → −0.43 in |
| Curveball | 99 | +1.68 → +0.33 in | +3.10 → +0.57 in |
| Cutter | 41 | −1.99 → **−0.11** in | −0.53 → −0.69 in |

Esta validación usa los mismos pitchers que la estimación; la validación fuera de muestra es parte
de la etapa 5.

## 3. Forma a nivel del mar y reclasificación

- `ivb_sea_level` = IVB ÷ air_ratio^k_ivb y `hb_sea_level` = HB ÷ air_ratio^k_hb, con el k de su tipo.
- **Reclasificación:** de los 2,163 pitches marcados como posibles mal etiquetados en la limpieza,
  **1,342 cambiaron de tipo** y 98 se confirmaron. Cada uno se asigna al pitch del repertorio de
  ese mismo pitcher cuya forma a nivel del mar se le parece más (velocidad, IVB y HB, en unidades
  de desviación robusta: 1.3 mph, 2.5 in, 2.6 in). Los cambios más comunes: changeup → sinker (249),
  changeup → four-seam (225), four-seam → changeup (214).
- `AutoPitchType` y `pitch_group` se conservan; el tipo final es `pitch_class`.

## 4. Sweeper contra slider (decisión D-013, aplicada)

Ajustamos una mezcla de dos normales sobre el movimiento horizontal a nivel del mar de las sliders:
grupos en −9.9 in (25 %) y −2.7 in (75 %), con una D de Ashman de **1.59**. Por debajo de 2 los
grupos se enciman: **en la LMB no hay un corte natural entre sweeper y slider**. Como acordamos en
D-013, usamos **12 in hacia el guante sobre la forma a nivel del mar**.

| Altitud | % sweeper con movimiento observado | % sweeper con forma a nivel del mar |
|---|---|---|
| Extreme | 3.1 % | **7.3 %** |
| Medium | 5.6 % | 8.4 % |
| No Altitude | 12.6 % | 12.6 % |

**Resultado honesto:** la conversión cierra casi la mitad de la brecha, pero no toda. La mediana de
la slider queda bien corregida (Δ HB −0.04 in), pero los sweepers, que son la cola de la
distribución, parecen perder más que la slider típica. Siguiente paso: un k que dependa del tamaño
del movimiento. Mientras tanto la etiqueta es consistente para el 96 % de los pitchers en casa y de
visita (94.7 % sin convertir), y el modelo usa el movimiento continuo, no la etiqueta.

## 5. Ángulos relativos (decisión D-012, aplicada)

`vaa_rel` = VAA − VAA esperado por altura de llegada; `haa_rel` = HAA (lado del brazo) − HAA
esperado por lado de llegada. Parábola por tipo de pitch, **ajustada solo con 2024–2025** y revisada
en 2026:

| Pitch | Correlación del VAA crudo con la altura | Correlación del VAA relativo con la altura |
|---|---|---|
| Four-Seam | 0.89 | **0.006** |
| Sinker | 0.87 | −0.010 |
| Slider | 0.83 | 0.022 |
| Changeup | 0.85 | −0.035 |
| Curveball | 0.73 | 0.028 |
| Cutter | 0.90 | −0.022 |

En rectas de 2026, la media de `vaa_rel` por decil de altura no se aleja más de 0.02° de cero: no
queda dependencia no lineal.

## 6. Arsenal (decisión D-014, aplicada)

- **Recta principal** (por pitcher y temporada; un pitcher puede cambiarla de un año a otro): four-seam en 788 pitchers, sinker en 350, cutter en 54.
- **Referencia:** mezcla de la recta del mismo juego con la del resto de sus salidas en esa altitud y
  temporada (sin contar el juego actual), con peso n / (n + k). k medido sobre la recta principal:

| Variable | k |
|---|---|
| Velocidad | 1.9 |
| IVB | 4.1 |
| HB | 3.4 |
| Eje de spin | 5.3 |
| Altura de release | 0.9 |
| Lado de release | 0.9 |
| Extensión | 0.9 |

  El release cambia más entre salidas que dentro de una (k < 1): ahí manda el juego. El eje de spin
  es ruidoso dentro del juego (k = 5.3): ahí manda el resto de sus salidas. *Nota:* en el reporte de
  decisiones k salía 2.4 y 4.8 porque se medía sobre todas las four-seam y sinkers; aquí se mide
  sobre la recta principal, que es la que usamos.
- **Variables:** `velo_diff_vs_fb`, `ivb_diff_vs_fb`, `hb_diff_vs_fb`, `axis_diff_vs_fb`,
  `release_dist_vs_fb`, `extension_diff_vs_fb`, `pitch_usage_pct`, `arsenal_size`.
- **Cobertura:** 99.5 % de los pitches usables tienen diferencias de arsenal.

## 7. Física extra

- `total_break`, `total_break_sea_level`.
- `magnus_dependence` = movimiento total a nivel del mar ÷ (spin / velocidad). Mediana: four-seam
  0.78, sinker 0.77, changeup 0.74, curva 0.41, cutter 0.41, slider 0.24.

## 8. Contexto (solo Location+ y Pitching+)

- `zone`: 9 celdas (alto/medio/bajo × adentro/centro/afuera respecto al bateador) y 4 regiones fuera.
  Usa la misma caja que la bandera `in_strike_zone` del dataset (1.62–3.21 ft de alto, ±0.708 ft):
  coincide en todos los pitches salvo 83 en el borde.
- `platoon_same_side`: si el bateador batea del mismo lado que lanza el pitcher. Las manos y el lado
  del bateador **siguen como variables**: el lado del brazo solo sirve para comparar formas.

## 9. Secuencia (decisión D-015)

El dataset no trae número de pitch, pero **sus filas vienen en orden cronológico**: dentro de cada
juego la entrada nunca retrocede (99.94 %) y el conteo de cada turno tampoco (99.99 %). La limpieza
ahora guarda ese orden en `pitch_seq`.

| Variable | Qué es |
|---|---|
| `pa_id`, `pitch_of_pa` | Turno al bat reconstruido y número de pitch en el turno |
| `prev_pitch_class`, `same_as_prev`, `velo_diff_vs_prev`, `plate_dist_vs_prev` | El pitch anterior del mismo pitcher en el turno |
| `tunnel_dist_vs_prev` | Separación con el pitch anterior en el punto de decisión del bateador (175 ms antes del plato), calculada con la trayectoria de Trackman |
| `pitcher_pitch_count` | Pitches del pitcher en el juego |
| `times_through_order` | Cuántas veces ha enfrentado a ese bateador en el juego |
| `pitcher_role`, `entry_inning` | Abridor (entra en la 1ra) o relevista, y la entrada en que entró |

**Validación:** 165,649 turnos; el 98.7 % empieza en 0-0. 4,303 aperturas (unas 2 por juego, como
debe ser); los relevistas entran en la 7ma de mediana. 5,445 pitches de un bateador con ID genérico
(hasta 72 turnos en un juego) quedan sin vuelta al orden. 4,754 pitches sin ID de bateador quedan
sin secuencia.

**Primera evidencia de que la secuencia importa:**

| Medida | Resultado |
|---|---|
| Separación del pitch anterior *después* del punto de decisión (cuartiles) | Whiff por swing de **20.3 % a 31.3 %** |
| Vuelta al orden 1 → 2 → 3 | Whiff por swing 25.0 % → 22.7 % → 21.8 %; hit por bola en juego 35.8 % → 36.9 % |
| Repetir el mismo pitch contra cambiarlo | 23.5 % contra 24.1 % |

El efecto de tunneling todavía mezcla combinaciones de pitches; el modelo lo separa.

## Qué no se pudo y por qué

- **Series de 3 juegos:** los juegos vienen por fecha y la serie se nota (el siguiente juego de un
  bateador es en la misma altitud 74 % de las veces contra 36 % al azar), pero falta reconstruir los
  equipos a partir de los jugadores. Queda para la herramienta de aclimatación.
- **Clima del día:** sin fecha ni estadio no podemos unir datos de clima históricos.

## Qué sigue

Etapa 3: el target de carreras esperadas y el baseline por conteo, ahora por turno reconstruido.
