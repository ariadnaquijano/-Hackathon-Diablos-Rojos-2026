# Etapa 6 · Ficha del pitcher

> **Estado:** primera versión, revisada en el navegador.
> **Evidencia:** `src/ficha.py` y `src/plantillas/ficha_pitcher.html` generan
> `data/fichas/fichas_pitchers.html`. La página trae identificadores y datos por pitcher, así que **no
> se sube al repo** (D-004). El riesgo de altitud se probó en `src/riesgo_altitud.py`, con cifras en
> `reportes/etapa_06_riesgo_altitud.json`.
> **Modelo:** versión 2 (D-035). Para regenerar: `modelo_v2.py`, `arsenal.py`,
> `pasaporte_altitud.py` y `ficha.py`.

## Para qué sirve

La pregunta que responde al cuerpo técnico:

> "¿Qué tiene este pitcher, cómo usa cada pitch y cuánto arriesga en el Harp Helú?"

Es una página local con buscador y temporada. Incluye 818 fichas (pitcher y temporada con 300+
pitches: 320 de 2024, 320 de 2025 y 178 de 2026) y una tabla de la liga que se puede ordenar.

## Qué muestra

1. **Stuff+, Location+ y Pitching+** (versión 2), en escala 100 y con su percentil en la temporada.
2. **Riesgo en el Harp Helú:** tercio bajo, medio o alto de la liga (ver abajo).
3. **Arsenal,** solo pitches con 100+ en la temporada:
   - uso;
   - Stuff+ dentro de su tipo;
   - percentil de cada componente dentro de su tipo (swing, whiff, foul, strike cantado);
   - un rol;
   - la pérdida promedio de ese tipo en altura en la liga.
4. **Lectura:** frases que salen de reglas fijas, listadas abajo.
5. **Qué tanto creerle:** cuánto se repite cada número de 2024 a 2025 en el mismo pitcher.

| Valor (versión 2) | r de 2024 a 2025 (146 pitchers) |
|---|---|
| Stuff+ | 0.83 |
| Location+ | 0.67 (0.68 en la versión 1) |
| Pitching+ | 0.64 (0.64 en la versión 1) |
| xRV real | 0.18 |

## El riesgo de altitud (D-036)

**Riesgo = suma de uso × pérdida promedio de la liga para ese tipo de pitch.** Las pérdidas vienen de
los pares de D-034:

| Tipo | Pérdida por 100 pitches | Pares |
|---|---|---|
| Recta | 0.40 | 210 |
| Sinker | 0.32 | 97 |
| Cambio | 0.32 | 51 |
| Slider | 0.18 | 129 |
| Curva | 0.02 | 35 |

**Prueba (299 pitchers, 2024–2025; la pérdida por tipo se calculó sin el pitcher evaluado):**

| Candidato | r con el cambio real | Error contra la constante |
|---|---|---|
| **Riesgo por arsenal** | **0.11** (0.0001 a 0.21) | −0.032 a +0.008 (empate) |
| Pasaporte agregado (comparación) | 0.20 (0.08 a 0.31) | −0.058 a +0.068 (empate) |

- **Veredicto según la regla: ordena, pero no como cifra.** El intervalo apenas excluye el cero.
- El pasaporte ordena un poco mejor, pero la diferencia toca cero (−0.01 a +0.18, calculada después) y
  su nivel exagera la pérdida (0.47 contra 0.31). Se queda el riesgo por arsenal, que era el candidato
  fijado y es más fácil de explicar.
- **Por eso la ficha muestra tercios, no carreras.** Además, la diferencia entre pitchers es chica:
  del percentil 10 al 90 va de 0.22 a 0.40 carreras por 100 pitches.

**Cobertura:**

- Solo cuentan los tipos con 100+ pitches y con pérdida medida. Cutter y splitter no tienen suficientes
  pares.
- En promedio el cálculo cubre 75 % de los pitches del pitcher (67 % en 2026, que va a media
  temporada).
- **Con menos de 60 % cubierto no se da nivel.** Si no, el riesgo lo decidiría un solo pitch: un pitcher
  con 42 % rectas y 40 % cutters salía "alto" solo por la recta. Quedan sin nivel 64, 58 y 63 fichas
  de 2024, 2025 y 2026.

## Reglas de la lectura

Los percentiles se calculan dentro del tipo de pitch y la temporada. "Alto" es el tercio superior
(percentil 67+); "bajo" es el tercio inferior (percentil 33 o menos).

| Lectura | Regla |
|---|---|
| Gana con calidad / con ubicación / parejo | Stuff+ − Location+ ≥ 10, ≤ −10, o entre ambos |
| Mejor pitch | El de mayor Stuff+ dentro de su tipo |
| Rol "para ponchar" | Whiff en el tercio alto |
| Rol "roba strikes" | Strike cantado en el tercio alto |
| Rol "provoca swing" / "saca fouls" | Swing / foul en el tercio alto |
| "Pitch débil" / pitch a vigilar | Whiff en el tercio bajo y Stuff+ < 95 |
| Riesgo alto con pitches que resisten | Tercio alto y un slider o curva (pérdida < 0.2) con Stuff+ ≥ 100 |
| Muestra corta | Menos de 450 pitches en la temporada |

El whiff manda en los roles porque es el componente que más separa un buen pitch de uno malo (r 0.67
a 0.73 con el Stuff+, `docs/05_arsenal.md`).

## Lo que la ficha no dice

- **No promete que cambiar la mezcla mejore el resultado.** Cuando sugiere apoyarse en una slider o
  curva en casa, lo dice como opción. Que esos tipos pierdan poco en altura es una observación de la
  liga; no probamos qué pasa si un pitcher los usa más.
- La pérdida por tipo es el promedio de la liga, no una estimación del pitcher.
- Los componentes del arsenal son probabilidades del modelo, no tasas observadas. Con poca muestra
  dependen menos del azar que el resultado, pero aun así se mueven.
- 2026 aparece porque es la temporada actual. Sus números salen de modelos entrenados con 2024–2025 y
  no se usan para evaluar.
