# Etapa 3 · Plan: el target de carreras esperadas y los modelos base

> **Estado:** validado por el equipo el 7 de octubre de 2026 e implementado. Resultados en
> [`03_target.md`](03_target.md). El modelo con `altitude_category` (punto 6, modelo 5) se evalúa en
> la etapa 4, porque usa el mismo algoritmo que el modelo final.
> **Evidencia:** `src/exploracion_etapa_03.py`; cifras en `reportes/etapa_03_exploracion.json`.
> Todo se estima con 2024–2025; 2026 solo se usa para evaluar.

## Qué queremos

Un número por pitch que diga **cuántas carreras le sumó o le quitó al rival** (xRV), quitando lo
que no depende del pitcher: la defensa y la suerte de dónde cae la pelota. Es lo que van a predecir
Stuff+, Location+ y Pitching+ en la etapa 4. El target es el mismo para los tres; cambian las
variables que puede usar cada uno.

Además, la escalera de **modelos base** de D-020: el modelo de la etapa 4 solo cuenta si les gana.

## Lo que encontramos en los datos

| Pregunta | Respuesta |
|---|---|
| ¿Hay estado de corredores en base? | No. Eso impide la tabla clásica de carreras esperadas por base y outs (RE24) |
| ¿Podemos reconstruir medias entradas? | Sí: 33,805 de 37,023 (91 %) empiezan con 0 outs y terminan con 3. Las demás tienen outs fuera de un pitch (robos, pickoffs) o pitches faltantes |
| ¿Las carreras tienen sentido? | 0.66 carreras por media entrada (≈ 5.9 por equipo en 9 entradas): 0.53 a nivel del mar, 0.81 en altitud extrema |
| ¿El conteo registrado es confiable? | Sí: de 464,599 cambios de conteo dentro del turno, solo 0.3 % no coincide con lo que dice el pitch anterior |
| ¿Toda bola en juego tiene velocidad de salida? | No: 7,764 de 115,946 no la tienen, y no al azar: valen 0.017 carreras en promedio contra 0.186 de las demás (son contacto débil que el radar no siguió) |

## Decisiones propuestas

### 1. Valor de cada desenlace: regresión sobre medias entradas completas

Sin corredores no podemos usar RE24. Usamos el método clásico de **pesos lineales por regresión**:
las carreras de cada media entrada se explican con cuántos sencillos, dobles, bases por bolas,
ponches, etc. hubo en ella. Usa la entrada completa, así que no necesita saber dónde estaban los
corredores.

| Desenlace | Carreras (liga) | Nivel del mar | Altitud extrema |
|---|---|---|---|
| Sencillo | 0.52 | 0.48 | 0.55 |
| Doble | 0.83 | 0.77 | 0.89 |
| Triple | 1.13 | 1.02 | 1.21 |
| Jonrón | 1.43 | 1.43 | 1.42 |
| Base por bolas | 0.39 | 0.34 | 0.45 |
| Golpeado | 0.41 | 0.38 | 0.37 |
| Ponche | −0.12 | −0.10 | −0.14 |
| Out en juego | −0.11 | −0.10 | −0.13 |

El orden y la escala son los esperados (el jonrón vale ≈ 1.4 carreras, como en MLB; ponche y out en
juego valen casi lo mismo). No los comparamos uno a uno con MLB porque allá se calculan con
corredores y en otro ambiente de carreras. En altura todo vale más salvo el jonrón: con más corredores en base
y más batazos, un embasado tiene más probabilidad de anotar.

- **Error, sacrificio y bola ocupada cuentan como out** para el pitcher: el error es de la defensa,
  y el sacrificio y la bola ocupada son outs. En la regresión salen con valores raros (error +0.60,
  sacrificio +0.19) porque solo pasan con corredores en base; por eso no los usamos tal cual.
- **Alternativas descartadas:** carreras esperadas solo por outs (confunde el desenlace con los
  corredores que ya había: la bola ocupada saldría positiva); pesos publicados de MLB (otro ambiente
  de carreras).

### 2. Dos versiones del target: neutral y local

- **Neutral (pesos de la liga):** para Stuff+ comparable entre pitchers sin importar dónde lanzan.
- **Local (pesos de su altitud):** para "¿cuánto vale este pitch en el Harp Helú?". Una base por
  bolas en la CDMX cuesta 0.45 carreras contra 0.34 a nivel del mar; el club debe ver ese costo real.

### 3. Valor del conteo y valor de cada pitch

El valor de un conteo es el promedio del desenlace final de los turnos que pasaron por él:

| Bolas \ Strikes | 0 | 1 | 2 |
|---|---|---|---|
| 0 | 0.145 | 0.106 | 0.053 |
| 1 | 0.179 | 0.133 | 0.073 |
| 2 | 0.227 | 0.174 | 0.107 |
| 3 | 0.307 | 0.257 | 0.185 |

El valor del pitch es **conteo después − conteo antes**. Si termina el turno, es **desenlace −
conteo antes**. Así, un strike en 0-0 vale −0.039 carreras; una bola en 3-2 (base por bolas) vale
+0.20. La suma de los pitches de un turno da exactamente el valor del desenlace.

- El conteo "después" se deduce del resultado del pitch (bola, strike, foul), no de la fila
  siguiente. Así el 0.3 % de conteos inconsistentes no contamina el target.
- Foul con dos strikes vale 0 (el conteo no cambia).

### 4. Bola en juego: valor esperado, no real

Una bola en juego vale lo que **suele valer un batazo con esa velocidad de salida, ángulo y
dirección**, no lo que pasó. Así no se castiga al pitcher por un error o un hit de suerte.

- Predicción en 2026: con velocidad y ángulo, R² = 0.38; agregando la dirección (hacia el lado que
  jala el bateador), R² = 0.51.
- **Regla fijada antes de probar:** nos quedamos con la versión cuyo promedio por pitcher en
  2024–2025 prediga mejor su valor real en 2026. La dirección explica más, pero puede ser más
  habilidad del bateador que del pitcher; que decida la prueba.
- **Neutral:** el modelo se entrena a nivel del mar (lo que valdría ese batazo en un parque sin
  altitud, coherente con la forma a nivel del mar de la etapa 2). **Local:** usa la altitud.
- **Bolas sin velocidad de salida (7,764):** ni se borran ni se inventa su velocidad. Toman el valor
  promedio real de su grupo (toques, por su tipo de batazo; las demás, el promedio de las bolas no
  seguidas por el radar). Borrarlas premiaría menos a los pitchers que provocan contacto débil.

### 5. Pitches sin target

Solo los 841 con `PitchCall` indefinido. Se quedan en la tabla con target nulo y bandera.

### 6. Modelos base (D-020)

Se construyen en esta etapa, con el target ya listo, y se evalúan en 2026:

| # | Modelo base | Qué representa |
|---|---|---|
| 1 | Media de la liga | Predecir siempre el promedio |
| 2 | Media por conteo | El contexto de bolas y strikes |
| 3 | Media por tipo de pitch y mano | "Una slider de derecho" en general |
| 4 | Regresión lineal con velocidad, movimiento y extensión | El modelo simple de cualquier equipo |
| 5 | Modelo con `altitude_category` como variable | La alternativa descartada en D-001 |

- **Por pitch:** error cuadrático medio en 2026.
- **Por pitcher** (lo que usa el club): qué tanto el promedio de 2024–2025 predice el valor real del
  pitcher en 2026, con intervalo remuestreando pitchers.

### 7. Prueba de que el target "esperado" sirve

Si quitar la suerte funciona, el xRV de un pitcher en 2024–2025 debe predecir su valor **real** de
2026 mejor que su propio valor real de 2024–2025. También medimos estabilidad: correlación entre dos
mitades al azar de los pitches de cada pitcher. Si no gana, se reporta y se revisa.

## Entregables

- `src/target.py`: agrega a la tabla las columnas `xrv_neutral` y `xrv_local`, con sus banderas.
- `src/modelos_base.py`: la escalera de modelos base y las pruebas del punto 7.
- `docs/03_target.md` y `reportes/etapa_03_target.html`.

## Límites conocidos

- Sin corredores, los pesos son promedios sobre todas las situaciones de base: no distinguen un
  sencillo con bases llenas de uno con bases vacías. Para evaluar pitchers es lo estándar (los pesos
  lineales de FanGraphs también son promedios).
- Las 3,218 medias entradas incompletas no entran a la regresión de pesos, pero sus pitches sí
  reciben target.
- Robos, wild pitches y pickoffs no se le cargan al pitch; no tenemos cómo atribuirlos.
