# Etapa 4 · Afinado del modelo (versión 2)

> **Estado:** probado con la regla D-035. Stuff+ se queda en la versión 1; Location+ pasa a la
> versión 2 (árboles de 31 hojas).
> **Evidencia:** `src/afinado.py` → `reportes/etapa_04_afinado.json` (elección, solo 2024 → 2025);
> `src/modelo_v2.py` → `reportes/etapa_04_modelo_v2.json` (cuarta mirada a 2026).

## Elección: entrenado con 2024, evaluado en 2025

### Stuff+: se queda la versión 1

| Configuración | Mejora por pitch | Diferencia contra la versión 1 | Error por pitcher | Diferencia de error por pitcher |
|---|---|---|---|---|
| **Versión 1** (hojas de 1,000 pitches, 15 hojas por árbol) | 0.136 % | — | 0.474 | — |
| Hojas de 200, 15 hojas | 0.139 % | −0.007 a +0.013 | 0.475 | −0.005 a +0.007 |
| Hojas de 1,000, 31 hojas | 0.139 % | −0.007 a +0.013 | 0.469 | −0.011 a +0.003 |
| Hojas de 200, 31 hojas | 0.146 % | −0.002 a +0.020 | 0.470 | −0.011 a +0.004 |
| Física, hojas de 1,000, 15 hojas | 0.230 % | +0.07 a +0.11 | 0.492 | **+0.004 a +0.032 (peor)** |
| Física, hojas de 200, 15 hojas | 0.217 % | +0.06 a +0.10 | 0.488 | **+0.001 a +0.029 (peor)** |
| Física, hojas de 1,000, 31 hojas | **0.287 %** | +0.12 a +0.18 | 0.495 | **+0.002 a +0.040 (peor)** |
| Física, hojas de 200, 31 hojas | 0.218 % | +0.06 a +0.10 | 0.483 | −0.005 a +0.023 |

Las configuraciones de "física" agregan cuatro variables: dependencia del efecto Magnus, movimiento
total a nivel del mar, ángulo horizontal relativo de llegada y tamaño del arsenal.

- Las variables físicas duplican la mejora por pitch, pero **empeoran el orden de los pitchers**. Por
  la regla, no se adoptan.
- Hipótesis, sin probar: el ángulo horizontal de llegada lleva información de dónde termina el pitch.
  Eso ayuda a predecir cada pitch, pero mezcla ubicación con Stuff+.
- Los hiperparámetros solos no cambian nada que se pueda medir.

### Location+: gana la versión con 31 hojas

| Configuración | Mejora por pitch | Diferencia contra la versión 1 | Error por pitcher |
|---|---|---|---|
| Versión 1 (hojas de 1,000, 15 hojas) | 4.93 % | — | 0.513 |
| Hojas de 200, 15 hojas | 4.92 % | −0.03 a +0.02 | 0.511 |
| **Hojas de 1,000, 31 hojas** | **5.00 %** | **+0.05 a +0.09** | 0.510 |
| Hojas de 200, 31 hojas | 4.99 % | +0.03 a +0.09 | 0.510 |

Cumple la regla: gana por pitch con un intervalo fuera de cero y no empeora por pitcher.

## Cuarta mirada a 2026: versión 1 contra versión 2

| Prueba en 2026 | Versión 1 | Versión 2 |
|---|---|---|
| Location+, mejora por pitch | 5.29 % | 5.45 % |
| Pitching+, mejora por pitch | 5.37 % | 5.51 % |
| Pitching+, error por pitcher (178 pitchers) | 0.689 | 0.695 (contra la lineal: −0.105 a +0.045, empate) |
| Proyección, error a futuro (114 pitchers) | 0.715 | 0.717 (contra la persistencia: −0.005 a +0.025, empate) |
| Pitching+, brecha entre altitudes | 0.089 | 0.091 |

Pesos de Pitching+ en la versión 2: 0.60 × Stuff + 1.03 × Location.

- La versión 2 sube un poco por pitch, igual que en 2025, y queda igual por pitcher y a futuro.
- No se calculó la diferencia pareada entre versiones en 2026, así que no se afirma que la versión 2
  sea mejor ahí. Ninguna conclusión de `docs/04_modelo.md` cambia.

## Decisión

- **El modelo oficial es la versión 2:** Stuff+ v1 y Location+ con 31 hojas. Se eligió con la regla de
  2024 → 2025, no por 2026.
- Las cifras de 2026 de las dos versiones se reportan juntas.
- **El afinado del modelo termina aquí.** Las mejoras que quedan son por pitch y de décimas de punto.
  Ya no cambian ninguna conclusión, y cada nueva mirada a 2026 debilita la evaluación.
