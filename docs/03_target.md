# Etapa 3 · El target de carreras esperadas y los modelos base

> **Plan validado:** `docs/03_plan_target.md`.
> **Código:** `src/target.py` (target) y `src/modelos_base.py` (modelos base).
> **Cifras:** `reportes/etapa_03_resumen.json` y `reportes/modelos_base.json`.
> **Reporte visual:** `reportes/etapa_03_target.html`.
> **Salida:** `data/processed/dataset_modelo.parquet` (features + target; no se sube al repo).

## En una frase

Cada pitch tiene ahora un valor en carreras para el rival (**xRV**), en dos versiones: neutral, para
comparar pitchers, y local, para ver lo que vale en su altitud. El modelo simple que cualquier equipo
puede llevar ya predice a los pitchers de 2026 mejor que sus propios resultados pasados; esa es la
barra que debe superar el modelo de la etapa 4.

## 1. Valor de cada desenlace

Regresión de las carreras de cada media entrada sobre sus desenlaces (plan, decisión 1). Se usan las
26,536 medias entradas completas de 2024–2025 (empiezan con 0 outs y terminan con 3).

| Desenlace | Liga | Nivel del mar | Altitud media | Altitud extrema |
|---|---|---|---|---|
| Sencillo | 0.518 | 0.478 | 0.537 | 0.549 |
| Doble | 0.831 | 0.772 | 0.839 | 0.885 |
| Triple | 1.134 | 1.017 | 1.113 | 1.214 |
| Jonrón | 1.432 | 1.430 | 1.431 | 1.423 |
| Base por bolas | 0.389 | 0.343 | 0.411 | 0.448 |
| Golpeado | 0.407 | 0.381 | 0.484 | 0.374 |
| Ponche | −0.117 | −0.102 | −0.122 | −0.136 |
| Out en juego | −0.113 | −0.095 | −0.121 | −0.133 |
| Carreras por media entrada | 0.657 | 0.531 | 0.739 | 0.808 |

- En altura todo vale más salvo el jonrón, que siempre vale lo mismo: las carreras que trae. Con más
  corredores en base y más batazos, un embasado anota más seguido y un out cuesta más oportunidades.
- El golpeado es el más ruidoso (pocos casos): 0.48 en altitud media y 0.37 en extrema no es una
  diferencia que interpretemos.
- **Error, sacrificio y bola ocupada se valúan como out** (−0.113 en la liga). En la regresión salen
  con valores sesgados (error +0.60, sacrificio +0.19) porque solo ocurren con corredores en base.

## 2. Valor de cada conteo

Promedio del desenlace final de los turnos de 2024–2025 que pasaron por el conteo.

| Bolas \ Strikes | Liga 0 | Liga 1 | Liga 2 | Extrema 0 | Extrema 1 | Extrema 2 |
|---|---|---|---|---|---|---|
| 0 | 0.146 | 0.107 | 0.053 | 0.168 | 0.126 | 0.067 |
| 1 | 0.179 | 0.133 | 0.073 | 0.204 | 0.152 | 0.089 |
| 2 | 0.227 | 0.174 | 0.107 | 0.265 | 0.208 | 0.128 |
| 3 | 0.307 | 0.258 | 0.185 | 0.351 | 0.297 | 0.219 |

Lectura para el cuerpo técnico: en el Harp Helú un strike en 0-0 le quita 0.043 carreras al rival
(0.034 a nivel del mar), y la cuarta bola en 3-2 le regala 0.23 (0.18 a nivel del mar). **Ponerse
adelante vale más en la CDMX.**

## 3. Valor de cada pitch

- **Pitch que no termina el turno:** conteo después − conteo antes. Foul con dos strikes vale 0.
- **Pitch que termina el turno:** desenlace − conteo antes. Si es bola en juego, el desenlace es su
  valor *esperado* (sección 4).
- El conteo "después" sale del resultado del pitch, no de la fila siguiente.

**Chequeos:**
- El fin de turno deducido del pitch (ponche o base por bolas) coincide con el registrado en 46,434
  de 46,445 casos (11 distintos).
- De 163,493 turnos que terminan en un desenlace, **162,106 suman exactamente** desenlace − conteo
  inicial. Otros 1,382 no suman porque el conteo registrado salta (falta un pitch): cada pitch se
  valúa con su propio conteo y el salto no se le cobra a nadie. Quedan 5 sin explicación.

## 4. Valor esperado de la bola en juego

Modelo de gradient boosting que da el valor típico de un batazo según su contacto.

- **Predicciones cruzadas:** en 2024–2025 cada batazo recibe la predicción de un modelo que no lo vio
  (5 pliegues agrupando por juego). En 2026, la de un modelo entrenado solo con 2024–2025. Así el
  resultado real de un batazo no se filtra a su propio valor esperado.
- **Neutral:** entrenado solo con batazos a nivel del mar. **Local:** entrenado con todos, con la
  altitud como variable.

| Variables | R² en 2026, neutral | R² en 2026, local |
|---|---|---|
| Velocidad de salida + ángulo | 0.347 | 0.380 |
| + dirección (hacia donde jala el bateador) | 0.473 | 0.510 |

**Elección de variables (regla fijada en el plan):** gana la versión cuyo xRV de 2024–2025 por
pitcher prediga mejor su valor real de 2026. Con 114 pitchers con al menos 300 pitches en cada
periodo y valores centrados por temporada (sección 6):

| Predictor (2024–2025) | r con el valor real de 2026 | Confiabilidad entre mitades |
|---|---|---|
| xRV con velocidad + ángulo | 0.250 | 0.250 |
| **xRV con velocidad + ángulo + dirección (elegido)** | **0.263** | 0.131 |
| Valor real (sin quitar la suerte) | 0.199 | 0.113 |

- Por la regla, gana la dirección, pero **es casi un empate**: la diferencia es de +0.012 con IC 95 %
  de −0.044 a +0.076. La versión sin dirección es el doble de estable entre mitades. Lo dejamos
  anotado (D-023) para la prueba de sensibilidad de la etapa 5.
- **¿Sirve quitar la suerte?** El xRV predice el futuro mejor que el valor real (0.263 contra
  0.199), pero el IC de la diferencia (−0.054 a +0.172) toca el cero. Apunta a que sí, sin certeza
  con 114 pitchers.
- **Bolas sin velocidad de salida (7,765):** toman el valor real promedio de su grupo a nivel del
  mar en 2024–2025: los toques, 0.017; las demás, −0.001. No se borran ni se les inventa velocidad.

## 5. Cobertura

| | Pitches |
|---|---|
| Total | 635,002 |
| Sin target (`PitchCall` indefinido) | 841 |
| Con target neutral pero sin local (juego sin altitud registrada) | 2,908 |

El xRV neutral promedia −0.003 carreras por pitch, con desviación de 0.145. Casi todo es ruido de
pitch a pitch; por eso Stuff+ se juzga por pitcher.

## 6. Modelos base

Entrenados con 2024–2025, predicen el xRV neutral de 2026 (decisión D-020).

### Por pitch

| Modelo base | Mejora del error contra la media | IC 95 % |
|---|---|---|
| Media de la liga | 0 | — |
| Media por conteo | +0.018 % | 0.005 a 0.028 |
| Media por tipo de pitch y mano | +0.001 % | −0.023 a 0.019 |
| Regresión lineal por tipo (velocidad, IVB, HB, extensión) | **+0.107 %** | 0.067 a 0.151 |

Las mejoras son mínimas, y es lo esperado: el resultado de un solo pitch es casi todo azar. La media
por conteo no aporta casi nada porque **el target ya descuenta el conteo** (es la diferencia de valor
entre conteos), que es lo que buscábamos.

### Por pitcher (lo que usa el club)

Para cada pitcher con al menos 300 pitches en 2024–2025 y en 2026 (114), se compara su xRV real de
2026 con lo que cada modelo predice para sus pitches de 2026. Todo en carreras por 100 pitches sobre
el promedio de la temporada.

**Por qué centrar por temporada:** el ambiente de carreras cambia de un año a otro: 10.4 carreras por
juego en 2024, 12.1 en 2025 y 11.1 en 2026. Stuff+ se define contra el promedio de su temporada
(100 = promedio de ese año). Sin centrar, ganaría quien adivine el nivel de la liga, no quien ordene
bien a los pitchers.

| Modelo | r con el xRV real de 2026 | IC 95 % | Error cuadrático por 100 |
|---|---|---|---|
| Media de la liga | — | — | 0.770 |
| Media por conteo | −0.296 | −0.460 a −0.113 | 0.776 |
| Media por tipo de pitch y mano | 0.144 | −0.087 a 0.352 | 0.758 |
| **Regresión lineal por tipo** | **0.454** | 0.293 a 0.596 | **0.649** |
| Persistencia: su xRV de 2024–2025 | 0.383 | 0.221 a 0.532 | 0.761 |
| Persistencia encogida hacia la media | 0.383 | 0.221 a 0.532 | 0.707 |

- **El modelo físico simple ya le gana a la historia del pitcher** en el valor puntual (r 0.45
  contra 0.38; error 0.649 contra 0.707). Los intervalos se enciman, así que no lo presentamos como
  diferencia probada.
- **Además sirve donde la historia no existe:** 64 de los 178 pitchers con muestra en 2026 no tenían
  300 pitches en 2024–2025. Para ellos solo hay modelo físico.
- La persistencia encogida usa la pendiente de 2024 → 2025 (0.19, con 146 pitchers): de un año a otro
  se repite menos de una quinta parte de la diferencia de un pitcher contra la liga.
- La media por conteo sale negativa: los pitchers que viven en conteos malos reciben predicciones
  "buenas", porque el siguiente pitch en 3-0 suele ser strike. No mide al pitcher.

### La barra para la etapa 4

El modelo de Stuff+ debe superar, con intervalo que no toque cero, a:

1. **Por pitch:** la regresión lineal por tipo (+0.107 % de mejora contra la media).
2. **Por pitcher:** la regresión lineal por tipo (r 0.454, error 0.649) y la persistencia encogida
   (error 0.707).
3. **El modelo con `altitude_category` como variable**, con el mismo algoritmo (alternativa de D-001).

Las predicciones de los modelos base quedan en `data/processed/predicciones_base.parquet` para
compararlas pitch a pitch.

## Límites

- Sin corredores en base, los valores de desenlace son promedios sobre todas las situaciones.
- Robos, wild pitches y pickoffs no se le cargan a ningún pitch.
- Las pruebas por pitcher tienen 114 pitchers: suficientes para ver diferencias grandes, no pequeñas.
  2026 es una temporada parcial (135 mil pitches contra 250 mil de un año completo).
- La elección de la dirección en el contacto fue casi un empate; se revisa en la etapa 5.
