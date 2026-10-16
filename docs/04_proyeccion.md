# Etapa 4 · Proyección del año siguiente: el ruido del contacto

> **Estado:** probado con las reglas D-031 y D-032; la segunda mirada a 2026 empata.
> **Evidencia:** `src/proyeccion.py`; cifras en `reportes/etapa_04_proyeccion.json`.

## El problema

El modelo congelado (D-030) no predice el xRV de 2026 de cada pitcher mejor que su historia. Aquí se
buscó por qué y si se puede mejorar, eligiendo solo con 2024–2025.

## 1. Las tasas observadas no ayudaron (D-031)

Validación cruzada de 10 pliegues por pitcher, repetida 20 veces, con los pares 2024 → 2025 (146
pitchers):

| Proyección del xRV de 2025 | r | Error por 100 | Diferencia de error contra la persistencia |
|---|---|---|---|
| Persistencia del xRV total (base) | 0.09 | 0.510 | — |
| xRV, Stuff+ y Location+ | 0.07 | 0.509 | −0.021 a +0.021 |
| xRV y tasas observadas | 0.11 | 0.508 | −0.030 a +0.031 |
| Todo junto | 0.10 | 0.509 | −0.029 a +0.029 |

Ninguno gana. Hasta la base casi no predice: de 2024 a 2025, el xRV de un pitcher se repite apenas
0.18.

## 2. El hallazgo: el contacto es casi puro ruido

El xRV de cada pitcher se partió en dos:

- **Sin contacto:** bolas, strikes, whiffs y fouls. Cada bola en juego vale lo que vale un batazo
  promedio en ese conteo.
- **Contacto:** lo que valió cada bola en juego por encima o por debajo de ese promedio.

| Parte (2024, pitchers con 300+ pitches) | Variación entre pitchers | Se repite de 2024 a 2025 | Confiabilidad entre mitades (2024 / 2025) |
|---|---|---|---|
| xRV total | 0.71 | 0.18 | 0.35 / 0.26 |
| **Sin contacto** | 0.47 | **0.50** | **0.58 / 0.53** |
| Contacto | 0.52 | **−0.03** | 0.14 / 0.10 |

- Más de la mitad de la variación entre pitchers viene del contacto, y esa parte no se repite nada de
  un año a otro.
- Es la idea de DIPS (McCracken), medida en la LMB: el pitcher controla sobre todo lo que pasa antes de
  que la pelota entre en juego.
- Una razón probable: con 300 pitches hay unas 55 bolas en juego, muy pocas para que la calidad del
  contacto se estabilice.

## 3. El xRV sin contacto predice mejor el resultado futuro, dentro de 2024–2025 (D-032)

| Prueba | Persistencia del xRV total | Persistencia del xRV sin contacto | Diferencia de error |
|---|---|---|---|
| 2024 → 2025, validación cruzada (146 pitchers) | r 0.09, error 0.510 | r 0.25, error 0.477 | −0.074 a +0.007 (toca cero) |
| **Primera → segunda mitad de la temporada** (640 temporadas de pitcher, 494 pitchers) | r 0.08, error 0.963 | **r 0.19, error 0.933** | **−0.054 a −0.004** |

- La confirmación con mitades se agregó porque 146 pitchers no alcanzaban.
- La primera mitad son los primeros pitches de cada pitcher en la temporada, porque las filas vienen en
  orden cronológico (D-015).
- Con la regla de D-032 se cumple: el xRV sin contacto se adopta como base de la proyección.

## 4. Segunda mirada a 2026: empate

Pitchers con 300+ pitches en 2024–2025 y en 2026 (114):

| Predictor de 2024–2025 | r con su xRV real de 2026 | IC 95 % | Error por 100 | Diferencia de error contra la persistencia |
|---|---|---|---|---|
| Persistencia del xRV total | 0.38 | 0.22 a 0.53 | 0.708 | — |
| Persistencia del xRV sin contacto | 0.31 | 0.12 a 0.45 | 0.709 | −0.035 a +0.041 |

En 2026 no se repite la ventaja. Por la regla (D-025), no se exploró más en 2026 para buscar por qué.

## Qué significa

1. **Lo probado:** el contacto es la parte ruidosa del resultado de un pitcher. La parte sin contacto
   es el doble de estable y, dentro de 2024–2025, predice mejor el resultado futuro, con un intervalo
   fuera de cero.
2. **Lo que no se sostiene:** en 2026 empata con la historia total. No podemos decir que predice mejor
   el año siguiente.
3. **Para el club:** al evaluar a un pitcher con una temporada o menos de muestra, su resultado en
   bolas en juego dice muy poco. Lo que hace antes del contacto (strikes, whiffs, bolas) es lo que se
   repite. Es el mismo argumento a favor de Stuff+, que además se repite 0.83.

## Límites

- Hubo tres miradas a 2026 en total: la exploración, D-030 y esta segunda mirada de la proyección. Se
  reportan todas.
- Las pruebas de D-032 se agregaron después de ver que D-031 no ganó. La confirmación con mitades se
  agregó después de ver que el error quedó cerca del cero.
- 114 a 146 pitchers por prueba entre años: solo se ven diferencias grandes.
