# Bitácora de decisiones

Cada decisión importante queda aquí, la más reciente arriba. Si una decisión cambia, no se borra:
se agrega una nueva entrada que la reemplaza y se marca la anterior como *Reemplazada*.

**Formato:** fecha · decisión · por qué · alternativas descartadas · estado.

---

### D-035 · 2026-10-14 · Afinado de Stuff+ y Location+ (versión 2): regla fijada antes de probar
- **Qué se prueba:** se entrena con 2024 y se evalúa en 2025; 2026 no se toca.
  - **Hiperparámetros:** hojas mínimas de 200 o 1,000 pitches y 15 o 31 hojas por árbol. Hoy se usan
    1,000 y 15, que nunca se afinaron.
  - **Variables de Stuff+:** se agregan la dependencia del efecto Magnus, el movimiento total a nivel
    del mar, el ángulo horizontal relativo de llegada y el tamaño del arsenal. No se agrega nada que
    cambie con el aire.
- **Regla para cada pieza (Stuff+ y Location+):**
  - Gana la versión con menor error por pitch en 2025.
  - Se adopta solo si le gana a la versión 1 por pitch con intervalo fuera de cero y no empeora el
    error por pitcher.
  - Si ninguna cumple, se queda la versión 1.
- **2026:** si alguna pieza cambia, la versión 2 se congela y se mira en 2026 una vez, reportada como
  **cuarta mirada** junto a la versión 1, sin reemplazarla.
- **Resultado:** Stuff+ se queda en la versión 1. Las variables físicas mejoran por pitch, pero
  empeoran por pitcher con intervalo fuera de cero. Location+ pasa a 31 hojas (+0.05 a +0.09 puntos
  por pitch). En 2026 la versión 2 sube un poco por pitch y queda igual en lo demás. Detalle en
  `docs/04_afinado.md`.
- **Estado:** Vigente. El modelo oficial es la versión 2 y el afinado termina aquí.

### D-034 · 2026-10-14 · Pasaporte de altitud: reglas fijadas antes de probar
- **Qué:** con los pitches a nivel del mar de un pitcher, predecir cómo cambia cada uno en altitud
  extrema. Se hace en dos pasos:
  - **Forma:** movimiento × aire^k, con la mediana del aire en altitud extrema y el k de su tipo de
    pitch (D-016).
  - **Valor:** un Stuff+ local, con los mismos componentes que D-027 pero con el movimiento observado,
    evalúa el pitch traducido y el original. El costo es la diferencia.
- **Prueba:**
  - Pitchers con el mismo tipo de pitch en altitud extrema y a nivel del mar en 2024–2025, con 50+
    pitches en cada lado.
  - Los modelos no vieron al pitcher (5 pliegues por pitcher).
  - Intervalos por bootstrap de pitchers.
- **Reglas:**
  - **Forma:** el pasaporte gana si su error contra el movimiento real en altura es menor que (a)
    suponer que no cambia y (b) aplicar a todos la pérdida promedio de la liga, con intervalo fuera de
    cero.
  - **Valor:** el costo predicho cuenta si su correlación con el cambio real del xRV sin contacto
    (D-032) es positiva con intervalo fuera de cero. Además, su error debe ser menor que el de dar a
    todos el mismo costo promedio.
- **Estado:** Vigente.

### D-033 · 2026-10-14 · Stuff+ por tipo de pitch (arsenal)
- **Qué:** el Stuff+ de D-027 promediado por pitcher y tipo de pitch (100+ pitches), en escala 100
  dentro de cada tipo: una slider se compara contra las sliders de la liga.
- **Prueba (pares 2024 → 2025):**
  - cuánto se repite;
  - si predice el xRV sin contacto del año siguiente de ese pitch con intervalo fuera de cero;
  - si lo predice mejor que la historia de ese pitch.
- **Estado:** Vigente.

### D-032 · 2026-10-14 · Candidatos sin contacto para la proyección, agregados después de D-031
- **Contexto:** en D-031 ningún candidato le ganó a la persistencia.
- **Hallazgo (pares 2024 → 2025, 146 pitchers):** al separar el xRV de cada pitcher, la parte del
  contacto no se repite (r −0.03) y la parte sin contacto sí (r 0.50).
  - La parte del contacto es lo que valió cada bola en juego menos lo que vale un batazo promedio en
    ese conteo.
  - La parte sin contacto (bolas, strikes, whiffs y fouls) tiene confiabilidad entre mitades de 0.53
    a 0.58, contra 0.26 a 0.35 del total.
  - Es la idea de DIPS (McCracken): el pitcher controla sobre todo lo que pasa antes del contacto.
- **Candidatos nuevos:**
  - persistencia del xRV sin contacto;
  - xRV sin contacto con las tasas, Stuff+ y Location+.
- **Prueba:** la misma regla y la misma validación de D-031.
- **Confirmación con más datos:** se agregó después de ver que el error quedó cerca del cero. Dentro de
  cada temporada de 2024 y 2025, la primera mitad de los pitches de cada pitcher predice el xRV total de
  la segunda mitad.
  - Muestra: pitchers con 300+ pitches en la temporada, validación cruzada por pitcher e intervalos
    remuestreando pitchers.
  - El xRV sin contacto se adopta como base de la proyección solo si le gana al xRV total en error, con
    intervalo fuera de cero.
- **Advertencia:** se agregaron después de ver que D-031 no ganó. Si el ganador se mira en 2026, se
  reporta como segunda mirada del modelo de proyección (la primera fue D-030).
- **Estado:** Vigente.

### D-031 · 2026-10-14 · Proyección a futuro con tasas observadas: regla fijada antes de probar
- **Por qué:** el modelo congelado (D-030) no predice el año siguiente mejor que la historia del
  pitcher. Las tasas observadas (whiff, persecución, strike cantado, contacto) se estabilizan más
  rápido que el resultado en carreras y podrían predecir mejor.
- **Candidatos:**
  - persistencia encogida (base);
  - ridge con xRV, Stuff+ y Location+;
  - ridge con xRV y las tasas observadas;
  - ridge con todo lo anterior más los componentes predichos de Stuff+.
- **Prueba:**
  - Pares 2024 → 2025 con 300+ pitches en cada año.
  - Validación cruzada de 10 pliegues por pitcher, repetida 20 veces.
  - Intervalo por bootstrap de pitchers sobre las predicciones fuera de pliegue.
- **Regla:** gana el de menor error. Se adopta solo si le gana a la persistencia con intervalo fuera de
  cero; si no, la persistencia se queda.
- **2026:** el ganador se mira una vez en 2026 y se reporta como **segunda mirada**, junto al resultado
  de D-030, sin reemplazarlo.
- **Estado:** Vigente.

### D-030 · 2026-10-14 · Modelo de la etapa 4 congelado; 2026 se evalúa una sola vez
- **Qué:** con D-026 a D-029 queda fijo el modelo final (`src/modelo.py`). Se entrena con 2024–2025 y
  se evalúa en 2026 una sola vez. Se reporta lo que salga, gane o pierda.
- **Pruebas fijadas antes de correr:**
  - por pitch;
  - por pitcher, contra la lineal observada y contra la lineal a nivel del mar;
  - a futuro, contra la persistencia encogida;
  - consistencia entre altitudes.
- **Proyección a futuro (camino 3 del plan):**
  - Fórmula: xRV del año siguiente = a + b × xRV histórico + c × Pitching+.
  - Los pesos se ajustan solo con los pares de pitchers 2024 → 2025, usando predicciones de modelos que
    no vieron a cada pitcher.
- **Estado:** Vigente.

### D-029 · 2026-10-14 · Pitching+ es la suma pesada de Stuff+ y Location+
- **Por qué:**
  - Por pitch en 2025, la suma predice igual que un modelo único de Pitching+ (diferencia −0.11 a
    +0.01 puntos).
  - La suma explica el 80 % del Pitching+ de cada pitcher.
  - Siempre se puede desglosar, por ejemplo "108 = Stuff+ 115 y Location+ 101".
  - Evidencia: `docs/04_relacion_componentes.md`.
- **Pesos:** regresión del xRV de cada pitch sobre las dos predicciones. Se ajusta con 2024–2025 y
  predicciones de modelos que no vieron al pitcher.
- **Alternativas descartadas:** un tercer modelo con forma, ubicación, conteo y secuencia. No aporta
  nada medible y no se puede desglosar.
- **Estado:** Vigente.

### D-028 · 2026-10-14 · Location+ usa ubicación y conteo
- **Por qué:**
  - El conteo solo no le da crédito a ningún pitcher: varía 0.011 carreras por 100 entre pitchers,
    contra 0.28 de Location+.
  - Como contexto sí ayuda: la mejora por pitch sube de +3.47 % a +5.11 %, una diferencia de +1.5 a
    +1.7 puntos.
  - Por pitcher, las dos versiones ordenan casi igual (r 0.95).
  - Evidencia: `docs/04_relacion_componentes.md`, sección 7.
- **Alternativas descartadas:** Location+ sin conteo.
- **Estado:** Vigente.

### D-027 · 2026-10-14 · Stuff+ por componentes
- **Qué:** P(swing), P(whiff | swing), P(foul | contacto), P(strike cantado | toma) y valor del
  batazo. Se predicen solo con la forma a nivel del mar y se combinan con el valor promedio de cada
  desenlace.
- **Datos (entrenado en 2024, evaluado en 2025):**
  - Contra la lineal a nivel del mar (D-026): gana por pitch (+0.06 a +0.11 puntos) y empata por
    pitcher (error −0.026 a +0.022).
  - Contra el Stuff+ directo: empata por pitch (−0.01 a +0.03) y por pitcher.
- **Por qué componentes y no directo, si empatan:**
  - Da al cuerpo técnico el porqué de cada pitch: genera whiff, roba strikes o saca contacto débil.
    Eso es la integración del arsenal que pide el reto.
  - El whiff es el componente con más señal (−4.8 % de log loss contra la tasa base).
- **Alternativas descartadas:**
  - **Stuff+ directo:** empata y no explica el porqué.
  - **Lineal a nivel del mar:** pierde por pitch.
- **Estado:** Vigente. Evidencia: `docs/04_stuff_componentes.md`.

### D-026 · 2026-10-14 · La base justa de Stuff+ es la lineal con forma a nivel del mar
- **Por qué:**
  - La lineal base de D-020 usa el movimiento observado, que trae el efecto del aire.
  - En 2025 le gana a la misma lineal a nivel del mar por pitcher (error 0.455 contra 0.476,
    diferencia +0.006 a +0.036). Su ventaja viene de "saber" el estadio, justo lo que D-001 quita.
  - Comparar contra ella castiga a cualquier Stuff+ que cumpla D-001.
- **Advertencia:** la decisión se tomó después de ver el resultado de 2025. Por eso no reemplaza la
  regla vieja: se reportan las dos bases, la lineal observada y la lineal a nivel del mar.
- **Estado:** Vigente.

### D-025 · 2026-10-11 · Desde la exploración de la etapa 4, 2026 no se usa para elegir nada
- **Por qué:** la exploración ya mostró los resultados de 2026. Ajustar el modelo hasta ganar ahí
  inflaría el resultado. Toda elección se hace entrenando con 2024 y evaluando en 2025; 2026 se usa
  una sola vez con el modelo congelado y se reporta lo que salga.
- **Alternativas descartadas:** seguir afinando contra 2026.
- **Estado:** Vigente desde 2026-10-14; se aplicó en D-026 a D-030.

### D-024 · 2026-10-07 · Las comparaciones por pitcher se centran por temporada
- **Por qué:** el ambiente de carreras cambia entre años (10.4 carreras por juego en 2024, 12.1 en
  2025, 11.1 en 2026). Stuff+ se define contra el promedio de su temporada. Sin centrar, la persistencia
  encogida salía peor que la media porque arrastraba el nivel de 2025.
- **Efecto en la elección de D-023:** ninguno; con y sin centrar gana la misma versión.
- **Estado:** Vigente.

### D-023 · 2026-10-07 · El contacto se valúa con velocidad de salida, ángulo y dirección
- **Por qué:** es lo que pidió la regla fijada en el plan: su xRV de 2024–2025 predice mejor el valor
  real de 2026 (r 0.263 contra 0.250 sin dirección).
- **Advertencia:** es casi un empate (IC de la diferencia −0.044 a +0.076) y la versión sin dirección
  es el doble de estable entre mitades (0.250 contra 0.131). En la etapa 5 se entrena el modelo con
  ambos targets como prueba de sensibilidad.
- **Estado:** Vigente, a revisar en la etapa 5.

### D-022 · 2026-10-07 · Target: xRV neutral y local con pesos lineales por regresión
- **Qué:** valor de cada desenlace por regresión sobre medias entradas completas de 2024–2025; valor
  del conteo como promedio del desenlace final; valor del pitch como cambio de conteo; bola en juego
  con valor esperado por predicción cruzada. Error, sacrificio y bola ocupada valen como out.
- **Por qué:** no hay corredores en base para RE24; la regresión sobre entradas completas no los
  necesita. Detalle en `03_plan_target.md` y `03_target.md`.
- **Alternativas descartadas:** carreras esperadas solo por outs; pesos publicados de MLB.
- **Estado:** Vigente.

### D-021 · 2026-10-07 · Nueva herramienta: jonrones regalados por el aire
- **Qué:** probabilidad de jonrón por batazo entrenada a nivel del mar y aplicada en altura; la
  diferencia son los jonrones que regaló el aire, por pitcher y por bateador.
- **Por qué:** con el mismo contacto (100 mph, 28°), en altitud extrema la pelota vuela 34 ft más
  (IC 95 % 31–38) y es jonrón 14.9 puntos más seguido (IC 95 % 10.0–19.6)
  (`src/evidencia_acarreo.py`). Separa al pitcher al que le pegaron fuerte del que castigó el aire.
- **Límite:** sin estadio ni medidas de bardas, estimamos acarreo, no distancia a la barda.
- **Estado:** Vigente; se construye en la etapa 6.

### D-020 · 2026-10-07 · Todo modelo se compara contra modelos base, fuera de muestra
- **Qué:** ningún resultado cuenta si no le gana a un modelo más simple en 2026, con intervalo por
  pitcher que no toque cero. La escalera de modelos base, de menor a mayor:
  1. **Media de la liga:** predecir siempre el promedio del entrenamiento ("predecir mejor que la media").
  2. **Media por conteo:** el valor del pitch depende mucho de bolas y strikes.
  3. **Media por tipo de pitch y mano:** lo que vale "una slider de derecho" en general.
  4. **Regresión lineal** con velocidad, movimiento y extensión: el modelo simple que cualquier
     equipo puede llevar.
  5. **Alternativa descartada en D-001:** un solo modelo con `altitude_category` como variable.
     Si nuestro traductor físico no le gana, no se justifica.
- **A nivel pitcher** (lo que usa el club): el Stuff+ de 2024–2025 debe predecir los resultados de
  2026 del pitcher mejor que sus propios resultados de 2024–2025 (whiff y valor en carreras) y que la
  media de la liga. También medimos estabilidad: correlación entre dos mitades de sus pitches.
- **Reglas:** los hiperparámetros se eligen con validación cruzada dentro de 2024–2025 agrupando por
  pitcher; 2026 se usa una vez. Se reportan todas las comparaciones planeadas, también las que
  pierden. Los efectos se dan en unidades de béisbol (puntos de whiff, carreras por 100 pitches).
- **Por qué:** sin modelos base no se puede saber si el modelo aprende algo o solo repite promedios;
  es lo primero que preguntará un jurado técnico.
- **Estado:** Vigente; se implementa con el target en la etapa 3 y los modelos en la etapa 4.

### D-019 · 2026-10-06 · Retroalimentación del experto: minimizar al bateador
- **Qué:** Pitching+ y las herramientas se orientan a contener al bateador: mapa de daño por zona con
  wOBA, bateador contra forma del pitch (no la pareja exacta, que tiene mediana de 6 pitches),
  asistente de bullpen durante el juego y encaje de bateadores con la altura. Stuff+ se queda sin
  bateador, como pide la convocatoria.
- **Por qué:** recomendación de un lanzador con experiencia; detalle en `retroalimentacion_experto.md`.
- **Estado:** Vigente.

### D-018 · 2026-10-06 · La zona usa la misma caja que la bandera del dataset
- **Por qué:** medimos la caja de `in_strike_zone`: 1.62–3.21 ft de alto y ±0.708 ft. Usarla hace que
  nuestra cuadrícula coincida con la bandera en todos los pitches salvo 83 en el borde.
- **Alternativa descartada:** caja de 1.5–3.5 ft y ±0.83 ft (no coincidía en 73 mil pitches).
- **Estado:** Vigente.

### D-017 · 2026-10-06 · Sweeper: no hay corte natural; se usa 12 in sobre la forma a nivel del mar
- **Por qué:** la mezcla de dos normales da una D de Ashman de 1.59 (< 2): los grupos se enciman. Es la
  salida prevista en D-013.
- **Pendiente:** la conversión cierra casi la mitad de la brecha de sweepers entre altitudes (7.3 %
  contra 12.6 %), no toda. Siguiente paso: un k que dependa del tamaño del movimiento.
- **Estado:** Vigente.

### D-016 · 2026-10-06 · El exponente k se estima con variable instrumental
- **Por qué:** el aire de cada juego se mide con ruido, y eso achica la pendiente (atenuación). La
  primera estimación (k = 1.37) dejaba al mismo pitcher con ~1 in menos de movimiento después de
  convertir. Instrumentando el aire del juego con el aire típico de su categoría y temporada, k sube a
  1.58 y la diferencia que queda es casi nula (sinker −0.04 in de HB, recta +0.11 in de IVB).
- **Además:** k por tipo de pitch y componente, porque el horizontal responde más que el vertical
  (1.67 contra 1.33 en la liga). Un tipo con menos de 100 pitchers usa el de la liga.
- **Estado:** Vigente.

### D-015 · 2026-10-06 · El orden de las filas es el orden cronológico de los pitches
- **Por qué:** dentro de cada juego la entrada nunca retrocede (99.94 %) ni el conteo de cada turno
  (99.99 %); los juegos vienen por fecha (el siguiente juego de un bateador es en la misma altitud
  74 % de las veces contra 36 % al azar). La limpieza guarda el orden en `pitch_seq`.
- **Corrige:** lo que dijimos en `02_plan_features.md` y en `00_contexto_y_approach.md`: que no había
  orden de pitches.
- **Estado:** Vigente.

### D-014 · 2026-10-01 · Recta de referencia: mezcla ponderada con peso estimado de los datos
- **Qué:** referencia = combinación de la recta del mismo juego y la del pitcher en esa altitud y
  temporada, con peso n / (n + k). k = varianza dentro del juego ÷ varianza real entre juegos:
  **k = 2.4 para velocidad y 4.8 para IVB**.
- **Por qué (estadística):** es el estimador de encogimiento empírico-bayesiano; minimiza el error
  cuadrático al combinar una estimación ruidosa con una referencia estable.
- **Por qué (béisbol):** la recta cambia de verdad entre salidas (±0.77 mph, ±1.1 in de IVB) y el
  bateador juzga contra la recta de hoy. El respaldo es de la misma altitud, así no mezcla aires.
- **Alternativas descartadas:** recta de toda la temporada (sesgo de −0.9 in en altitud y +1.0 a
  nivel del mar); solo mismo juego con mínimo de 5 (descarta 17 % de las salidas).
- **Prueba pendiente:** validación de mitades dentro de cada juego.
- **Valores finales (etapa 2):** medidos sobre la recta principal de cada pitcher, k = 1.9 velocidad,
  4.1 IVB, 3.4 HB, 5.3 eje, 0.9 release y extensión. El reporte de decisiones daba 2.4 y 4.8 porque
  usaba todas las four-seam y sinkers.
- **Estado:** Vigente. Reemplaza la propuesta de "mínimo 5" del plan.

### D-013 · 2026-10-01 · Sweeper vs slider: corte de los datos sobre la forma a nivel del mar
- **Por qué:** con el umbral fijo sobre el movimiento observado, 16 de 19 pitchers cuya slider es
  sweeper a nivel del mar dejan de serlo en altitud. La etiqueta debe ser del pitcher, no del
  estadio; si no, cualquier comparación entre estadios tiene sesgo de selección.
- **Si no hay un corte natural:** se usa 12 in sobre la forma a nivel del mar y se reporta.
- **Prueba pendiente:** % de sweepers parecido entre altitudes; misma etiqueta en casa y de visita.
- **Estado:** Vigente.

### D-012 · 2026-10-01 · Stuff+ usa el VAA relativo, no el VAA ni el ángulo de salida crudos
- **Por qué:** la altura de llegada explica 54–80 % del VAA y 49–71 % del ángulo de salida; ambos
  meten ubicación en Stuff+. El VAA relativo (VAA menos el esperado para ese tipo de pitch a esa
  altura) tiene correlación 0 con la altura, depende de rasgos del pitcher (altura de release −0.77,
  IVB 0.27) y predice whiffs: 21.9 % → 36.8 % en rectas altas, de las más inclinadas a las más planas.
- **Alternativas descartadas:** VAA crudo; ángulo de salida (era la propuesta del plan y tenía el
  mismo problema).
- **Prueba pendiente:** ablación con y sin `vaa_rel` en el holdout de pitchers.
- **Estado:** Vigente.

### D-011 · 2026-09-30 · Un valor mal medido se anula; la fila se conserva
- **Por qué:** la primera versión de la regla de atípicos marcaba 2.2 % de los pitches para
  excluirlos. Al revisarlos, casi todos eran **un solo valor malo en un pitch bueno**: lecturas de
  spin ~1,150 rpm fuera de lo normal para ese pitcher (falla conocida de Trackman) o release
  desplazado 1–2 ft. Anular solo ese valor conserva el resto del pitch; LightGBM maneja nulos.
  Si lo que se sale de lo normal es la velocidad o el movimiento, el pitch está bien medido pero
  probablemente mal etiquetado: se marca y se reclasifica por forma en la etapa 2.
- **Resultado:** los pitches no usables para Stuff+ bajan de 2.5 % a **0.31 %**.
- **Alternativas descartadas:** excluir la fila completa; subir el umbral (dejaría pasar lecturas
  de spin claramente erróneas).
- **Estado:** Vigente. Detalle en `01_limpieza.md`, sección D.

### D-010 · 2026-09-30 · `Sweeper` se agrupa con `Slider`; Two/One-Seam con `Sinker`
- **Por qué:** solo hay 588 sweepers y la mayoría de los sweepers reales ya vienen etiquetados como
  slider; separarlos por etiqueta sería inconsistente. En la etapa 2 creamos grupos propios por
  forma del pitch. `AutoPitchType` original se conserva.
- **Estado:** Vigente.

### D-009 · 2026-09-30 · Consultas y limpieza en SQL con DuckDB
- **Por qué:** DuckDB consulta el parquet directo, sin cargar 635k filas en memoria, y cada regla
  queda como una expresión SQL corta y fácil de explicar. Pandas solo para exportar y graficar.
- **Alternativas descartadas:** todo en pandas (más lento y las reglas quedan dispersas en código).
- **Estado:** Vigente.

### D-008 · 2026-09-30 · Solo se marcan valores físicamente imposibles
- **Por qué:** un valor raro pero posible (105 mph) es información real; quitarlo recorta a los
  mejores pitchers. Solo marcamos lo imposible, y la regla afecta a 340 pitches (0.05 %).
- **Alternativas descartadas:** recortar por percentiles (p1–p99), porque eliminaría 1 % de pitches
  reales en cada variable.
- **Estado:** Vigente. Detalle en `01_limpieza.md`, sección D.

### D-007 · 2026-09-30 · Batazos sin `ExitSpeed`: ni imputar ni eliminar
- **Por qué:** faltan de forma no aleatoria (hit rate 19 % vs 37 %) y en distinta proporción por
  altitud. Eliminarlos o rellenarlos con el promedio sesgaría justo la comparación de altitud.
  Conservamos la fila y usamos el resultado registrado del batazo.
- **Alternativas descartadas:** eliminar filas; imputar con la media; imputar con un modelo
  (queda solo como prueba de sensibilidad).
- **Estado:** Vigente. Detalle en `01_limpieza.md`, sección C.1.

### D-006 · 2026-09-30 · La temporada 2026 es el holdout de temporada
- **Por qué:** entrenar con 2024–2025 y validar en 2026 simula usar el modelo en una temporada
  futura, que es como lo usaría el club.
- **Alternativas descartadas:** mezclar 2026 en el entrenamiento; validación cruzada aleatoria.
- **Estado:** Vigente.

### D-005 · 2026-09-30 · El proyecto se trabaja en Python
- **Estado:** Vigente.

### D-004 · 2026-09-29 · Los datos nunca se suben al repositorio
- **Por qué:** el reglamento dice que los datos son de ISAC y Diablos Rojos y solo se pueden
  presentar resultados. `.gitignore` excluye todo `data/`.
- **Alternativas descartadas:** subir una muestra; Git LFS.
- **Estado:** Vigente.

### D-003 · 2026-09-29 · Documentación en `.md` por etapa + un HTML visual por etapa
- **Por qué:** todo el equipo debe poder explicar cada paso en la entrevista final. El `.md` es la
  fuente de verdad; el HTML es la versión para presentar.
- **Estado:** Vigente.

### D-002 · 2026-09-29 · Priorizar pasaporte de altitud, índice Magnus y punto de mira
- **Por qué:** son las ideas con mejor evidencia preliminar y las más útiles para el club
  (ver `00_contexto_y_approach.md`, secciones 5 y 6).
- **Alternativas descartadas por tiempo:** causal forest táctico, modelo bayesiano jerárquico
  completo; quedan como trabajo futuro.
- **Estado:** Vigente.

### D-001 · 2026-09-29 · Modelo en dos etapas: traductor físico → modelo de resultado
- **Por qué:** permite un contrafactual físicamente coherente (el mismo pitch en CDMX y a nivel del
  mar) en vez de solo "prender" una variable de altitud.
- **Alternativas descartadas:** un solo modelo con `altitude_category` como variable; modelos
  separados por altitud (no permiten comparar el mismo pitch).
- **Estado:** Vigente.

---

## Pendientes de decidir

Ninguna por ahora.
