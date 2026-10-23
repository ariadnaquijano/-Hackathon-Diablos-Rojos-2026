# Auditoría de jueces simulados (22 de octubre)

> Tres rondas de un panel de agentes que hicieron de jueces con la rúbrica del hackathon. Cada hallazgo lo
> revisó otro agente que intentaba refutarlo, y las cifras se comprobaron contra `reportes/`. Son
> estimaciones internas, no la calificación oficial.

## El panel

| Juez | Qué revisó |
|---|---|
| Modelo y robustez | Calidad del modelo y validación fuera de muestra (criterios 1 y 2) |
| Arsenal y altitud | Física del ajuste, pérdida por tipo, literatura (criterio 3) |
| Aplicabilidad | Los cinco entregables y si un coach sabe qué hacer (criterio 4) |
| Verificador de cifras | Cada número del documento contra los reportes |
| Corrector | Erratas, figuras, secciones vacías, formato |

## Puntajes (0 a 100)

| Juez | Ronda 1 (doc v0) | Ronda 2 (doc v1) | Ronda 3 (doc v2) | Ronda 3 con todo aplicado |
|---|---|---|---|---|
| Modelo y robustez | falló | 71 | 71 | 77 |
| Arsenal y altitud | 48 | 60 | 71 | 80 |
| Aplicabilidad | 52 | 70 | 72 | 82 |
| Corrector | 52 | 55 | 56 | 82 |
| Cifras correctas | 95 % | 95 % | 95 % | 100 % |

Total estimado de la ronda 3: **unos 71 como estaba y unos 79 con todo aplicado.**

## Lo que dijeron, por ronda

**Ronda 1.** El documento no tenía cierre: sección 7 y referencias vacías, figuras pendientes, y no
nombraba ningún entregable. Faltaban los valores de k y su lectura física, y el 0.15 de calibración se
leía como defecto porque no se comparaba con el nulo (0.32).

**Ronda 2.** Los scores por pitch no estaban en ningún lugar que viera el jurado. La portada no enlazaba el
documento. El reporte no citaba literatura ni el placebo.

**Ronda 3.** Los HTML afirmaban de más en algunos puntos: el k de 1.10 de la liga presentado como
confirmación, la curva que "casi no pierde", un r de Location+ del modelo viejo (0.67 en vez de 0.58),
y un placebo que en realidad no pasó (6 de 7 casos). El CSV por pitcher daba estimados en altura que la
ficha niega. Faltaba comparar contra modelos simples en la portada.

## Qué se corrigió

- **Documento** (lo corrige el equipo): erratas y datos puntuales, Figura 2, referencias en APA.
- **Portada:** tres cifras clave, enlaces a los cinco entregables, y la validación completa plegada:
  modelos simples, intervalos, calibración, estabilidad y el límite a futuro.
- **Reporte de entregables:** k en densidad, placebo honesto, hipótesis de costura con literatura,
  enlaces a los scores; el soporte plegado debajo de cada respuesta.
- **Scores:** los tres archivos en la entrega, con `LEEME.txt`; el estimado en altura con la misma regla
  que las fichas.
- **Simulador y fichas:** qué es el aire y su escala, el k horizontal, el riesgo de un arsenal, que los
  scores son fuera de muestra.

## Lo que no se arregla

- Stuff+ solo aporta 0.15 % por pitch y por pitcher empata con una regresión lineal.
- Para la temporada siguiente, la historia del pitcher predice mejor (r 0.38 contra 0.21 de Stuff+).
- El placebo de k no pasa y el HB cae más que la IVB sin causa probada.
- No hay estadio, clima ni corredores en la base; 2026 se consultó durante el desarrollo.

## Lo que dijeron los organizadores

Hay unos 90 equipos y los dashboards con muchas funciones no se revisan: menos es más. Por eso cada
página abre con la respuesta y deja el detalle a un clic.
