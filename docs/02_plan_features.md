# 02 · Plan de features

> **Estado:** plan en revisión del equipo. Todavía no se construye nada.
> **Entrada:** `data/processed/pitches_limpios.parquet`.
> **Salida prevista:** `data/processed/features.parquet` (un renglón por pitch).
> **Evidencia:** todas las cifras salen de `src/exploracion_etapa_02.py`.

## Qué es un feature y por qué esta etapa importa

Un *feature* es una variable que el modelo usa para predecir. Aquí decidimos **qué información
ve el modelo** de cada pitch. Es la etapa que más pesa en el criterio "Integración arsenal +
altitud" (25 % de la calificación).

Regla que no se rompe: **ningún feature usa el resultado del pitch.** Todo sale de la física, del
repertorio del pitcher o del contexto previo al pitch.

---

## Lo que validamos antes de proponer

### 1. Podemos medir el aire de cada juego, y es física real

De la trayectoria de Trackman calculamos cuánto frena cada recta (proxy de arrastre). La duda era
si eso mide el aire o la calibración de la cámara en cada estadio. Dos pruebas:

| Prueba | Si fuera aire real… | Resultado |
|---|---|---|
| Four-seam vs sinker del **mismo juego** | Ambos frenan igual | Correlación **0.94** (2,050 juegos) |
| Arrastre vs IVB del mismo juego (contra el IVB normal de cada pitcher) | Menos arrastre = menos movimiento, **incluso dentro de la misma categoría de altitud** | Correlación 0.41 (Extreme), 0.36 (Medium), 0.56 (No Altitude) |

**Conclusión:** el proxy mide el aire. Además varía *dentro* de cada categoría de altitud, así que
es más fino que las tres cajas que nos dieron.

**Razón de arrastre contra nivel del mar:** Extreme 0.84, Medium 0.89. Para CDMX la física
predice ~0.78; nuestro 0.84 es un promedio de varios parques altos. Los juegos con el aire más
delgado son los candidatos a ser el Harp Helú (no lo podemos confirmar sin ID de estadio).

**Hallazgo a corregir:** el arrastre sube cada temporada en todas las altitudes (mediana a nivel
del mar: 0.211 en 2024, 0.216 en 2025, 0.219 en 2026). Puede ser la pelota o la calibración de
Trackman. Por eso lo **normalizamos por temporada**.

### 2. No hay orden de pitches dentro del juego

No existe ninguna columna de número de pitch, hora ni turno al bat. **No podemos construir
"pitch anterior" ni secuencias**, aunque la convocatoria los sugiere. Lo reportamos como límite
del dataset. El conteo (`Balls`, `Strikes`) captura parte de ese contexto.

### 3. La altitud cambia la forma lo suficiente para confundir una clasificación

Mismo pitcher, mismo tipo de pitch, mediana:

| Pitch | IVB mar → altitud | HB lado brazo mar → altitud |
|---|---|---|
| Four-Seam | 16.9 → 13.1 in | 10.3 → 7.4 in |
| Sinker | 11.4 → 8.6 in | 15.8 → 11.7 in |
| Changeup | 6.7 → 5.1 in | 13.9 → 9.1 in |
| Curveball | −8.2 → −6.8 in | −10.5 → −7.5 in |

Sliders que "parecen sweeper" (≥ 12 in hacia el guante): **12.7 %** a nivel del mar, **3.1 %** en
altitud extrema. No es que en altitud se lancen menos sweepers: es que el mismo sweeper rompe
menos. **Si clasificamos por forma sin ajustar por el aire, en CDMX etiquetaríamos mal los
pitches.**

**Solución propuesta:** clasificar con la **forma equivalente a nivel del mar**. El movimiento por
spin es proporcional a la densidad del aire, así que `movimiento / razón_de_aire` da cómo se
movería ese pitch a nivel del mar. Validación: el % de sweepers debe quedar parecido en todas las
altitudes.

**Cuidado:** la relación no es 1 a 1. El arrastre dice que en altitud extrema hay 0.84 del aire de
nivel del mar, pero el movimiento cae a ~0.77 (sección 5.1 de `00_contexto_y_approach.md`). Dividir
entre `air_ratio` se quedaría corto. Por eso el factor de conversión **no se supone: se estima**
con los ~400 pitchers que lanzan en ambos ambientes (movimiento ∝ `air_ratio`^k, ajustando k). Esa
misma relación es la primera versión del traductor físico (etapa A del modelo).

### 4. La recta de referencia debe ser del mismo juego

Las diferencias de arsenal ("el cambio va 9 mph más lento que la recta") comparan cada pitch con
la recta principal del pitcher. Recta principal: four-seam en 758 pitchers, sinker en 317, cutter
en 42. Ningún pitcher con ≥ 100 pitches carece de recta.

**Por qué del mismo juego:** una recta a nivel del mar y un cambio en CDMX no respiraron el mismo
aire; su diferencia mezclaría arsenal con altitud. En 82.6 % de las salidas el pitcher lanza al
menos 5 rectas, suficiente para una referencia del mismo juego. En el resto usamos su recta en esa
altitud y temporada.

---

## Features propuestos

### A. Ambiente

| Feature | Qué es | Por qué |
|---|---|---|
| `air_ratio` | Arrastre del juego ÷ mediana a nivel del mar de esa temporada | Medida continua del aire; 1.0 = nivel del mar |
| `altitude_category` | Las tres categorías originales | Para reportar y para comparar contra `air_ratio` |

### B. Física del pitch (Stuff+)

| Feature | Qué es |
|---|---|
| `RelSpeed`, `EffectiveVelo` | Velocidad |
| `SpinRate`, `spin_axis_arm` | Spin y su dirección, lado del brazo |
| `InducedVertBreak`, `hb_arm_side` | Movimiento observado |
| `ivb_sea_level`, `hb_sea_level` | Movimiento equivalente a nivel del mar (`movimiento / air_ratio^k`, con k estimado) |
| `Extension`, `RelHeight`, `rel_side_arm` | Punto de release |
| `VertRelAngle`, `horz_rel_angle_arm` | Ángulo de salida de la mano |
| `magnus_dependence` | Movimiento total ÷ (spin / velocidad). Qué tanto del movimiento depende del giro; base del índice Magnus |
| `total_break` | √(IVB² + HB²) |

### C. Arsenal (relación con el repertorio)

| Feature | Qué es |
|---|---|
| `primary_fb_type` | Recta principal del pitcher (four-seam, sinker o cutter) |
| `velo_diff_vs_fb`, `ivb_diff_vs_fb`, `hb_diff_vs_fb` | Diferencias contra la recta principal del **mismo juego** |
| `axis_diff_vs_fb` | Diferencia de eje de spin contra la recta |
| `release_dist_vs_fb` | Distancia del punto de release contra la recta; proxy del efecto túnel |
| `pitch_usage_pct` | % de uso de ese pitch en la temporada del pitcher |
| `arsenal_size` | Número de pitches distintos con ≥ 5 % de uso |

### D. Contexto (solo Location+ y Pitching+)

| Feature | Qué es |
|---|---|
| `Balls`, `Strikes` | Conteo |
| `batter_side`, `platoon_same_side` | Lado del bateador y si coincide con la mano del pitcher |
| `zone` | 9 cuadrantes de la zona + 4 regiones fuera |
| `PlateLocHeight`, `PlateLocSide` | Ubicación exacta |

### E. Clasificación por forma

| Feature | Qué es |
|---|---|
| `pitch_class` | Tipo de pitch reasignado por forma a nivel del mar; resuelve los 2,187 posibles mal etiquetados |
| `slider_shape` | Para sliders: `sweeper` o `gyro`, clave para el índice Magnus |

## Cómo evitamos fuga de información

- Ningún feature usa `PitchCall`, `play_result`, `ExitSpeed` ni otra columna de resultado.
- `pitch_usage_pct` y las referencias del pitcher se calculan con sus propios pitches, que no
  contienen resultados. Para el holdout 2026 se calculan solo con datos de 2026.
- `air_ratio` sale de la trayectoria, no de resultados.

## Salidas de la etapa

- `src/features.py`: construye todos los features.
- `data/processed/features.parquet`: un renglón por pitch.
- `docs/02_features.md`: este plan convertido en reporte, con cifras reales.
- `reportes/etapa_02_features.html`: mapa de movimiento antes y después del ajuste por aire,
  distribución de `air_ratio` y ejemplos de arsenal.

## Preguntas para el equipo

1. **¿El ángulo de llegada (VAA) entra a Stuff+?** Es física pura, pero depende de dónde llega el
   pitch, y Stuff+ no debería usar ubicación. Propuesta: Stuff+ usa el ángulo de salida
   (`VertRelAngle`) y el VAA ajustado por altura queda para Pitching+.
2. **¿El umbral de sweeper es fijo (12 in) o lo sacamos de los datos** con un modelo de mezclas?
   Propuesta: de los datos, usando el 12 in solo como punto de partida.
3. **¿Mínimo de 5 rectas en el juego** para usar referencia del mismo juego? Propuesta: sí.
