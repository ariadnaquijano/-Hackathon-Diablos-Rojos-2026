# 01 · Limpieza de datos

> **Estado:** hecha.
> **Entrada:** `data/raw/stuff_model_df.parquet` (635,002 pitches).
> **Salida:** `data/processed/pitches_limpios.parquet` (635,002 pitches, 107 columnas).
> **Código:** `src/limpieza.py` (reglas) y `src/perfil_calidad_datos.py` (mediciones previas).
> **Cifras:** todas salen de `reportes/etapa_01_resumen.json`, generado por `src/limpieza.py`.
> **Reporte visual:** `reportes/etapa_01_limpieza.html`.

## Resumen en 30 segundos

- **No borramos ninguna fila y no inventamos ningún dato.**
- Cada problema queda marcado en una columna `flag_*`. Un valor mal medido se anula (queda nulo)
  sin tocar el resto del pitch.
- **633,050 pitches (99.69 %) sirven para Stuff+.** Solo 1,952 (0.31 %) quedan fuera, por física
  faltante o imposible, o por ser un tipo de pitch no modelable.
- Entrenamos con 2024–2025 (499,398 pitches) y validamos con 2026 (135,604).

## Principios

1. **Los datos crudos no se tocan.** Toda transformación vive en `src/limpieza.py` y se repite en
   ~4 segundos.
2. **Ni inventar ni borrar.** Cuando un dato falta o está mal, lo marcamos y usamos lo que sí
   sabemos. Borrar filas o rellenar promedios sesgaría justo la comparación de altitud (sección C.1).
3. **Solo es error lo imposible**, no lo raro. Un 105 mph es posible; una extensión de 14 pies no.
4. **La limpieza nunca usa el resultado del pitch** para decidir qué conservar.

## Resultado de cada regla

| Bandera | Qué significa | Pitches | % |
|---|---|---|---|
| `flag_sin_altitud` | Sin categoría de altitud | 3,020 | 0.48 % |
| `flag_sin_fisica` | Falta alguna variable física clave en el dato original | 1,555 | 0.24 % |
| `flag_fisica_imposible` | Algún valor físico fuera de límites imposibles | 340 | 0.05 % |
| `flag_valor_anulado` | Spin o release mal medido para ese pitcher; solo ese valor se anuló | 12,643 | 1.99 % |
| `flag_posible_mal_etiquetado` | Velocidad o movimiento muy distinto a su tipo de pitch; se conserva | 2,187 | 0.34 % |
| `flag_tipo_pitch_raro` | Tipo de pitch sin grupo modelable | 62 | 0.01 % |
| `flag_mano_inferida` | Mano del pitcher faltante, inferida | 1,421 | 0.22 % |
| `flag_lado_bateador_inferido` | Lado del bateador faltante o switch, inferido | 339 | 0.05 % |
| `flag_resultado_corregido` | Banderas de resultado inconsistentes con `PitchCall`, recalculadas | 1,591 | 0.25 % |
| `flag_pitchcall_indefinido` | `PitchCall = Undefined`, no sirve como target | 841 | 0.13 % |
| `flag_outs_invalido` | `Outs = 3` antes del pitch | 8 | 0.00 % |
| `flag_sin_exit_speed` | Bola en juego sin `ExitSpeed` (se conserva) | 7,764 | 1.22 % |
| `flag_exit_speed_sospechosa` | `ExitSpeed` > 125 mph (se conserva) | 32 | 0.01 % |

Un pitch puede tener varias banderas. **`usable_stuff`** es verdadero salvo que el pitch tenga
física faltante, física imposible, tipo de pitch raro o mano del pitcher sin resolver.

---

## A. Tipos de datos

| Cambio | Por qué |
|---|---|
| `EffectiveVelo` de texto a número | Venía como texto; todos los valores eran numéricos, ninguno se perdió |
| 18 banderas de resultado (`is_swing`, `home_run`, …) de decimal a entero 0/1 | Más claro y seguro |
| `Balls`, `Strikes`, `Outs`, `Inning`, `RunsScored`, `OutsOnPlay` a entero | Son conteos |

## B. Identificadores y mano

- **`PitchUID` es único:** 635,002 valores distintos, sin duplicados.
- **Conteo consistente:** `count` siempre coincide con `Balls` y `Strikes`.
- **Mano del pitcher:** 1,421 pitches no la tenían (`NULL` o `Undefined`). Se resolvió con la mano
  habitual de ese pitcher y, si nunca se registró, con el lado del release. Resultado: 1,150
  derechos y 271 zurdos. Todos los pitches quedaron con mano.
- **Lado del bateador:** los switch se asignan al lado contrario de la mano del pitcher y los
  faltantes al lado habitual de ese bateador contra esa mano (339 pitches). **1,163 quedan sin
  resolver** porque no tienen identificador de bateador o el bateador nunca aparece con lado. No
  afecta a Stuff+, que no usa al bateador; en Location+ y Pitching+ se tratan como faltantes.

## C. Faltantes

| Caso | Pitches | Qué hacemos |
|---|---|---|
| Sin `altitude_category` | 3,020 | Sirven para el modelo base; se excluyen de la comparación de altitud |
| Sin física clave en el original | 1,555 | Fuera de Stuff+ (sin forma no hay Stuff+) |
| Bola en juego sin `ExitSpeed` | 7,764 | Se conservan (C.1) |

### C.1 Por qué no imputamos ni eliminamos los batazos sin `ExitSpeed`

Medido con `src/perfil_calidad_datos.py`:

| | Con `ExitSpeed` | Sin `ExitSpeed` |
|---|---|---|
| Bolas en juego | 108,183 | 7,765 |
| Hit rate | 37.2 % | **19.3 %** |
| HR rate | 4.2 % | **0.3 %** |
| Sin `hit_type` | 0 % | 84 % |

- **No faltan al azar.** Son sobre todo contactos débiles que Trackman no rastreó. Además faltan más
  a nivel del mar (7.4 %) que en altitud (5.8 %), y más en changeups (7.7 %) que en rectas (5.8 %).
- **Si eliminamos las filas**, borramos justo el contacto débil: los pitchers se verían peor, más a
  nivel del mar que en altitud. Eso contamina la comparación que es el centro del reto.
- **Si inventamos un valor** (por ejemplo, el promedio), a un toque débil le damos la velocidad de
  un batazo normal. Mismo sesgo, y el modelo cree tener más certeza de la que tiene.
- **Lo que hacemos:** conservar la fila y usar lo que sí sabemos. El resultado (hit, out, jonrón)
  está registrado, así que el xRunValue lo usa. El sub-modelo de calidad de contacto se entrena
  solo con batazos medidos.
- **Prueba de sensibilidad (etapa 5):** repetir con una imputación condicionada al resultado para
  mostrar que las conclusiones no cambian.

*(La diferencia de 7,765 a 7,764 viene de un pitch marcado como bola en juego cuyo `PitchCall` no
era `InPlay`; la regla E lo corrigió.)*

## D. Valores imposibles y atípicos

### D.1 Primera capa: límites físicos imposibles

| Variable | Observado (mín / p0.1 / p99.9 / máx) | Límite | Fuera |
|---|---|---|---|
| `RelSpeed` | 44.7 / 67.3 / 98.9 / 102.5 mph | 40–110 mph | 0 |
| `SpinRate` | 608 / 822 / 3,265 / 3,594 rpm | 0–4,000 rpm | 0 |
| `Extension` | −6.1 / 4.1 / 8.0 / 14.4 ft | 3–9.5 ft | 294 |
| `RelHeight` | 0.3 / 3.1 / 7.1 / 9.6 ft | 1–8.5 ft | 26 |
| `RelSide` | −5.8 / −4.3 / 4.6 / 6.9 ft | ±6 ft | 12 |
| `InducedVertBreak` | −54 / −19 / 24 / 58 in | ±35 in | 7 |
| `HorzBreak` | −39 / −21 / 23 / 55 in | ±35 in | 2 |
| **Total** | | | **340 (0.05 %)** |

- `ExitSpeed` > 125 mph (32 batazos): se marca como sospechoso, pero se conserva.
- `PlateLocHeight = 0` (6,669 pitches) **no es error**: son pitches que tocan el suelo. Se conservan.

### D.2 Segunda capa: absurdo para *ese* pitcher

Comparamos cada pitch con la mediana de su propio pitcher y tipo de pitch (mínimo 30 pitches) y
medimos la distancia en desviaciones robustas (MAD). Marcamos más de 6.

**Qué encontramos al revisar los casos:**

| Variable | Valores | Desviación típica | Diagnóstico | Qué hacemos |
|---|---|---|---|---|
| `SpinRate` | 8,147 | ~1,150 rpm | Falla de lectura de spin de Trackman | Anular el valor |
| `RelSide` | 2,861 | ~1.5 ft | Error de medición del release | Anular el valor |
| `Extension` | 1,401 | ~1.8 ft | Ídem | Anular el valor |
| `RelHeight` | 804 | ~1.1 ft | Ídem | Anular el valor |
| Velocidad / IVB / HB | 2,187 pitches | 8.6 mph, 15–19 in | Pitch bien medido, **mal etiquetado** | Conservar y marcar |

**Por qué anular el valor y no la fila (decisión D-011):** si una recta de 2,300 rpm aparece con
1,150 rpm pero su velocidad y movimiento son normales, lo que falló es la lectura del spin, no el
pitch. Anular solo el spin conserva el resto de la información. LightGBM maneja nulos de forma
nativa. La primera versión, que excluía la fila completa, dejaba fuera 2.5 % de los pitches;
ahora es 0.31 %.

## E. Consistencia de resultados

`PitchCall` es la decisión del umpire registrada por Trackman, así que es la fuente primaria.
Recalculamos `is_swing`, `is_whiff`, `is_contact` e `is_ball_in_play` desde ahí.

| `PitchCall` | Pitches corregidos | Qué estaba mal |
|---|---|---|
| `BallCalled` | 463 | Marcados como swing y contacto en una bola cantada |
| `StrikeSwinging` | 450 | Marcados como contacto en un swing fallado |
| `StrikeCalled` | 403 | Marcados como swing en un strike cantado |
| `HitByPitch` | 230 | Marcados como swing |
| `BallinDirt` | 45 | Marcados como swing |
| **Total** | **1,591** | |

- `PitchCall = Undefined` (841): todos con `play_result = NeutralPlay`; no dicen qué pasó. Se
  conservan, pero sus banderas de resultado quedan nulas y no entran a ningún target.
- `Outs = 3` antes del pitch (8): imposible; se marca.

## F. Tipos de pitch

`AutoPitchType` se conserva y se agrega `pitch_group` (decisión D-010):

| `pitch_group` | Incluye | Pitches | Usables Stuff+ |
|---|---|---|---|
| Four-Seam | Four-Seam | 217,618 | 216,908 |
| Slider | Slider, Sweeper | 139,717 | 139,389 |
| Sinker | Sinker, TwoSeam, OneSeam | 110,899 | 110,477 |
| Changeup | Changeup | 78,925 | 78,698 |
| Curveball | Curveball | 54,024 | 53,909 |
| Cutter | Cutter | 26,468 | 26,419 |
| Splitter | Splitter | 7,289 | 7,250 |
| Other | Other, Knuckleball | 62 | 0 |

## G. Lado del brazo

En zurdos, el movimiento horizontal y el eje de spin salen en espejo respecto a los derechos.
Creamos columnas donde **positivo = hacia el brazo del pitcher**, para que el modelo no tenga que
aprender dos veces lo mismo.

| Recta (mediana) | HB original | `hb_arm_side` | Eje original | `spin_axis_arm` |
|---|---|---|---|---|
| Derechos | +8.4 in | +8.4 in | 211° | 211° |
| Zurdos | −8.3 in | **+8.3 in** | 150° | **210°** |

Columnas nuevas: `hb_arm_side`, `rel_side_arm`, `horz_rel_angle_arm`, `horz_appr_angle_arm`,
`spin_axis_arm`. Las originales se conservan.

## H. Qué puede entrar al modelo (anti-fuga)

| Rol | Columnas | Uso |
|---|---|---|
| Identificador | `PitchUID`, `*_anon_id` | Solo para unir y agrupar, **nunca** como variable |
| Stuff (física) | velocidad, spin, movimiento, release, ángulos, trayectoria, columnas `*_arm` | Stuff+ |
| Ubicación | `PlateLocHeight`, `PlateLocSide`, `in_strike_zone` | Solo Location+ y Pitching+ |
| Contexto | `count`, `Balls`, `Strikes`, `Outs`, `Inning`, `batter_side`, altitud | Location+/Pitching+ y normalización |
| Target | `PitchCall`, `is_*`, `play_result`, `hit_type`, `ExitSpeed`, `Angle`, `Distance`, `RunsScored`, … | **Solo** para construir lo que se predice |
| Calidad | `flag_*`, `usable_stuff`, `split` | Filtrar y auditar, nunca como variable |

**Por altitud:** Extreme 182,223 de 183,267 usables; Medium 154,335 de 154,840; No Altitude
293,475 de 293,875. La limpieza no desbalancea las altitudes.

## I. Temporadas

| `split` | Temporadas | Pitches | Usables Stuff+ |
|---|---|---|---|
| `train` | 2024–2025 | 499,398 | 498,315 |
| `holdout` | 2026 | 135,604 | 134,735 |

2026 solo se usa para validar predicciones (decisión D-006).

## Qué queda para la etapa 2

- Reclasificar pitches por forma (resuelve `flag_posible_mal_etiquetado` y el caso Sweeper/Slider).
- Estimar la densidad del aire por juego desde la trayectoria.
- Construir features de arsenal (diferencias contra la recta principal).
