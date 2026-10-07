# H4 · ¿El spin rate por sí solo basta para predecir la calidad de un pitch?

> **Responsable:** Alexis.
> **Hipótesis de la convocatoria:** "El spin rate por sí solo resulta insuficiente como predictor de
> Stuff+. La clave es cuánto se mueve el lanzamiento, más que cuánto gira. En altitud, un spin rate
> alto puede traducirse en movimiento real menor y un Stuff+ más bajo de lo esperado."
> **Datos:** dataset original, como acordó el equipo. Filtros mínimos: solo swings con spin,
> velocidad y movimiento medidos (280,084 swings). El movimiento horizontal se expresa hacia el
> lado del brazo para juntar zurdos y derechos.
> **Código:** `src/hipotesis_h4.py`. **Cifras:** `reportes/h4_resumen.json`.
> **Reporte visual:** `reportes/h4_spin_rate.html`.

## Veredicto

**H4 se sostiene, con un matiz.** El spin rate solo casi no predice nada. Con el mismo spin, el
movimiento cambia el resultado de forma clara, y la altura le quita movimiento sin tocar el spin.
La excepción es el cambio de velocidad: ahí lo que manda es la velocidad, no el movimiento.

## Cómo lo medimos

El plan se fijó antes de correr el análisis:

- **Qué se predice:** si un swing termina en swing fallido (whiff). Es la parte del resultado que
  más depende del pitch y menos de la ubicación. Todavía no tenemos Stuff+; el whiff es su
  componente más directo.
- **Por tipo de pitch:** recta de cuatro costuras, sinker, slider, curva y cambio.
- **Cinco modelos** (gradient boosting) con distintas variables: solo spin; solo velocidad; solo
  movimiento (IVB y HB); velocidad + movimiento; velocidad + movimiento + spin.
- **Validación:** entrenados con 2024–2025, evaluados en 2026, que no vieron.
- **Métricas:** AUC (0.5 = adivinar al azar; 1 = perfecto) y mejora del log loss contra predecir
  siempre la tasa base. Las diferencias llevan intervalo de 95 % remuestreando pitchers completos,
  porque los swings de un mismo pitcher no son independientes.

## Resultado 1 · El spin solo casi no predice

AUC en 2026:

| Pitch | Swings de prueba | Solo spin | Solo velocidad | Solo movimiento | Velocidad + movimiento | + spin |
|---|---|---|---|---|---|---|
| Recta 4 costuras | 19,935 | 0.546 | 0.551 | 0.569 | 0.587 | 0.590 |
| Sinker | 11,336 | 0.515 | 0.518 | 0.533 | 0.543 | 0.550 |
| Slider | 14,575 | 0.521 | 0.512 | 0.552 | 0.559 | 0.558 |
| Curva | 4,880 | 0.506 | 0.540 | 0.525 | 0.568 | 0.570 |
| Cambio | 8,280 | 0.525 | 0.542 | 0.508 | 0.550 | 0.561 |

| Comparación | Recta | Sinker | Slider | Curva | Cambio |
|---|---|---|---|---|---|
| Movimiento − spin (AUC) | **+0.022** [0.004, 0.040] | +0.018 [−0.009, 0.038] | **+0.031** [0.015, 0.048] | +0.019 [−0.007, 0.043] | −0.017 [−0.044, 0.007] |
| Lo que agrega el spin a velocidad + movimiento | +0.003 [−0.001, 0.007] | +0.008 [−0.002, 0.018] | −0.001 [−0.004, 0.002] | +0.002 [−0.002, 0.007] | **+0.011** [0.000, 0.019] |

**Lectura:**
- El spin solo apenas supera a adivinar al azar (AUC 0.51–0.55). Mejora el log loss menos de
  0.5 % sobre la tasa base.
- En la recta y la slider, el movimiento le gana al spin con un intervalo que no toca el cero.
  En el sinker y la curva va en la misma dirección, pero con menos certeza.
- Si ya sabes la velocidad y el movimiento, el spin no agrega nada en recta, sinker, slider ni curva.
- **El cambio es la excepción.** El movimiento solo no le gana al spin, y lo que más predice es la
  velocidad. Tiene sentido: el cambio engaña por diferencia de velocidad. El spin agrega un poco,
  quizá porque un cambio de bajo spin indica un agarre que "mata" la pelota.

**Por qué todos los AUC son bajos:** un swing individual depende de la ubicación, el conteo y el
bateador, que aquí no entran a propósito. La pregunta de H4 es *cuál variable física predice más*,
no cuánto predice la física sola.

## Resultado 2 · Mismo spin, distinto movimiento, distinto resultado

Rectas de cuatro costuras con spin entre 2,250 y 2,400 rpm, en tercios según su IVB:

| Tercio de IVB | Spin mediano | Velocidad mediana | IVB mediano | Whiff por swing | Swings |
|---|---|---|---|---|---|
| Bajo | 2,324 rpm | 92.2 mph | 12.3 in | 15.7 % | 12,940 |
| Medio | 2,328 rpm | 92.1 mph | 15.3 in | 18.2 % | 12,940 |
| Alto | 2,327 rpm | 91.6 mph | 18.8 in | **24.2 %** | 12,939 |

Con el mismo spin, la recta que más sube saca **8.5 puntos más de whiff** (IC 95 % 7.3 a 9.7). La
velocidad no lo explica: las rectas de más movimiento son incluso un poco más lentas.

## Resultado 3 · La altura quita movimiento sin tocar el spin

Las mismas rectas, por altitud:

| Altitud | Spin mediano | IVB mediano | Whiff por swing | Swings |
|---|---|---|---|---|
| Nivel del mar | 2,326 rpm | 17.4 in | 20.7 % | 18,378 |
| Altitud media | 2,327 rpm | 14.4 in | 18.2 % | 9,702 |
| Altitud extrema | 2,326 rpm | 13.2 in | 18.0 % | 10,596 |

El spin es idéntico; la recta en altitud extrema sube 4.2 in menos y saca **2.8 puntos menos de
whiff** (IC 95 % 1.6 a 3.9). Es exactamente lo que plantea H4: en altura, el mismo spin se traduce
en menos movimiento y en un pitch menos efectivo.

**Prueba de transferencia:** entrenamos con juegos a nivel del mar y predijimos el whiff en altitud
extrema.

| Pitch | Whiff real en altitud | Predicho con solo spin | Predicho con solo movimiento |
|---|---|---|---|
| Recta 4 costuras | 18.1 % | 21.2 % (+3.1) | 16.3 % (−1.8) |
| Sinker | 13.6 % | 15.2 % (+1.6) | 13.9 % (+0.3) |
| Slider | 31.0 % | 32.7 % (+1.7) | 32.4 % (+1.4) |
| Curva | 32.8 % | 33.0 % (+0.3) | 31.4 % (−1.4) |
| Cambio | 27.9 % | 29.3 % (+1.4) | 29.4 % (+1.5) |

El modelo de spin **sobreestima el whiff en altura en los cinco tipos**: como el spin no cambia,
predice lo mismo que a nivel del mar. El de movimiento se acerca más en recta, sinker y slider. En
la curva le va peor y en el cambio empatan, coherente con el resultado 1. En la recta se pasa del
otro lado (−1.8): el movimiento no es lo único que cambia en altura.

## Qué significa para el proyecto

- Confirma la decisión del modelo: la física entra como **forma del pitch** (movimiento a nivel del
  mar), no como spin suelto. El spin sigue como variable, porque en el cambio agrega algo.
- El **índice de dependencia del Magnus** (movimiento por unidad de spin) es la forma operativa de
  H4: mide cuánto movimiento saca un pitcher de su spin.
- Para el cuerpo técnico: un pitcher con mucho spin no es automáticamente bueno, y menos en la CDMX.
  Hay que ver cuánto se mueve su pitch.

## Límites

- El whiff es solo un componente de Stuff+. Cuando tengamos las carreras esperadas, repetimos la
  comparación con ese target.
- Son 10 comparaciones con intervalo; tomamos como sólidas solo las que quedan lejos de cero (recta
  y slider en el resultado 1, y los resultados 2 y 3).
- Las rectas de más ride también pueden tener otras ventajas (ángulo de llegada, extensión). El
  resultado 2 controla spin y velocidad, no todo.
