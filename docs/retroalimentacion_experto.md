# Retroalimentación de un experto en béisbol

> **Fecha:** 6 de octubre de 2026.
> **Quién:** Héctor, lanzador, en conversación con el equipo.
> **Para qué sirve este documento:** dejar por escrito qué nos dijo, qué comprobamos con los datos y
> qué cambia en el plan. Cada punto dice si lo adoptamos, cómo, y si no, por qué.

## Lo que más cambia el plan

El experto insistió en que **la secuencia importa**: "la eficiencia de un lanzamiento depende del
anterior, no hay pérdida de memoria". Habíamos concluido que el dataset no tenía orden de pitches.
Al revisarlo encontramos que **sí lo tiene en el orden de las filas** (decisión D-015), así que ahora
podemos trabajar secuencia, tunneling, vuelta al orden, relevos y series. Los primeros datos le dan
la razón: cuando el pitch se separa más del anterior *después* de que el bateador decide, el whiff
por swing sube de 20.3 % a 31.3 % (`docs/02_features.md`, sección 9).

## Punto por punto

| Lo que dijo | Qué comprobamos | Qué hacemos |
|---|---|---|
| Un buen lanzamiento es el que tiene efecto positivo en el juego | — | Ya era el plan: el target es carreras esperadas, no solo swings fallidos |
| Los bateadores tienen zonas de poder ("yo bateo zurdo, mi zona es abajo adentro"); mandar a donde el heatmap no esté en rojo | Tenemos 864 bateadores con ubicación de cada pitch y su resultado | **Mapa de daño por zona** de cada bateador, con wOBA (pondera bases por bolas, sencillos, dobles y jonrones) en vez de promedio. A los bateadores con pocos turnos los jalamos al promedio de su tipo para que el mapa no sea ruido. Alimenta Location+ y el punto de mira |
| Es muy importante la pareja específica bateador-pitcher | De 83,969 parejas, la mediana es de **6 pitches** y solo 4.8 % llegan a 20 | La pareja exacta casi no tiene datos. Modelamos al **bateador contra la forma del pitch** (cómo le va contra sweepers rápidos, por ejemplo), que sí tiene muestra y responde la misma pregunta |
| No queremos maximizar al pitcher, queremos minimizar al bateador | — | Es el enfoque de Pitching+ y de las herramientas. Stuff+ se queda sin bateador porque así lo define la convocatoria |
| La limpieza debería medir cuánto se equivoca el pitcher según el bateador | No tenemos el punto donde pedía el catcher | No va en la limpieza (que solo corrige errores de medición; quitar los errores del pitcher sesgaría el modelo). Va como **variable de comando**: qué tanto se aleja de su ubicación habitual según bateador y conteo |
| La secuencia importa; hay que cambiar, no tirar siempre el mejor; tunneling | Confirmado en datos (arriba) | Variables de pitch anterior y tunneling en el punto de decisión, ya construidas |
| Importa el porcentaje de cada pitch; la mezcla tiene que variar con la atmósfera | — | Ya tenemos `pitch_usage_pct`. El optimizador de mezcla propondrá mezcla *y* orden por ambiente |
| Las sliders se aplanan en altura y parecen sweepers; las que más rompen serán menos efectivas | Las sliders con forma de sweeper bajan de 12.6 % a 3.1 % en altitud extrema; las que más dependen del spin pierden whiff (33.5 % → 29.2 %) | Coincide con nuestro índice de dependencia del Magnus |
| "Mi sweeper cae muy bien en Mazatlán y en la CDMX no hay cambio" | No contradice lo anterior: cada pitcher reacciona distinto | Es justo lo que mide el pasaporte de altitud por pitcher. Si su sweeper depende poco del spin, el modelo debería mostrarlo estable |
| Homologar zurdos y diestros no es óptimo; el platoon da ventaja | — | Aclaración: el lado del brazo solo sirve para comparar formas. La mano del pitcher, el lado del bateador y `platoon_same_side` **siguen como variables**, y vamos a medir el efecto de platoon |
| Emular la diferencia por series (3 juegos aquí, 3 allá) | Los juegos vienen por fecha y la serie se nota: el siguiente juego de un bateador es en la misma altitud 74 % de las veces contra 36 % al azar | Factible: falta reconstruir los equipos a partir de los jugadores. Habilita el **valor de aclimatación** (juego 1 contra juego 3 en altura) |
| Importa quién abre y quién cubre de la 5ta a la 8va; el relevo no se puede definir antes del juego | Reconstruimos 4,303 aperturas; los relevistas entran en la 7ma de mediana | **Asistente de bullpen durante el juego**: qué relevista conviene contra los próximos bateadores, en lugar de un plan fijo |

## Anotaciones al plan de herramientas

| Herramienta | Anotación | Qué hacemos |
|---|---|---|
| Pasaporte de altitud | Caso Isaac Paredes en Houston: hay jugadores que se acoplan mejor a un lugar; cada campo es diferente | Además del pasaporte de pitchers, un **encaje de bateadores con la altura**: qué perfil gana más en el Harp Helú (probablemente quienes jalan y elevan), con dirección, ángulo, distancia y velocidad de salida. Sirve para saber a quién contener. No tenemos el estadio exacto, solo la altitud |
| Punto de mira | Decir tipo de lanzamiento y velocidad, con heatmap en el rectángulo de bateo y punto de tiro; usar OPS además del promedio, porque un hit no lo es todo y las bases por bolas importan | Pantalla con el mapa de daño del bateador (wOBA por zona), el pitch recomendado, su velocidad y el punto donde apuntar ya corregido por altura |
| Aire del día | Humedad y presión con una API de clima; impacto en la trayectoria de bateo (ejemplo: jonrones perdidos por clima) | Sin fecha ni estadio no podemos unir clima histórico. Nuestro aire medido por juego es la referencia para calibrar la API cuando se use en vivo. Queda como trabajo futuro |

## Qué cambia en el plan

1. **Nueva familia de variables de secuencia** (hecha en la etapa 2).
2. **Nuevas herramientas:** mapa de daño por zona con wOBA, asistente de bullpen, encaje de
   bateadores con la altura.
3. **Pitching+ con el bateador** (minimizar al bateador), además de Stuff+ sin bateador.
4. **Aclimatación** pasa de trabajo futuro a posible, si alcanza el tiempo.
