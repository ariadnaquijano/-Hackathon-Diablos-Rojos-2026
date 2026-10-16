# Location+ con PyTorch: guía de implementación

Esta guía describe el código de `location_plus.py` y `run_value.py` tal como está en el
repositorio. Explica qué mide Location+, por qué se diseñó así, cómo funciona la red y
con qué fórmulas se calcula cada métrica. La sección 12 tiene los resultados de la
corrida completa.

**Resumen honesto:** el modelo predice bien si habrá swing (AUC 0.84) y si un take será
strike (AUC 0.98). Predice moderadamente el whiff (AUC 0.73) y casi nada el resultado
del contacto (foul o en juego, y qué tipo de hit). Eso es lo esperado si el modelo solo
ve ubicación y cuenta. A nivel pitcher, Location+ se correlaciona +0.42 con el CSW real
y −0.43 con el run value real en 2026, datos que el modelo no vio al entrenar.

## 1. Qué construimos

Location+ mide la calidad de la **ubicación** de los pitches de un pitcher, aislándola
del tipo de pitch, la velocidad y el movimiento. Responde a esta pregunta: si un pitch
promedio de la liga cayera exactamente donde cayó este, en la misma cuenta y con el
mismo enfrentamiento de manos, ¿qué esperaríamos que pasara?

El sistema tiene cuatro piezas:

1. **Run value por pitch** (`run_value.py`): cuántas carreras vale cada resultado posible
   de un pitch en cada cuenta. Se estima solo con train y usa la misma construcción que
   el Stuff+ de Max.
2. **Red neuronal de resultados** (`location_plus.py`): una red de PyTorch que, a partir
   de la ubicación y el contexto, predice la probabilidad de cada resultado del pitch
   (bola, strike cantado, whiff, foul, HBP, out, 1B, 2B, 3B, HR).
3. **Dos métricas esperadas por pitch:** el **xCSW** (probabilidad de called strike o
   whiff) y el **xRV** (run value esperado).
4. **Location+:** combina el xCSW y el xRV de cada pitcher, ambos ajustados por cuenta,
   en una escala plus (100 = liga, ±10 = ±1 desviación estándar).

### Explicación corta para la reunión

> La red aprendió, con 2024-2025, qué tan seguido un pitch en cada punto de la zona
> provoca swing, whiff o strike cantado, y qué pasa cuando le hacen contacto. Con eso
> calculamos para cada pitch de 2026 dos cosas: la probabilidad de sacar un strike
> (xCSW) y cuántas carreras esperamos que le cueste o le ahorre al pitcher (xRV).
> Location+ promedia ambas por pitcher, comparando contra la liga en las mismas cuentas.
> 100 es promedio y 110 es una desviación estándar mejor.

## 2. Datos de entrada

- **Fuente:** `pitches_limpios.parquet` (635,002 pitches, 2,127 juegos).
- **Partición:** se usa la columna `split` existente.
  - Train: 2024-2025 (499,393 pitches después de los filtros).
  - Holdout: 2026 (134,768 pitches). Solo se usa para evaluar y para calcular Location+.
- **Filtros del modelo** (`filtrar_para_modelo`): se quitan los pitches con
  `PitchCall = 'Undefined'`, con `is_swing` nulo y con cuentas imposibles (más de 3
  bolas o más de 2 strikes).
- **Filtros del run value:** ninguno antes del ajuste. El run value necesita ver las
  medias entradas completas, incluso con pitches indefinidos, para decidir cuáles son
  confiables (sección 4.2).
- **Nulos:** `altitude_category` y `batter_side` nulos se reemplazan por la categoría
  `'Unknown'`, en lugar de descartar el pitch.

## 3. Qué ve y qué no ve el modelo

| Grupo | Columnas | Tipo |
|---|---|---|
| Ubicación | `PlateLocHeight`, `PlateLocSide`, `in_strike_zone`, `outside_strike_zone` | numérica |
| Cuenta | `Balls`, `Strikes` (numéricas) y `count` (one-hot) | ambas |
| Situación | `Outs`, `Inning`, `Top/Bottom` | numérica / one-hot |
| Altitud | `altitude_category` | one-hot |
| Manos | `pitcher_hand`, `batter_side` | one-hot |

**El modelo no ve** velocidad, spin, movimiento, punto de suelta, tipo de pitch, la
identidad del pitcher o del bateador, ni ninguna variable del resultado. Esa es la
decisión central del diseño: si el modelo viera el tipo de pitch o la velocidad,
Location+ se mezclaría con Stuff+.

**Por qué entran las manos:** el mismo `PlateLocSide` puede ser "adentro" contra un
bateador y "afuera" contra otro. Sin `pitcher_hand` y `batter_side`, la red no puede
distinguirlos.

**Por qué entra la altitud:** en altura la bola se comporta distinto y la zona puede
jugar distinto. Se deja como contexto para que no se acredite como habilidad.

**Preprocesamiento** (`Preprocesador`): las numéricas se estandarizan con la media y la
desviación de train, y las categóricas pasan a one-hot. Las categorías se fijan en todo
el DataFrame para que train y holdout tengan exactamente las mismas columnas.

## 4. Run value: cuántas carreras vale cada resultado

Esta parte replica la sección 6 de `docs/STUFFPLUS_MODEL_GUIDE.md` de la rama Max
(`stuffplus/target.py`). Se reimplementó en `run_value.py` con la misma lógica, los
mismos filtros y las mismas validaciones. Con los mismos datos de train da exactamente
los mismos pesos y valores de cuenta que reporta Max.

### 4.1 Transición de cada pitch

Cada pitch se clasifica solo con su propio `PitchCall` y su cuenta, sin depender del
orden de las filas:

| Resultado del pitch | Menos de 3 bolas / 2 strikes | Con 3 bolas / 2 strikes |
|---|---|---|
| Bola (`BallCalled`, `BallinDirt`) | cuenta +1 bola | **BB** (terminal) |
| Strike (`StrikeCalled`, `StrikeSwinging`) | cuenta +1 strike | **K** (terminal) |
| Foul (`FoulBall`, `FoulBallNotFieldable`) | cuenta +1 strike | misma cuenta |
| `FoulBallFieldable` con out registrado | **OUT** (terminal) | **OUT** (terminal) |
| `FoulBallFieldable` sin out | como foul | como foul |
| `HitByPitch` | **HBP** (terminal) | **HBP** (terminal) |
| `InPlay` | según `play_result`: 1B, 2B, 3B, HR, OUT, E, SAC, FC | igual |

Un `play_result` que no se reconoce (por ejemplo, `NeutralPlay` en una bola en juego)
deja la transición como **desconocida**. No se reetiqueta como out.

### 4.2 Pesos lineales por evento

Se agrupan los pitches de train por media entrada (`year`, `game_anon_id`, `Inning`,
`Top/Bottom`). Una media entrada es **completa** si empieza con 0 outs, termina con
exactamente 3 outs, los outs registrados suman 3, no tiene transiciones desconocidas y
sus carreras no son negativas.

Con las 24,977 medias entradas completas de train se ajusta una regresión OLS **sin
intercepto**:

```text
carreras en la media entrada ≈ Σ_e  w_e · (número de eventos e en la media entrada)
e ∈ {1B, 2B, 3B, HR, BB, HBP, K, OUT, E, SAC, FC}
```

Después del ajuste, los pesos de E, SAC y FC se reemplazan por el de OUT, para no
cobrarle al pitcher la defensa ni las decisiones de los corredores. El código verifica
que HR > 1B > OUT y BB > K. Si no se cumple, falla.

| Evento | Peso (carreras) |
|---|---:|
| Sencillo (1B) | +0.533 |
| Doble (2B) | +0.826 |
| Triple (3B) | +1.124 |
| Home run (HR) | +1.426 |
| Base por bolas (BB) | +0.396 |
| Golpeado (HBP) | +0.430 |
| Ponche (K) | −0.123 |
| Out (y E, SAC, FC) | −0.108 |

### 4.3 Valor de cada cuenta

`V(c)` es el run value esperado del turno cuando está en la cuenta `c` (12 cuentas,
de 0-0 a 3-2). Se resuelve como una cadena de Markov absorbente:

```text
V(c) = Σ_d P(d | c) · V(d)  +  Σ_e P(e | c) · w_e
En forma matricial:  (I − Q) · V = r
```

`Q` contiene las probabilidades de pasar de una cuenta a otra y `r` el valor esperado
de los eventos terminales desde cada cuenta, ambos estimados con los pitches de train.
Se exigen al menos 30 transiciones por cuenta.

| Bolas / strikes | 0 strikes | 1 strike | 2 strikes |
|---|---:|---:|---:|
| 0 bolas | 0.1496 | 0.1109 | 0.0543 |
| 1 bola | 0.1819 | 0.1358 | 0.0733 |
| 2 bolas | 0.2305 | 0.1769 | 0.1081 |
| 3 bolas | 0.3112 | 0.2588 | 0.1864 |

### 4.4 Run value observado de un pitch

```text
Pitch que no termina el turno:  RV = V(cuenta después) − V(cuenta antes)
Pitch que termina el turno:     RV = w(evento)         − V(cuenta antes)
```

Ejemplo: un strike cantado en 0-0 vale `0.1109 − 0.1496 = −0.0387` carreras. El signo
negativo significa que es bueno para el pitcher. Un foul con 2 strikes vale 0.

### 4.5 Diferencias con la implementación de Max

| | Stuff+ (Max) | Location+ (esta guía) |
|---|---|---|
| Filas para ajustar el run value | solo pitches elegibles para Stuff+ | todos los pitches de train |
| Uso del RV | etiqueta de una regresión con XGBoost | valores para ponderar las probabilidades de la red |
| Modelo | XGBoost por familia de pitch | una red de PyTorch para todos los pitches |

Ajustar con todas las filas hace que haya más medias entradas completas disponibles.
En esta corrida los pesos quedaron iguales a los de Max hasta el tercer decimal.

## 5. La red neuronal

### 5.1 Por qué un árbol de resultados y no una regresión directa del RV

El run value de un pitch individual es muy ruidoso: la mayoría de los pitches valen
unas centésimas de carrera, y unos pocos (los home runs) valen más de una carrera.
Hacer una regresión directa del RV con la ubicación desperdicia información. Por eso la
red predice **qué pasa** con el pitch, y el valor en carreras se calcula después con las
tablas de la sección 4.

Esta estructura tiene dos ventajas:

- La red no necesita aprender el valor de las cuentas. Ese valor ya viene fijo de la
  sección 4.
- El xCSW y el xRV salen del **mismo modelo**, así que son coherentes entre sí.

### 5.2 Arquitectura (`RedLocation`)

```text
entrada (numéricas estandarizadas + one-hot)
  → Linear(128) → BatchNorm → ReLU → Dropout(0.1)
  → Linear(64)  → BatchNorm → ReLU → Dropout(0.1)
  → Linear(32)  → BatchNorm → ReLU → Dropout(0.1)
  → Linear(10 logits)
```

Es un tronco compartido con una capa final de 10 salidas. Las primeras 5 son cabezas
binarias (sigmoide) y las últimas 5 son una softmax.

| # | Cabeza | Población con la que se entrena | Activación |
|---|---|---|---|
| 1 | P(swing) | todos los pitches | sigmoide |
| 2 | P(whiff \| swing) | pitches con swing | sigmoide |
| 3 | P(called strike \| take) | pitches sin swing | sigmoide |
| 4 | P(HBP \| take sin strike) | takes que no fueron strike cantado | sigmoide |
| 5 | P(foul \| contacto) | swings sin whiff | sigmoide |
| 6-10 | P(OUT, 1B, 2B, 3B, HR \| en juego) | contactos que no fueron foul | softmax |

Un `FoulBallFieldable` atrapado (out) se cuenta como bola en juego con resultado OUT,
no como foul. E, SAC y FC se agrupan dentro de OUT porque valen lo mismo
(sección 4.2).

### 5.3 Función de pérdida

Cada cabeza aprende solo de su población, mediante una máscara. Por ejemplo, un take no
le enseña nada a la cabeza de whiff.

```text
pérdida = Σ_{k=1..5}  mean_{i ∈ población_k}  BCE(y_ik, σ(logit_ik))
        + mean_{i ∈ en juego}  CrossEntropy(clase_i, softmax(logits_i,6..10))
```

El promedio de cada cabeza se calcula sobre su propia población, así que las cabezas con
pocas observaciones (HBP, bolas en juego) pesan igual que la de swing en la pérdida.

### 5.4 Entrenamiento y validación

| Parámetro | Valor |
|---|---|
| Optimizador | AdamW, lr = 1e-3, weight_decay = 1e-4 |
| Scheduler | ReduceLROnPlateau (factor 0.5, paciencia 1) |
| Batch | 2048 |
| Épocas | máximo 40, early stopping con paciencia 4 |
| Validación | 10% de los **juegos** de train |
| Semilla | 42 |
| Dispositivo | MPS (Mac), CUDA o CPU, el que haya |

- **La validación se separa por juego, no por pitch.** Así los pitches de un mismo juego
  no quedan a la vez en entrenamiento y en validación.
- **El holdout (2026) nunca se usa para entrenar ni para elegir la época.** Se usa solo
  al final, para medir el desempeño y calcular Location+.
- **Se guardan los pesos de la mejor época** según la pérdida de validación, no los de la
  última.

## 6. Fórmulas por pitch

Notación: `ps` = P(swing), `pw` = P(whiff | swing), `pcs` = P(called strike | take),
`ph` = P(HBP | take sin strike), `pf` = P(foul | contacto), `q_k` = P(clase k | en juego).

### 6.1 Probabilidad de cada resultado final

```text
P(whiff)          = ps · pw
P(called strike)  = (1 − ps) · pcs
P(HBP)            = (1 − ps) · (1 − pcs) · ph
P(bola)           = (1 − ps) · (1 − pcs) · (1 − ph)
P(foul)           = ps · (1 − pw) · pf
P(en juego)       = ps · (1 − pw) · (1 − pf)
P(en juego, k)    = P(en juego) · q_k ,   k ∈ {OUT, 1B, 2B, 3B, HR}
```

Las seis primeras suman 1 por construcción.

### 6.2 xCSW

```text
xCSW = P(called strike) + P(whiff)
```

Se pueden sumar porque son excluyentes: el whiff requiere swing y el called strike
requiere take.

### 6.3 Valor de cada resultado según la cuenta (`valores_por_resultado`)

Para un pitch con cuenta `(b, s)` y `V` de la sección 4.3:

```text
v_bola    = w_BB  si b = 3,  si no  V(b+1, s)     − V(b, s)
v_strike  = w_K   si s = 2,  si no  V(b, s+1)     − V(b, s)
v_foul    = V(b, min(s+1, 2))                     − V(b, s)
v_HBP     = w_HBP                                 − V(b, s)
v_k       = w_k   para k ∈ {OUT, 1B, 2B, 3B, HR}  − V(b, s)
```

El called strike y el whiff usan el mismo `v_strike`, porque los dos suman un strike.

### 6.4 xRV

```text
xRV = P(bola) · v_bola
    + P(HBP) · v_HBP
    + xCSW · v_strike
    + P(foul) · v_foul
    + P(en juego) · Σ_k q_k · v_k
```

El xRV está en carreras desde la perspectiva de la ofensiva: **negativo es bueno para
el pitcher**. Es el valor esperado del mismo RV observado de la sección 4.4, así que se
pueden comparar directamente.

## 7. Ajuste por cuenta (residuos)

La cuenta cambia mucho el xCSW y el xRV. En 0-2 el bateador hace swing a casi todo y el
pitcher puede tirar afuera. En 3-0 el pitcher necesita strike. Si comparáramos
promedios crudos, un pitcher que vive en cuentas favorables se vería mejor sin que su
ubicación sea mejor. Para cada pitch:

```text
xCSW_resid = xCSW − promedio de xCSW de la liga en esa cuenta
xRV_resid  = xRV  − promedio de xRV  de la liga en esa cuenta
```

Los promedios de la liga se calculan con todos los pitches del holdout, incluidos los
de pitchers que no califican. Después se promedian los residuos por pitcher (o por
pitcher × `pitch_group`).

## 8. Escalas plus y Location+

### 8.1 Convención

Se usa la misma convención que el Stuff+ de Max: **100 ± 10 por desviación estándar
poblacional** (`ddof = 0`). Hay dos diferencias:

- **El centro es residuo 0, es decir, el promedio de la liga en la misma cuenta.** No es
  el promedio de los pitchers que califican. Por eso el promedio de la tabla no da
  exactamente 100.
- **La desviación se calcula entre los grupos que califican** (pitchers con 200 pitches o
  más, o combinaciones pitcher × pitch con 75 o más). En Stuff+ se calcula entre pitches.
  Con la desviación entre pitches, los promedios por pitcher quedarían todos pegados a 100.

### 8.2 Fórmulas

Para cada grupo `g` que califica, con `σ` = desviación estándar entre grupos:

```text
z_CSW(g) =  xCSW_resid(g) / σ(xCSW_resid)
z_RV(g)  = −xRV_resid(g)  / σ(xRV_resid)        (el signo − hace que mayor sea mejor)

CSW+(g)  = 100 + 10 · z_CSW(g)
RV+(g)   = 100 + 10 · z_RV(g)

z(g)          = PESO_CSW · z_CSW(g) + (1 − PESO_CSW) · z_RV(g)
Location+(g)  = 100 + 10 · z(g) / σ(z)
```

Con `PESO_CSW = 0.5` (constante en `location_plus.py`).

**Por qué se reestandariza `z`:** como `z_CSW` y `z_RV` están muy correlacionados, su
promedio tiene una desviación menor que 1. Reestandarizar hace que Location+ mantenga la
lectura de "±10 = ±1 desviación estándar".

**Por qué combinar CSW y RV si el xRV ya incluye los strikes:** los dos miden cosas
distintas. El xCSW premia la capacidad de **sacar strikes** con la ubicación, que es
estable y fácil de explicar a un pitcher. El xRV premia **evitar daño**: también cuenta
las bolas, los HBP y lo que pasa con el contacto. Combinarlos le da más peso a los
strikes que el RV solo, y ese es un énfasis intencional. `PESO_CSW` permite moverlo.

### 8.3 Cómo leer los valores

- **100:** igual que la liga en las mismas cuentas.
- **110:** una desviación estándar mejor que la liga.
- **90:** una desviación estándar peor.
- **110 no significa** 10% más strikes ni 10% menos carreras.

## 9. Salidas

| Archivo | Contenido |
|---|---|
| `location_plus_pitcher.parquet` | una fila por pitcher (≥ 200 pitches en 2026) |
| `location_plus_pitcher_pitch.parquet` | una fila por pitcher × `pitch_group` (≥ 75 pitches) |
| `run_value_tablas.json` | pesos, V(cuenta) y diagnósticos del run value |
| `location_plus_red.pt` | pesos de la red, media/desv. del preprocesador y tablas de RV |

Columnas de los parquet:

| Columna | Significado |
|---|---|
| `pitches` | pitches del grupo en el holdout |
| `xCSW`, `CSW` | CSW esperado y real (crudos, sin ajustar por cuenta) |
| `p_whiff`, `p_called_strike` | componentes promedio del xCSW |
| `xRV`, `RV` | run value esperado y real por pitch (crudos) |
| `xCSW_resid`, `xRV_resid` | residuos promedio contra la liga en la misma cuenta |
| `CSW+`, `RV+` | cada componente en escala plus |
| `Location+` | la combinación final |

## 10. Cómo correrlo

```bash
python location_plus.py
```

- Necesita `pitches_limpios.parquet` en la misma carpeta que el script (no está en git).
- Dependencias: `numpy`, `pandas`, `pyarrow`, `torch`, `scikit-learn`.
- Los archivos de salida se guardan en la carpeta desde donde se ejecuta el comando.
- En una Mac con MPS tarda unos minutos.
- Si `torch` se instaló compilado para NumPy 1.x, hace falta `numpy<2`.

## 11. Limitaciones y qué decir con cuidado

- **No hay corredores en base.** Los pesos son promedios: un sencillo vale lo mismo con
  las bases vacías que con las bases llenas. Lo mismo pasa con el Stuff+ de Max.
- **La ubicación no es independiente del stuff.** Un pitcher con una recta dominante
  puede atacar la zona y aun así sacar whiffs. El modelo usa la tasa promedio de la liga
  en ese punto, así que no lo acredita a la ubicación. Esto es intencional, pero hay que
  explicarlo.
- **No se distinguen tipos de pitch.** Un slider abajo y afuera y una recta en el mismo
  punto reciben la misma predicción. Lo que mide Location+ es "qué tan buen lugar es
  este para un pitch promedio".
- **El resultado del contacto casi no se predice con ubicación.** Las cabezas de foul y
  de resultado en juego apenas superan a la base constante (sección 12). La mayor parte
  de la señal del xRV viene de swing, whiff, strike cantado y bola.
- **Faltan algunas medias entradas.** Alrededor del 9% no registra 3 outs. Esas no
  entran al ajuste de los pesos, pero sus pitches sí entran al modelo.
- **Las variables de zona son derivadas.** `in_strike_zone` y `outside_strike_zone`
  vienen de la limpieza de los datos. Si la zona se definió con un criterio fijo, puede
  no coincidir con la zona real de cada umpire.
- **Una sola temporada de evaluación.** Todavía no se mide qué tan estable es Location+
  de un año a otro ni si predice el desempeño futuro.

## 12. Resultados de la corrida completa

### 12.1 Cabezas de la red (holdout 2026)

La base es predecir siempre la tasa de train.

| Cabeza | n | Tasa | AUC | LogLoss (base) | Brier (base) |
|---|---:|---:|---:|---|---|
| swing | 134,768 | 0.465 | 0.842 | 0.487 (0.691) | 0.162 (0.249) |
| whiff \| swing | 62,615 | 0.244 | 0.731 | 0.480 (0.555) | 0.154 (0.184) |
| called strike \| take | 72,153 | 0.309 | 0.977 | 0.195 (0.620) | 0.060 (0.214) |
| HBP \| take sin strike | 49,844 | 0.010 | 0.969 | 0.028 (0.058) | 0.008 (0.010) |
| foul \| contacto | 47,364 | 0.483 | 0.595 | 0.677 (0.693) | 0.242 (0.250) |
| resultado en juego (5 clases) | 24,502 | — | — | 0.961 (0.973) | — |

El entrenamiento paró en la época 21. La mejor pérdida de validación fue 2.8129, en la
época 17.

### 12.2 Métricas por pitch

| | Esperado | Real |
|---|---:|---:|
| CSW medio | 0.259 | 0.279 |
| RV medio por pitch | −0.0005 | −0.0014 |
| Correlación pitch a pitch | xCSW vs CSW: 0.430 | xRV vs RV: 0.181 |

Calibración del xRV por cuenta (carreras por pitch):

| | 0-0 | 0-1 | 0-2 | 1-0 | 1-1 | 1-2 | 2-0 | 2-1 | 2-2 | 3-0 | 3-1 | 3-2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| xRV | −0.0002 | +0.0006 | −0.0012 | −0.0014 | +0.0002 | −0.0000 | −0.0010 | +0.0013 | −0.0007 | −0.0052 | −0.0011 | −0.0035 |
| RV | −0.0009 | −0.0005 | +0.0011 | −0.0050 | +0.0008 | −0.0029 | +0.0013 | +0.0021 | −0.0025 | −0.0052 | −0.0069 | −0.0035 |

En todas las cuentas, la diferencia es menor a media centésima de carrera por pitch.

**El CSW real (0.279) es mayor que el esperado (0.259).** En 2026 hubo más strikes de
lo que la red aprendió con 2024-2025. Puede ser un cambio de liga o de umpires. Este
desfase no afecta a Location+, porque Location+ compara contra la liga del mismo año.

### 12.3 Por pitcher (273 pitchers con 200 pitches o más)

| Métrica | Correlación con CSW real | Correlación con RV real |
|---|---:|---:|
| Location+ | +0.424 | −0.428 |
| CSW+ | +0.426 | −0.341 |
| RV+ | +0.377 | −0.470 |

Como era de esperar, CSW+ es el que mejor sigue al CSW real y RV+ el que mejor sigue al
RV real. Location+ queda en medio y sigue a los dos casi igual de bien. Esa es la
intención de combinarlos.

Top 5 de Location+ en 2026:

| Pitcher | Pitches | CSW+ | RV+ | Location+ |
|---|---:|---:|---:|---:|
| pitcher_00875 | 349 | 124.5 | 125.9 | 126.6 |
| pitcher_00456 | 220 | 125.2 | 124.5 | 126.2 |
| pitcher_00465 | 357 | 122.1 | 123.7 | 124.1 |
| pitcher_00469 | 284 | 121.3 | 120.8 | 122.2 |
| pitcher_00355 | 333 | 113.9 | 127.6 | 121.9 |

pitcher_00355 es un buen ejemplo de por qué conviene combinar las métricas: su ubicación
saca strikes un poco arriba del promedio (CSW+ 114), pero es de las que menos daño
permite de la liga (RV+ 128).

## 13. Siguientes pasos sensatos

1. **Medir la estabilidad:** dividir 2026 en juegos pares e impares y correlacionar el
   Location+ de cada mitad. Comparar CSW+, RV+ y Location+.
2. **Elegir `PESO_CSW` con datos:** usar el peso que mejor prediga el RV del periodo
   siguiente, en lugar del 0.5 fijo.
3. **Interacción con el tipo de pitch:** entrenar una versión que vea `pitch_group`, para
   medir la ubicación relativa a cada pitch (un slider abajo y afuera contra una recta
   arriba). Esa versión mediría algo distinto y debería reportarse por separado.
4. **Unir con Stuff+:** combinar Location+ con el Stuff+ de Max en una métrica general de
   pitcheo, cuidando no contar dos veces el efecto de la ubicación que Max ya quita con
   su modelo de contexto.
