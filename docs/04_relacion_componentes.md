# Etapa 4 · Cómo Stuff+ y Location+ forman Pitching+

> **Estado:** análisis terminado; la propuesta del final está pendiente de validar por el equipo.
> **Evidencia:** `src/relacion_componentes.py`; cifras en `reportes/etapa_04_relacion_componentes.json`.
> **Datos:** solo 2024 y 2025 (D-025); 2026 no se tocó. Las predicciones de cada pitcher vienen de
> modelos que no lo vieron (5 pliegues por pitcher). Los modelos son la primera versión de la
> exploración (`docs/04_plan_modelo.md`).

## Qué preguntamos

Las preguntas se fijaron antes de correr el análisis:

1. ¿Stuff+ y Location+ miden habilidades distintas?
2. ¿Cuánto del Pitching+ de un pitcher se explica con su Stuff+ y su Location+, y con qué peso?
3. ¿Pitching+ aporta algo por pitch que no dé la suma de los dos?
4. ¿Cuál se repite más y cuál predice el año siguiente?

Los valores son carreras por 100 pitches, centrados por temporada. Muestra: 320 pitchers con al menos
300 pitches en la temporada, y 146 con al menos 300 pitches en ambas. Todos los intervalos son de
95 % y remuestrean pitchers completos (1,000 repeticiones, semilla 2026).

## Resultados

### 1. Stuff+ y Location+ son casi independientes

| Temporada | r entre Stuff+ y Location+ | IC 95 % |
|---|---|---|
| 2024 | −0.07 | −0.19 a +0.04 |
| 2025 | −0.17 | −0.29 a −0.06 |

Saber el Stuff+ de un pitcher casi no dice nada de su Location+. En 2025 aparece un intercambio leve:
los pitchers con peor forma tienden a ubicar un poco mejor. En 2024 el intervalo toca cero, así que
ese intercambio no es firme.

### 2. Pitching+ es, en un 80 %, la suma de Stuff+ y Location+

Regresión del Pitching+ de cada pitcher sobre su Stuff+ y su Location+, en unidades estándar:

| Temporada | Peso de Stuff+ | Peso de Location+ | R² |
|---|---|---|---|
| 2024 | 0.62 (0.57 a 0.68) | 0.69 (0.64 a 0.74) | 0.80 (0.75 a 0.84) |
| 2025 | 0.60 (0.56 a 0.66) | 0.77 (0.72 a 0.82) | 0.80 (0.75 a 0.84) |

- Ocho de cada diez puntos de diferencia en Pitching+ entre pitchers vienen de sumar sus dos
  componentes.
- Location+ pesa un poco más que Stuff+. También varía más entre pitchers: 0.28–0.30 carreras por 100
  contra 0.18.

### 3. Por pitch, la suma de los dos predice igual que Pitching+

Error por pitch en 2025 contra la media. La suma se ajustó con 2024 (pesos 0.73 para Stuff+ y 1.09
para Location+).

| Predictor | Mejora contra la media | IC 95 % | Diferencia contra la suma |
|---|---|---|---|
| Stuff+ solo | +0.15 % | 0.12 a 0.18 | −5.24 a −4.81 |
| Location+ solo | +5.11 % | 4.90 a 5.32 | −0.09 a −0.05 |
| **Suma de Stuff+ y Location+** | **+5.18 %** | 4.95 a 5.40 | — |
| Pitching+ (un solo modelo) | +5.14 % | 4.93 a 5.34 | −0.11 a +0.01 (empate) |

- La suma le gana a Location+ sola, con un intervalo que no toca cero: el Stuff+ sí aporta encima de
  la ubicación.
- El modelo único de Pitching+ no le gana a la suma, aunque además ve las interacciones forma ×
  ubicación y la secuencia. Con este target, esas piezas no aportan nada que se pueda medir.

### 4. Cuánto sigue cada uno al xRV real en la misma temporada

| Temporada | Stuff+ | Location+ | Pitching+ |
|---|---|---|---|
| 2024 | 0.25 (0.13 a 0.36) | 0.30 (0.21 a 0.39) | 0.48 (0.39 a 0.56) |
| 2025 | 0.35 (0.24 a 0.46) | 0.21 (0.11 a 0.31) | 0.50 (0.40 a 0.58) |

Cada componente explica una parte distinta del resultado. Por eso la combinación sigue mejor al xRV
real que cualquiera de los dos solo. Estos intervalos no son pareados, así que la ventaja de
Pitching+ no está probada; solo se repite en las dos temporadas.

### 5. Estabilidad: el resultado real casi no se repite, los componentes sí

| Valor | Mitades de la temporada (2024 / 2025) | De 2024 a 2025 (146 pitchers) |
|---|---|---|
| xRV real | 0.35 / 0.26 | 0.18 (−0.01 a +0.35) |
| Stuff+ | 0.99 / 0.99 | 0.85 (0.79 a 0.89) |
| Location+ | 0.77 / 0.82 | 0.68 (0.58 a 0.77) |
| Pitching+ | 0.85 / 0.87 | 0.65 (0.55 a 0.73) |

La confiabilidad de las mitades usa pitches pares contra impares, con Spearman-Brown.

**Cuidado:** que el Stuff+ casi no cambie es en parte por construcción, porque la forma de los pitches
de un pitcher cambia poco. Que sea estable no significa que prediga el resultado; eso se mide en la
siguiente tabla.

### 6. A futuro: el valor de 2024 contra el xRV real de 2025 (146 pitchers)

| Predictor de 2024 | r con el xRV real de 2025 | IC 95 % | Diferencia contra el xRV de 2024 |
|---|---|---|---|
| **Pitching+** | **0.22** | 0.05 a 0.38 | −0.15 a +0.24 |
| xRV real de 2024 (la historia) | 0.18 | −0.01 a +0.35 | — |
| Stuff+ | 0.14 | −0.03 a +0.31 | −0.30 a +0.21 |
| Location+ | 0.04 | −0.10 a +0.18 | −0.30 a +0.03 |

- Pitching+ queda arriba en la estimación puntual, y es el único con un intervalo que no toca cero.
  Pero la diferencia contra la historia no está probada.
- Con 2024–2025 como prueba de 2026, la historia encogida le ganó a Pitching+ (`docs/04_plan_modelo.md`,
  sección 4). Las dos pruebas no coinciden: con 146 pitchers no se puede afirmar que uno prediga mejor
  que el otro.

### 7. El conteo en Location+ es contexto, no crédito

Chequeo con `src/location_sin_conteo.py` (cifras en `reportes/etapa_04_location_sin_conteo.json`).
Se entrenó un Location+ sin bolas ni strikes, igual que el original (200 árboles, 5 pliegues por
pitcher, solo 2024–2025).

**El conteo solo no le da crédito a ningún pitcher.** El modelo base que predice con el conteo
(`media_conteo`) varía 0.011 carreras por 100 entre pitchers. Location+ varía 0.28. Estar en conteos
buenos no infla el Location+ de nadie. Era de esperarse, porque el xRV ya se mide contra el valor del
conteo en que ocurre el pitch.

**Por pitch, el conteo sí importa como contexto.** Una misma ubicación vale distinto según el conteo:
un pitch fuera de la zona es buen pitch en 0-2 y mal pitch en 3-0.

| Predictor, por pitch en 2025 | Mejora contra la media | IC 95 % | Diferencia contra Location+ |
|---|---|---|---|
| Solo el conteo | +0.004 % | −0.005 a +0.013 | −5.31 a −4.90 |
| Location+ sin conteo | +3.47 % | 3.31 a 3.63 | −1.74 a −1.54 |
| Location+ con conteo | +5.11 % | 4.90 a 5.32 | — |

**Por pitcher, las dos versiones casi no se distinguen:**

| Medida | Con conteo | Sin conteo | Diferencia (IC 95 %) |
|---|---|---|---|
| r entre las dos versiones (2024 / 2025) | 0.95 / 0.95 | | |
| r con el xRV real, 2024 | 0.30 | 0.27 | −0.07 a +0.01 |
| r con el xRV real, 2025 | 0.21 | 0.20 | −0.05 a +0.02 |
| Confiabilidad entre mitades (2024 / 2025) | 0.77 / 0.82 | 0.78 / 0.81 | se traslapan |
| Repetición de 2024 a 2025 | 0.68 | 0.66 | −0.06 a +0.04 |
| Predice el xRV real de 2025 | 0.04 | 0.03 | −0.06 a +0.03 |
| R² de Pitching+ con Stuff+ y esta versión, 2024 | 0.80 | 0.76 | −0.06 a −0.02 |
| R² de Pitching+ con Stuff+ y esta versión, 2025 | 0.80 | 0.74 | −0.08 a −0.03 |

Conclusión: **Location+ se queda con el conteo.**

- Predice mejor cada pitch (+1.6 puntos, con un intervalo lejos de cero).
- Ordena a los pitchers casi igual que la versión sin conteo.
- Explica mejor el Pitching+.

Lo que mide es "ubicar bien para el conteo en que estás", que es lo que un coach entiende por
comando.

## Qué significa

1. **La relación que el equipo buscaba sí está en los datos.** Pitching+ ≈ 0.6 × Stuff+ + 0.7 ×
   Location+, en unidades estándar, y explica el 80 % de las diferencias entre pitchers. Las dos
   piezas son casi independientes, así que cada una aporta información propia.
2. **Por pitch, armar Pitching+ como suma pesada no pierde nada** frente a un modelo único (empate,
   −0.11 a +0.01).
3. **El resultado real es muy ruidoso** (se repite 0.18 de un año a otro). Ahí está el argumento para
   usar Stuff+, Location+ y Pitching+: son mucho más estables que el resultado. Lo que todavía no
   podemos afirmar es que predigan el año siguiente mejor que la historia del pitcher.

## Propuesta para validar

**Construir Pitching+ como la suma pesada de Stuff+ y Location+**, en lugar de un tercer modelo
independiente:

- Los pesos se ajustan con 2024 y se revisan con 2025 (D-025).
- **A favor:**
  - Predice igual por pitch.
  - Es coherente por construcción: un Pitching+ alto se explica siempre como "tanto de forma, tanto de
    ubicación".
  - Para el cuerpo técnico es más fácil de leer: "su Pitching+ es 108 porque su Stuff+ es 115 y su
    Location+ es 101".
- **En contra:** no ve la secuencia. En este análisis la secuencia no aportó nada medible, pero podría
  aportar con un target menos ruidoso.

## Límites

- **Location+ incluye el conteo como contexto.** La sección 7 muestra que eso no le da crédito a un
  pitcher por estar en conteos buenos.
- **Los pliegues no son perfectamente independientes.** Las predicciones de 2024 vienen de modelos que
  sí vieron 2025 de otros pitchers. No hay fuga del mismo pitcher, pero sí del ambiente de la liga.
- **El Stuff+ es la primera versión.** No le gana a la regresión lineal por pitcher (plan, sección
  3), y estos pesos pueden cambiar cuando mejore.
- **La prueba a futuro tiene poca potencia.** Con 146 pitchers solo se distinguen diferencias grandes.
