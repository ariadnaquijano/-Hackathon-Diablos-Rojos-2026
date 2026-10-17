# Guía técnica para escribir el documento técnico (6–10 páginas)

> **Para qué es:** el documento lo escribe el equipo a mano. Esta guía explica la parte técnica que
> quizá no todos dominan, en el orden que pide la convocatoria, con las cifras exactas y de dónde
> salen. **No es el documento**: es el material para escribirlo.
> **Regla de oro:** toda cifra del documento debe salir de un archivo de `reportes/` o de `docs/`.
> Si no está ahí, no se escribe. Los empates y lo que perdimos también van.

## 0. Lo que pide la convocatoria y cuánto espacio darle

El documento técnico debe cubrir cinco cosas. Esta tabla propone un reparto para 8 páginas:

| Sección pedida | Páginas | Sección de esta guía |
|---|---|---|
| Marco teórico: sabermetría, física del béisbol y entorno LMB | 1.5 | 1 |
| Decisiones de modelado: arquitectura, features y función de pérdida | 2 | 2 a 4 |
| Definición formal de la escala Stuff+ y normalización | 1 | 5 |
| Validación fuera de muestra: pitcher, season y park holdout | 2 | 6 |
| Alcance y fronteras del modelo | 1 | 8 |
| Resultados de altitud (los pide la rúbrica de integración) | 0.5 | 7 |

Rúbrica (25 % cada una): calidad del modelo (RMSE y calibración contra el modelo nulo), robustez
fuera de muestra (pitcher y park holdout), integración arsenal + altitud (delta de Stuff+ por tipo
de pitch entre el Harp Helú y nivel del mar) y aplicabilidad (entrevista de 10 minutos).

---

## 1. Marco teórico

### 1.1 Sabermetría: por qué valuar el pitch y no el resultado

- **Valor en carreras (run value).** Cada desenlace (sencillo, ponche, base por bolas…) cambia las
  carreras que se esperan en la entrada. A eso se le llama *pesos lineales* (Tango, Lichtman y
  Dolphin, *The Book*, 2007). Nosotros los estimamos con la LMB (sección 3).
- **El resultado de un pitch es casi todo azar.** Un mismo pitch puede ser foul, out o jonrón. Por
  eso se modela el valor *esperado* (xRV): lo que ese pitch suele producir, no lo que produjo.
  Dato nuestro: el xRV real de un pitcher se repite solo r = 0.18 de un año a otro.
- **La familia "plus" (FanGraphs).** Stuff+ mide la calidad física del pitch, Location+ dónde se
  puso y Pitching+ las dos juntas. 100 es la media de la liga y cada 10 puntos es una desviación.
  Se separan para no mezclar talento físico con comando.

### 1.2 Física: por qué el aire de la CDMX cambia el pitch

- **Efecto Magnus.** Un pitch con giro empuja el aire hacia un lado y el aire lo empuja de vuelta.
  De ahí sale el quiebre "inducido" (IVB, HB). Esa fuerza es proporcional a la densidad del aire.
- **Arrastre.** El aire frena la pelota, y también es proporcional a la densidad.
- **En el Harp Helú (2,240 m)** el aire es menos denso, así que:
  1. el pitch se mueve menos (menos Magnus);
  2. llega un poco antes, con menos tiempo para moverse;
  3. el batazo vuela más (menos arrastre).
- **Cómo medimos el aire sin datos de clima.** Con el propio TrackMan: el frenado de las rectas de
  cada juego. `air_ratio` = frenado mediano de las rectas del juego ÷ frenado mediano a nivel del mar
  esa temporada. Mediana en altitud extrema: 0.85 (2024) y 0.84 (2025): **16 % menos frenado**.
- **Ojo, frenado no es densidad (D-041).** El frenado es densidad × coeficiente de arrastre (ρ · Cd).
  Con la atmósfera estándar (77.2 kPa a 2,240 m) y temperaturas de juego, la densidad del Harp Helú es
  **0.785** de la del nivel del mar (rango 0.76–0.81). El frenado cae menos que la densidad porque el
  coeficiente de arrastre sube ~8 % con aire menos denso (menor número de Reynolds); esto último es una
  explicación plausible, no medida. Fuente: `docs/06_fisica_densidad.md`.

### 1.3 El exponente k: cuánto cambia el movimiento con el aire

- Modelo: **movimiento ∝ air_ratio^k**, con el aire medido como frenado.
- **En densidad:** k_ρ = k · ln(0.8445) ÷ ln(0.785) ≈ 0.70 · k. La física predice k_ρ ≈ 1.11: fuerza de
  Magnus ∝ ρ, y movimiento = ½ · a · t² con un tiempo de vuelo 1.3 % menor en altura (medido: la recta
  llega a 85.8 mph en la CDMX contra 83.9 a nivel del mar). **Resultado:** recta 1.05 en IVB y 1.14 en
  HB, sinker 0.98 en IVB, liga 1.10. La física cuadra.
- **Excepciones honestas:** el HB del cambio (1.43) y la IVB de la slider (0.47). Hipótesis, sin
  probar: los efectos de costura (*seam-shifted wake*) del cambio dependen del régimen del flujo, y la
  IVB de la slider es casi cero, así que su cociente es inestable.
- Se estima con el **mismo pitcher y el mismo pitch** en juegos con distinto aire.
- **Detalle técnico importante (D-016):** el aire de cada juego se mide con ruido. El ruido en la
  variable explicativa *achica* la pendiente; a eso se le llama sesgo de atenuación. La primera
  estimación daba k = 1.37. Se corrigió con **variable instrumental**: se usa solo la parte del aire
  que explica la categoría de altitud y la temporada, que se mide casi sin ruido. Así k sube a 1.58.
  Para el documento basta una frase: "estimamos k con variables instrumentales para corregir el
  sesgo de atenuación por error de medición del aire".
- **k por tipo de pitch** (fuente: `docs/02_features.md`, sección 2):

| Tipo | k vertical (IVB) | k horizontal (HB) |
|---|---|---|
| Recta | 1.50 | 1.64 |
| Sinker | 1.40 | 1.75 |
| Cambio | 1.30 | 2.06 |
| Curva | 1.19 | 1.67 |
| Slider | **0.68** | 1.22 |

- **Lectura física:** la slider casi no depende del giro para moverse verticalmente (mucho giro de
  bala, *gyro*), así que el aire le quita poco. El HB del cambio es lo más sensible.
- **Validación:** después de convertir, la recta del mismo pitcher queda a +0.11 in de IVB entre las
  dos altitudes, contra −3.83 in sin convertir.

### 1.4 Entorno LMB

- En altitud **todo vale más en carreras** salvo el jonrón. Carreras por media entrada: 0.53 a nivel
  del mar contra 0.81 en altitud extrema (`docs/03_target.md`, sección 1).
- **Ponerse adelante vale más en la CDMX:** un strike en 0-0 vale 0.043 carreras ahí y 0.034 a nivel
  del mar.
- **El acarreo:** con el mismo contacto (100 mph, 28°), en altitud extrema la pelota vuela 34 ft más
  y es jonrón 14.9 puntos más seguido (D-021, `reportes/evidencia_acarreo.json`).

**Referencias de la convocatoria que sí usamos:** Tango et al. (2007) para los pesos lineales; Huang
y Hsu (2021) para la H4 (forma sobre spin); SABR, *High altitude offense*, para la H3 (flies en
altura). La cifra de Alan Nathan sobre Coors Field viene de la convocatoria; si se cita, que sea así.
**No citen un paper que nadie del equipo haya leído.**

---

## 2. Datos y limpieza (media página)

- 635,002 pitches de la LMB, 2024–2026. Entrenamiento 2024–2025 (499,398); prueba 2026 (135,604).
- **No se borró ninguna fila ni se inventó ningún dato.** Cada problema queda marcado con una bandera
  y un valor mal medido se anula sin tirar el pitch. 99.69 % de los pitches sirven para Stuff+.
- **Por qué importa para la altitud:** borrar filas o imputar promedios sesgaría justo la comparación
  entre estadios.
- **Detalles que vale mencionar:**
  - Movimiento expresado **hacia el lado del brazo**, para juntar zurdos y derechos.
  - 1,342 pitches **reclasificados** por su forma a nivel del mar, dentro del repertorio del mismo
    pitcher.
- Fuente: `docs/01_limpieza.md`, `docs/02_features.md`.
- **Limitación honesta:** algunas estadísticas de la limpieza (mediana por pitcher para detectar
  valores mal medidos) usaron las tres temporadas. Es una fuga menor que no toca el resultado del
  pitch; se puede mencionar en fronteras.

---

## 3. El target: xRV (valor esperado en carreras)

Es lo que predicen todos los modelos. Explíquenlo en tres pasos (fuente: `docs/03_target.md`):

1. **Valor de cada desenlace.** Regresión de las carreras de cada media entrada completa sobre sus
   desenlaces (26,536 medias entradas de 2024–2025). Se usa regresión porque **el dataset no trae
   corredores en base**, y el método clásico (RE24) los necesita.
2. **Valor de cada conteo.** Promedio del desenlace final de los turnos que pasaron por ese conteo.
3. **Valor de cada pitch:**
   - si el turno sigue: valor del conteo después − valor del conteo antes;
   - si el turno termina: valor del desenlace − valor del conteo antes;
   - si es bola en juego: el desenlace se reemplaza por su **valor esperado** según velocidad de
     salida, ángulo y dirección. Lo da un modelo entrenado sin ver ese batazo (predicción cruzada).

**Fórmula para el documento:**

xRV_pitch = V(estado después) − V(estado antes), y para la bola en juego
V(después) = E[valor | velocidad de salida, ángulo, dirección].

- **Neutral contra local.** El xRV *neutral* valúa todo con los pesos de nivel del mar: sirve para
  comparar pitchers entre estadios. El *local* usa los pesos de su altitud.
- **Por qué el modelo nulo "por conteo" casi no mejora a la media:** el target ya descuenta el conteo
  (es diferencia de valor entre conteos). Eso es intencional y hay que decirlo, porque la convocatoria
  propone ese modelo nulo.

---

## 4. Decisiones de modelado

### 4.1 Arquitectura en dos etapas (D-001)

1. **Traductor físico:** lleva el movimiento de cada pitch al aire de nivel del mar,
   `ivb_sea_level = IVB ÷ air_ratio^k_ivb` (igual con HB).
2. **Modelo de resultado:** predice el valor del pitch con esa forma neutral.

**Por qué no poner la altitud como una variable más:** el modelo aprendería que "menos movimiento =
peor" y castigaría al pitcher por el estadio donde lanzó. Con el traductor, el mismo pitch vale lo
mismo en cualquier estadio. Además permite el **contrafactual**: el mismo pitch lanzado con el aire
de la CDMX y con el de la costa.

### 4.2 Las tres piezas

| Pieza | Variables | Modelo |
|---|---|---|
| **Stuff+** | Forma a nivel del mar (IVB, HB), velocidad, spin, eje, salida (altura, lado), extensión, VAA relativo; diferencias contra la recta del pitcher (velocidad, IVB, HB, eje, distancia de salida, extensión); tipo de pitch, mano, mismo lado que el bateador | 5 modelos por componentes (abajo) |
| **Location+** (de Ben, D-039) | Altura y lado en el plato, dentro o fuera de la zona, bolas, strikes, outs, entrada, mitad de la entrada, manos de pitcher y bateador; la altitud se fija en nivel del mar al predecir (D-040). **No ve el tipo de pitch** | Árbol de resultados: 6 modelos XGBoost (abajo) |
| **Pitching+** | Las predicciones de Stuff+ y Location+ | Regresión lineal: 0.78 × Stuff + 0.94 × Location |

**Stuff+ por componentes (D-027).** En vez de predecir el xRV directo, se predicen cinco cosas y se
combinan con el valor promedio de cada desenlace (V):

Stuff = P(swing) × [P(whiff) × V(whiff) + (1 − P(whiff)) × (P(foul) × V(foul) + (1 − P(foul)) × (valor del batazo − conteo del batazo))] + (1 − P(swing)) × [P(strike) × V(strike) + (1 − P(strike)) × V(bola)]

- P(whiff) es *dado que hubo swing*; P(foul), *dado que hubo contacto*; P(strike), *dado que no hubo
  swing*.
- **Por qué componentes si empatan con el directo:** explican el porqué de cada pitch (genera
  fallos, roba strikes…). Eso es lo que usa la ficha y lo que pide el reto de "arsenal". El whiff es
  el componente con más señal.
- Esto cubre los targets multi-objetivo de la convocatoria: P(whiff), P(called_strike) y xRunValue.
  P(chase) queda implícito en Location+ (el swing depende de la ubicación). Contacto débil, rolling y
  barril entran a través del valor esperado del batazo. **No modelamos P(out en el turno) por
  separado; si se menciona, que sea como frontera.**

**Location+ como árbol de resultados (D-039).** Seis modelos predicen qué pasa con el pitch según dónde
cae: P(swing), P(whiff | swing), P(strike cantado | toma), P(golpeado | toma sin strike), P(foul |
contacto) y el resultado en juego (out, 1B, 2B, 3B o HR). Con eso salen dos cifras por pitch:

- **xCSW** = P(strike cantado) + P(whiff);
- **xRV** = Σ P(resultado) × valor del resultado en esa cuenta, con los valores de cuenta de una
  cadena de Markov (`run_value.py`).

**Versión neutral (D-040):** el modelo de Ben usa la altitud como variable. Con su altitud real, el
mismo pitcher salía 1.00 carreras por 100 peor en la CDMX que a nivel del mar: lo castigaba por el
estadio. Por eso cada pitch se predice como si fuera a nivel del mar, igual que nuestro Stuff+.

### 4.3 Por qué estas variables

- **Recta de referencia (D-014):** los secundarios se juzgan contra la recta. La referencia mezcla
  la recta del mismo juego con la de la temporada, con peso n ÷ (n + k). Es un **estimador de
  encogimiento empírico-bayesiano**: con pocas rectas en el juego, pesa más la de temporada.
- **VAA relativo (D-012):** el ángulo de llegada crudo depende de la altura a la que llega el pitch,
  que es ubicación. Se usa el VAA menos el esperado a esa altura, que mide el rasgo del pitcher.
- **Lo que se probó y no entró (D-035):** dependencia del Magnus, movimiento total, ángulo horizontal
  relativo y tamaño del arsenal. Mejoraban por pitch pero **empeoraban el orden de los pitchers**.
  Sospecha: el ángulo horizontal mete ubicación en Stuff+.
- **Spin solo no basta (H4):** con el mismo spin, el movimiento cambia el resultado. El spin solo da
  un AUC de whiff de 0.546 en rectas contra 0.587 con velocidad y movimiento
  (`docs/hipotesis_h4.md`).

### 4.4 Algoritmo y función de pérdida

- **Gradient boosting por histogramas** (scikit-learn `HistGradientBoosting`), de la misma familia
  que LightGBM, que menciona la convocatoria.
- **Funciones de pérdida:**
  - componentes de sí/no (swing, whiff, foul, strike): **log loss** (entropía cruzada binaria);
  - valor del batazo: **error cuadrático**;
  - Location+: **log loss** en sus cinco cabezas de sí/no y **log loss multiclase** en el resultado en
    juego.
- **Hiperparámetros de Stuff+:** tasa de aprendizaje 0.05, 15 hojas por árbol, mínimo 1,000 pitches
  por hoja y regularización L2 de 1.0.
- **Hiperparámetros de Location+ (XGBoost, los de Ben):** tasa 0.05, profundidad 6, mínimo 50 de
  peso por hoja, 80 % de filas y de columnas por árbol, L2 de 1.0, hasta 2,000 árboles con *early
  stopping* de 50 rondas sobre el 10 % de los juegos.
- **Número de árboles:** se entrena con el 80 % de los pitchers y se elige el número de árboles que
  minimiza el error en el 20 % de pitchers que el modelo no vio (*early stopping* agrupado por
  pitcher). Árboles finales de Stuff+: swing 502, whiff 418, strike 401, foul 98, batazo 22. De
  Location+: swing 303, whiff 199, strike cantado 259, golpeado 257, foul 148, en juego 99.
- **Por qué gradient boosting y no una red o un modelo bayesiano:** capta interacciones no lineales
  (velocidad × movimiento × tipo) sin suponer una forma, con datos tabulares grandes, y se puede
  explicar por componentes. Un modelo jerárquico bayesiano quedó como trabajo futuro (D-002).

---

## 5. Definición formal de la escala

La convocatoria define **Stuff+ = 100 + 10 × z(score)**. En nuestro caso el score está en carreras
que permite el pitcher, donde **menos es mejor**, así que se invierte el signo:

**Stuff+ = 100 − 10 × (valor − media) ÷ desviación**

Usamos tres versiones, y el documento debe decir cuál es cuál:

| Dónde | Valor | Media y desviación |
|---|---|---|
| **Por pitcher** (ficha, tabla de la liga) | Promedio por 100 pitches del pitcher en la temporada (300+ pitches) | Media de la temporada; desviación entre pitchers |
| **Location+ por pitcher** | Mitad CSW y mitad RV, cada uno contra la liga en la misma cuenta | Ver la fórmula abajo |
| **Por pitch dentro del arsenal** | Promedio del pitcher con ese tipo (100+ pitches) | Media y desviación de ese tipo de pitch en esa temporada |
| **Simulador** (un perfil escrito a mano) | Valor del perfil promedio ingresado | Media y desviación de los perfiles promedio de la liga de ese tipo |

- **Normalización por temporada (D-024):** el ambiente de carreras cambia cada año (10.4 carreras por
  juego en 2024, 12.1 en 2025 y 11.1 en 2026). Centrar por temporada hace que 100 sea siempre "la
  media de ese año".
- **Por qué el simulador compara contra perfiles y no contra pitches sueltos:** el coach escribe un
  perfil promedio. Un pitch suelto trae la variación de cada lanzamiento, así que un perfil limpio
  se vería élite. Con perfiles, el pitch mediano de cada tipo queda entre 96 y 102.
- **Location+ (fórmula de Ben):** a cada pitch se le resta el promedio de la liga en su cuenta (xCSW y
  xRV), se promedia por pitcher y se estandariza: z_CSW = residuo de xCSW ÷ desviación,
  z_RV = −residuo de xRV ÷ desviación, z = 0.5 · z_CSW + 0.5 · z_RV, y **Location+ = 100 + 10 · z ÷
  desv(z)**. Ajustar por cuenta evita acreditarle al pitcher los conteos en que vive.
- **Distribución real por pitcher** (p10 / p50 / p90, 2025): Stuff+ 89 / 100 / 115; Location+ 87 /
  101 / 113; Pitching+ 88 / 101 / 114. La convocatoria dice "120+ élite (percentil ~97)". En nuestros
  datos, 120 o más de Stuff+ lo tiene el 4 % de los pitchers-temporada, y de Pitching+ el 3 %:
  coincide con lo que esperan.

---

## 6. Validación fuera de muestra

### 6.1 Los tres holdouts que pide la convocatoria

| Holdout | Cómo lo hicimos | Fuente |
|---|---|---|
| **Pitcher holdout** | Validación cruzada de 5 pliegues **agrupando por pitcher**: cada pitch de 2024–2025 lo predice un modelo que nunca vio a su pitcher | `src/modelo.py` |
| **Season holdout** | Entrenado con 2024–2025, evaluado en 2026 | `reportes/etapa_04_modelo_v2.json` |
| **Park holdout** | Los datos no traen estadio, solo categoría de altitud. Se entrena **sin ningún pitch de altitud extrema** (y sin el pitcher) y se evalúa en altitud extrema (D-037) | `reportes/etapa_06_validacion_estadio.json` |

**Intervalos:** todos los IC 95 % remuestrean **pitchers completos** (1,000 veces, semilla 2026).
Los pitches de un mismo pitcher no son independientes; remuestrear pitches daría intervalos falsamente
angostos. Una frase en el documento lo justifica.

### 6.2 Calidad contra el modelo nulo (RMSE y calibración)

Fuente: `reportes/etapa_06_metricas_documento.json`.

| | RMSE modelo nulo (promedio por conteo) | RMSE Pitching+ | Diferencia (IC 95 %) | Pendiente de calibración |
|---|---|---|---|---|
| Pitcher holdout (2024–2025) | 0.14448 | 0.14055 | −0.0041 a −0.0038 | 1.00 |
| Season holdout (2026) | 0.14807 | 0.14408 | −0.0042 a −0.0038 | 1.03 |

- **Calibración:** se ordenan los pitches por su predicción en 10 grupos y se compara el promedio
  predicho con el real. Pendiente 1 = calibrado. En 2026 los deciles van de −5.0 a +6.7 carreras por
  100 predichas contra −5.1 a +6.8 reales. Esta gráfica luce muy bien en el documento.
- **Ojo:** en el pitcher holdout la pendiente de 1.00 sale en parte por construcción, porque los
  pesos de Pitching+ se ajustaron con esas mismas predicciones. La de 2026 sí es fuera de muestra.
- **Escala de la mejora:** el RMSE baja poco en términos absolutos porque **un pitch suelto es casi
  todo azar** (desviación del xRV: 0.145). Por eso el documento reporta también la mejora del error
  cuadrático en %: +5.3 % de Pitching+ en 2026 contra +0.11 % de la mejor base lineal.

### 6.3 La escalera de modelos base (D-020)

Ningún resultado cuenta si no le gana a un modelo más simple. Resultados en 2026 (`docs/04_modelo.md`):

| Prueba | Resultado |
|---|---|
| Por pitch | **Stuff+, Location+ y Pitching+ le ganan** a la media, al promedio por conteo y a las dos regresiones lineales, con intervalo fuera de cero |
| Por pitcher, misma temporada | **Pitching+ le gana a las dos lineales** con intervalo fuera de cero: r 0.55, error 0.61 contra 0.72 de la lineal observada (−0.19 a −0.03) y 0.75 de la lineal a nivel del mar (−0.23 a −0.05) |
| A futuro (predecir 2026 con 2024–2025) | **Ninguno le gana** a la historia del pitcher encogida hacia la media |
| Altitud (mismo pitcher en las dos altitudes) | El xRV real cambia 0.57 carreras por 100; **Stuff+ solo 0.05** (r 0.92 entre altitudes) y Pitching+ 0.07 |

**Escriban los empates y las derrotas.** Un jurado técnico confía más en un documento que dice qué no
funcionó. La explicación de la derrota a futuro: el contacto es ruido (DIPS) y Location+ no se repite
de un año a otro.

### 6.4 Park holdout (D-037)

En 139,277 pitches de altitud extrema, de 725 pitchers, con modelos que no vieron ni al pitcher ni la
altitud extrema. Mejora del error contra el promedio por conteo:

- Stuff+: +0.13 % (0.08 a 0.18);
- Location+ (de Ben, también entrenado sin altitud extrema): +4.91 % (4.64 a 5.21);
- Pitching+: +4.97 % (4.70 a 5.25).

Pasa la regla. Entrenar con altitud extrema no cambia Pitching+ (−0.04 a +0.05). **Hallazgo:** el modelo
sin altitud es optimista en la CDMX por unas 0.3 carreras por 100 pitches, del tamaño de la pérdida
por altitud medida aparte. Las dos mediciones coinciden.

### 6.5 Higiene: cuántas veces miramos 2026

2026 se miró **seis veces**, todas declaradas en la bitácora: la exploración, el modelo congelado
(D-030), la proyección (D-032), la versión 2 (D-035) y la versión 3 local y neutral (D-039 y D-040).
El Location+ de Ben lo adoptó el equipo antes de mirar 2026, y la versión neutral corrige un
problema de principio (castigaba al pitcher por el estadio), no un resultado de 2026. Desde D-025 nada se eligió con 2026; las
elecciones se hicieron con 2024 → 2025. Conviene una frase así en el documento: muestra que no
buscamos el resultado hasta encontrarlo.

---

## 7. Resultados de altitud (integración arsenal + altitud)

### 7.1 Delta de Stuff+ por tipo de pitch entre el Harp Helú y nivel del mar

Mismo pitcher y mismo pitch en las dos altitudes, 2024–2025, 50+ pitches por lado. Pérdida real en
carreras por 100 pitches (xRV sin contacto) y su equivalente en puntos de Stuff+, en la **escala
oficial del arsenal** (la de las fichas, los archivos de scores y el simulador). Fuente:
`reportes/etapa_06_scores.json`.

| Tipo | Pares | Pérdida real por 100 (IC 95 %) | Delta de Stuff+ (IC 95 %) |
|---|---|---|---|
| Recta | 210 | 0.40 (0.27 a 0.53) | **−13.0** (−17.3 a −8.8) |
| Sinker | 97 | 0.32 (0.14 a 0.49) | **−13.3** (−20.5 a −6.1) |
| Cambio | 51 | 0.32 (0.09 a 0.58) | **−9.7** (−17.5 a −2.8) |
| Slider | 129 | 0.18 (−0.03 a 0.39) | −6.9 (−14.8 a +1.1) |
| Curva | 35 | 0.02 (−0.24 a 0.28) | −0.7 (−9.5 a +8.1) |

- **Lectura:** pierden las que dependen del efecto Magnus (rectas, sinkers, cambios); slider y curva
  casi no, y su intervalo toca cero.
- **H2 de la convocatoria (el cambio gana valor relativo en altura): no se sostiene.** El cambio
  pierde lo mismo que el sinker en carreras. Hay que decirlo así.
- **Por qué "sin contacto":** el xRV sin contacto reemplaza el valor de cada batazo por el promedio
  de su conteo. Se usa porque el contacto es casi todo ruido (idea DIPS). El de un mismo pitch se
  repite r = 0.44 de un año a otro, contra 0.17 del total.

### 7.2 Riesgo de contacto duro y jonrón

Fuente: `reportes/etapa_06_riesgo_contacto.json` (2024–2025, descriptivo).

| En altitud extrema contra nivel del mar | Altura | Mar | Diferencia (IC 95 %) |
|---|---|---|---|
| Jonrones por fly | 16.1 % | 12.8 % | +3.3 puntos (2.2 a 4.6) |
| Contacto duro (95+ mph) | 25.5 % | 22.4 % | +3.0 puntos (2.3 a 3.8) |
| Carreras por 100 batazos | 6.9 | 3.1 | +3.7 (3.0 a 4.5) |

- **Un fly vale 0.136 carreras en altura y 0.039 a nivel del mar** (+0.097). Un rolling cambia poco
  (+0.020). Apoya la **H3**: el pitcher de rolling vale más en altura.
- Por tipo, con el mismo pitcher, las rectas y sinkers pierden en carreras por batazo (+3.4 y +4.5
  por 100, intervalos fuera de cero). Cutter, curva y cambio no tienen suficientes pitchers para
  reportarse.

### 7.3 El pasaporte de altitud (D-034) y el riesgo por arsenal (D-036)

- **Pasaporte:** traduce un pitch visto a nivel del mar al aire de la CDMX y estima cuánto pierde.
  - La forma se predice bien: el error es 7 veces menor que suponer que el pitch no cambia.
  - Pero **no le gana a aplicar la pérdida promedio de su tipo**, y exagera la pérdida de las rectas.
  - Por eso en la ficha y el simulador solo se usa para **ordenar** (percentil).
- **Riesgo por arsenal** (uso × pérdida promedio del tipo): ordena a los pitchers (r 0.11, intervalo
  apenas fuera de cero) pero **no como cifra exacta**. Se muestra en tercios.

### 7.4 Perfil físico ideal: lo que sí y lo que no

Fuente: `reportes/etapa_06_perfil_ideal.json`.

- **Dentro de un mismo tipo de pitch, ninguna característica tiene evidencia real** de perder menos
  en altura. Todos los intervalos tocan cero. El modelo cree que las rectas con más IVB y más
  dependencia del Magnus pierden más (r 0.66–0.74), y los datos apuntan al mismo lado, pero sin
  significancia.
- **La evidencia está entre tipos y en el contacto:**
  - un arsenal que no dependa solo de rectas y sinkers;
  - una slider o curva de calidad;
  - inducir rolling, porque el fly cuesta 3.5 veces más.
- **Redacción sugerida:** "Con los datos de dos temporadas, el perfil ideal se define por la mezcla
  del arsenal y el tipo de contacto, no por un rasgo físico dentro de cada tipo de pitch."

---

## 8. Alcance y fronteras del modelo

Usen esta lista; cada punto tiene respaldo:

1. **No predice el año siguiente mejor que la historia del pitcher.** Para pitchers con historia, la
   historia encogida gana; Stuff+ sirve donde no hay historia (64 de 178 pitchers en 2026 no la
   tenían).
2. **El aire se mide por juego, no por pitch**, y la altitud viene en tres categorías, no por
   estadio. El "park holdout" es un *altitude holdout*.
3. **No hay corredores en base** en los datos: el valor de cada desenlace es un promedio de
   situaciones. Robos, wild pitches y pickoffs no se le cargan a nadie.
4. **Stuff+ por pitcher empata con la regresión lineal**; gana por pitch. Pitching+ sí le gana por
   pitcher, gracias al Location+ ajustado por cuenta.
5. **El costo de altitud de un pitcher específico no es preciso**: se da en tercios.
6. **2026 es una temporada parcial** (178 pitchers con 300+ pitches).
7. **Asociación, no causalidad:** que la slider pierda poco en altura no prueba que usarla más mejore
   el resultado. El análisis causal (el *causal forest* que sugiere la convocatoria) quedó fuera.
8. **El simulador extrapola** fuera del rango de la liga (lo marca en pantalla).
9. **Fuga menor en la limpieza:** algunas medianas por pitcher usaron las tres temporadas.

---

## 9. Preguntas difíciles del jurado (para preparar)

| Pregunta | Respuesta corta |
|---|---|
| ¿Por qué Stuff+ mejora tan poco por pitch (0.15 %)? | Un pitch suelto es casi azar. Lo que importa es que le gana a la lineal con intervalo fuera de cero y que es estable por pitcher (r 0.83 entre años). |
| ¿Por qué no pusieron la altitud como variable? | Castigaría al pitcher por el estadio. El traductor físico separa al pitcher del aire (D-001), y el park holdout muestra que el modelo funciona en la CDMX sin haberla visto. |
| ¿Cómo saben que k es correcto? | Se estimó con el mismo pitcher en distintos aires, corregido por atenuación. Después de convertir, la recta del mismo pitcher queda a +0.11 in entre altitudes. Y pasado a densidad da 1.05 para la recta y 1.10 en la liga, contra 1.11 que predice la física. |
| ¿Su k de 1.6 no contradice la física? | Ese k está en frenado, no en densidad. En densidad es 1.10, que es lo que predicen Magnus ∝ ρ y el menor tiempo de vuelo. |
| ¿Por qué no le ganan a la historia del pitcher? | Porque el resultado incluye contacto y ubicación, que se repiten poco. Stuff+ es la parte estable y la única disponible para un pitcher nuevo. |
| ¿Miraron 2026 muchas veces? | Seis, declaradas. Nada se eligió con 2026 desde D-025. |
| ¿Por qué el Location+ no ve el tipo de pitch? | Mide qué tan buen lugar es ese para un pitch promedio de la liga; el tipo de pitch es Stuff+. Así no se cuenta dos veces. |
| ¿Qué cambiaría en el reclutamiento? | Las rectas y sinkers de un agente libre pierden ~13 puntos de Stuff+ en el Harp Helú; uno con slider o curva de calidad pierde menos. Y un pitcher de rolling sufre menos el acarreo. |

---

## 10. Errores de redacción que hay que evitar

- **"Stuff+ predice el rendimiento futuro mejor que…"**: falso; empata o pierde contra la historia.
- **"Ajustado por estadio"**: es por categoría de altitud; no tenemos estadio.
- **"El cambio gana valor en altura"**: nuestros datos dicen que no (H2).
- **"Usar más la slider mejora el resultado"**: es una asociación, no lo probamos.
- **Llamar "mejora" a un empate.** Si el intervalo toca cero, es empate.
- **Dar el costo de altitud de un pitcher como cifra exacta.** Se da como tercio.
- **Inventar referencias o cifras de MLB.** Solo citen lo que leyeron.

---

## 11. Glosario rápido

- **IVB:** quiebre vertical inducido, en pulgadas; lo que sube o baja el pitch por el giro, sin la
  gravedad.
- **HB:** quiebre horizontal; aquí siempre hacia el lado del brazo.
- **VAA:** ángulo vertical con el que llega el pitch al plato.
- **Efecto Magnus:** fuerza que el giro le da a la pelota a través del aire.
- **xRV:** valor esperado en carreras de un pitch; negativo es bueno para el pitcher.
- **Log loss:** pérdida para probabilidades; castiga estar seguro y equivocado.
- **RMSE:** raíz del error cuadrático medio.
- **Calibración:** que una predicción de X se cumpla en promedio X.
- **Holdout:** datos que el modelo no vio al entrenar.
- **Validación cruzada agrupada:** pliegues que nunca parten a un mismo pitcher entre entrenamiento y
  prueba.
- **Bootstrap por pitcher:** repetir el cálculo remuestreando pitchers completos para obtener el
  intervalo.
- **Encogimiento (shrinkage):** acercar una estimación ruidosa hacia la media según cuánta muestra
  tiene.
- **Variable instrumental:** técnica para estimar una pendiente cuando la variable explicativa se
  mide con error.
- **DIPS:** la idea de que el pitcher controla poco lo que pasa con la pelota en juego.

## 12. Gráficas que conviene incluir

1. Mapa de movimiento de rectas: liga a nivel del mar con el mismo pitch trasladado a la CDMX (sale
   del simulador).
2. Barras del delta de Stuff+ por tipo de pitch con su intervalo (tabla 7.1).
3. Calibración por deciles en 2026 (sección 6.2).
4. Consistencia del mismo pitcher entre altitudes: xRV real contra Stuff+ (sección 6.3).
5. Captura de la ficha de un pitcher (aplicabilidad).
