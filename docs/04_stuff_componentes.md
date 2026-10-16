# Etapa 4 · Stuff+ por componentes (camino 1)

> **Estado:** probado; según la regla fijada, **no gana**. Pendiente de discutir con el equipo.
> **Evidencia:** `src/stuff_componentes.py`; cifras en `reportes/etapa_04_stuff_componentes.json`.
> **Datos:** entrenado con 2024 y evaluado en 2025 (D-025); 2026 no se tocó.

## Qué probamos

En lugar de predecir el valor final del pitch, que es casi todo ruido, se predice cada paso por
separado. Los modelos usan solo la forma del pitch a nivel del mar, con las mismas variables del Stuff+
de la exploración:

| Componente | Se ajusta con | Mejora contra la tasa base en 2025 |
|---|---|---|
| P(whiff \| swing) | 118,905 swings | **−4.8 % de log loss** |
| P(strike cantado \| no swing) | 137,239 tomas | −1.9 % |
| P(foul \| contacto) | 90,465 contactos | −1.2 % |
| P(swing) | 256,144 pitches | −0.6 % |
| Valor del batazo | 46,792 bolas en juego | −0.1 % de error |

Después se combinan con el valor promedio en carreras de cada desenlace en 2024 (fórmula en el
script).

**Corrección de diseño, declarada:** la primera corrida combinaba las probabilidades con el valor del
desenlace en el conteo de cada pitch. Las probabilidades no ven el conteo, así que la combinación
mezclaba información que el modelo no tenía, y quedó peor que la media por pitch (−0.36 %). Se
corrigió a valores promedio de todos los conteos antes de mirar los resultados por pitcher.

## Resultados

### Por pitch, en 2025

| Modelo | Mejora contra la media | IC 95 % | Diferencia contra la lineal |
|---|---|---|---|
| Media por tipo y mano | +0.01 % | −0.004 a +0.03 | −0.10 a −0.05 |
| Regresión lineal por tipo (base) | +0.09 % | 0.06 a 0.12 | — |
| Stuff+ directo (gradient boosting) | +0.13 % | 0.10 a 0.15 | +0.01 a +0.06 |
| **Stuff+ por componentes** | **+0.14 %** | 0.10 a 0.17 | **+0.02 a +0.08** |

Por pitch, los componentes le ganan a la lineal con un intervalo fuera de cero.

### Por pitcher, en 2025: la regla fijada (320 pitchers con 300+ pitches)

| Modelo | r con su xRV real | IC 95 % | Error por 100 | Diferencia de error contra la lineal |
|---|---|---|---|---|
| **Regresión lineal por tipo (base)** | **0.34** | 0.24 a 0.45 | **0.455** | — |
| Stuff+ directo | 0.31 | 0.21 a 0.42 | 0.469 | −0.007 a +0.034 |
| Stuff+ por componentes | 0.28 | 0.18 a 0.38 | 0.474 | −0.006 a +0.046 |
| Media por tipo y mano | 0.04 | −0.08 a +0.16 | 0.517 | +0.032 a +0.094 |

**Según la regla, gana la lineal:** tiene el menor error por pitcher, y ningún camino le gana con un
intervalo fuera de cero.

### Chequeo posterior: la lineal base ve la altitud

Este chequeo se agregó después de ver el resultado, y se reporta como tal.

La lineal base usa el **movimiento observado** (IVB y HB tal como se midieron), que trae el efecto del
aire. Los Stuff+ usan la **forma a nivel del mar**, que por diseño lo quita (D-001). Como el xRV real
de un pitcher sí empeora en altura, una variable que "sabe" en qué estadio se lanzó tiene ventaja para
seguirlo. Para comparar con la misma información, se corrió la misma lineal con la forma a nivel del
mar:

| Modelo, solo forma a nivel del mar | r | IC 95 % | Error por 100 | Diferencia de error contra la lineal a nivel del mar |
|---|---|---|---|---|
| Regresión lineal por tipo | 0.27 | 0.17 a 0.38 | 0.476 | — |
| Stuff+ directo | 0.31 | 0.21 a 0.42 | 0.469 | −0.025 a +0.010 (empate) |
| Stuff+ por componentes | 0.28 | 0.18 a 0.38 | 0.474 | −0.026 a +0.022 (empate) |

- La lineal con movimiento observado le gana a la misma lineal a nivel del mar: error 0.455 contra
  0.476, diferencia +0.006 a +0.036 (r −0.12 a −0.02). **La ventaja de la base viene de ver la
  altitud**, no de un mejor modelo de la forma.
- Con la misma información, los tres modelos empatan.

## Qué significa

1. **Por componentes no gana; se reporta así.** La lineal se queda como referencia de Stuff+, según
   la regla del plan.
2. **El veredicto anterior era injusto contra Stuff+.** "Stuff+ no le gana a la lineal" incluye
   también la exploración con 2026 (`docs/04_plan_modelo.md`, sección 3), donde la base es la misma. Se
   debe leer así: la lineal gana porque ve el estadio. Para comparar pitchers sin castigarlos por su
   parque (el objetivo del reto), la base justa es la lineal a nivel del mar, y contra ella hay empate.
3. **El whiff es el componente con más señal** (−4.8 % de log loss, el único que se aleja claramente
   de la tasa base). Es candidato a métrica propia del arsenal ("Whiff+"), fácil de explicar a un
   coach. Esto es una hipótesis: falta medir su estabilidad y si predice.

## Para decidir con el equipo

- **¿Cambiamos la base de Stuff+ a la lineal a nivel del mar?** A favor: compara con la misma
  información que D-001 exige. En contra: el cambio se propone después de ver el resultado. Si se
  acepta, debe quedar escrito como decisión nueva, con esta razón, y no reescribir la regla vieja.
- **Con empate, ¿qué Stuff+ usamos?** La lineal a nivel del mar es la más simple y transparente. Los
  componentes dan más para explicar (whiff, strike cantado, contacto) y ganan por pitch. Ninguno gana
  por pitcher.
- **Siguiente prueba posible:** el camino 3 del plan, combinar Stuff+ con la historia del pitcher.

## Límites

- Los pitchers de 2025 también están en el entrenamiento de 2024, porque es lo que tendría el club. Un
  modelo flexible podría memorizar algo del pitcher; con hojas de 1,000 pitches el riesgo es bajo.
- 320 pitchers: solo se ven diferencias grandes por pitcher.
- Los valores de cada desenlace son promedios de la liga sobre todos los conteos. No distinguen, por
  ejemplo, que un whiff en 0-2 vale más que en 0-0.
