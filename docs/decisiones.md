# Bitácora de decisiones

Cada decisión importante queda aquí, la más reciente arriba. Si una decisión cambia, no se borra:
se agrega una nueva entrada que la reemplaza y se marca la anterior como *Reemplazada*.

**Formato:** fecha · decisión · por qué · alternativas descartadas · estado.

---

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
