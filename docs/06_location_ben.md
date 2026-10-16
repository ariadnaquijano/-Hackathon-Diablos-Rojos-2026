# Etapa 6 · Location+ del equipo en el modelo oficial (versión 3)

> **Decisiones:** D-039 (adopción, decidida por el equipo) y D-040 (versión neutral).
> **Evidencia:** `src/location_ben.py` → `reportes/etapa_06_location_ben.json` (comparación, 2024–2025);
> `src/modelo_v3.py` → `reportes/etapa_06_modelo_v3.json` (2026); `reportes/etapa_06_validacion_estadio.json`
> (`version_3`).
> **Origen:** PR #2 de Ben (`location_plus_xgb.py`, `run_value.py`, `docs/LOCATIONPLUS_MODEL_GUIDE.md`).

## Qué es

Un **árbol de resultados**: seis modelos XGBoost predicen qué pasa con el pitch según dónde cae, en qué
cuenta y contra qué mano. Cada pitch recibe su xCSW (probabilidad de strike cantado o whiff) y su xRV
(valor esperado en carreras). El Location+ por pitcher mezcla mitad CSW y mitad RV, ajustados contra la
liga en la misma cuenta. No ve el tipo de pitch: mide qué tan buen lugar es ese para un pitch promedio.

## Qué hicimos para integrarlo

1. **Rearmamos las piezas que faltaban.** `location_plus_xgb.py` importaba cinco funciones que no
   estaban en el PR. Se rearmaron siguiendo su guía; el modelo, las variables, los hiperparámetros, el
   run value y las fórmulas son los suyos.
2. **Lo entrenamos con nuestros 5 pliegues por pitcher**, para tener 2024–2025 sin ver al pitcher (lo
   necesitan Pitching+ y las pruebas por pitcher). 2026 sale de un modelo de 2024–2025.
3. **Versión neutral (D-040).** Su modelo usa la altitud como variable. Con su altitud real, el mismo
   pitcher salía **1.00 carreras por 100 peor** en la CDMX que a nivel del mar en Pitching+ (su
   resultado real solo cambia 0.57): castigaba al pitcher por el estadio. Ahora cada pitch se predice
   como si fuera a nivel del mar, igual que nuestro Stuff+.

## Comparación contra nuestro Location+ v2 (2024–2025, sin ver al pitcher)

| Prueba | Ben neutral | Ben local | v2 |
|---|---|---|---|
| Pitching+, mejora por pitch contra el promedio por conteo | 5.37 % | 5.38 % | **5.65 %** |
| Por pitcher: r con su xRV real | **0.36** | 0.40 | 0.25 |
| Por pitcher: r con su CSW real | **0.29** | 0.33 | 0.16 |
| Repetición de 2024 a 2025 | 0.58 | 0.59 | **0.67** |

- **Por pitch predice un poco peor** (−0.34 a −0.21 puntos): no ve el tipo de pitch.
- **Por pitcher ordena mucho mejor** (neutral contra v2: +0.06 a +0.15 con el xRV real), que es lo que
  usa el club. La versión neutral conserva casi toda la ventaja: no venía de conocer el estadio.
- **Se repite algo menos** de un año a otro.

## El modelo oficial v3 en 2026 (sexta mirada, declarada)

| Prueba | v2 | **v3** |
|---|---|---|
| Pitching+ por pitch, mejora contra la media | 5.51 % | 5.34 % |
| Pitching+ por pitcher, r con su xRV real | 0.44 | **0.55** |
| Pitching+ por pitcher, error contra la lineal observada | empate | **le gana: −0.19 a −0.03** |
| Mismo pitcher entre altitudes (Pitching+) | 0.09 | 0.07 |
| RMSE de Pitching+ (modelo nulo 0.14807) | 0.14394 | 0.14408 |
| Validación por estadio, Pitching+ | 5.12 % | 4.97 % |

**Es la primera vez que un modelo nuestro le gana a la base lineal por pitcher con intervalo fuera de
cero.** A futuro sigue sin ganarle a la historia del pitcher.

## Límites

- No ve el tipo de pitch: una slider y una recta en el mismo punto reciben la misma predicción.
- Su run value usa otra construcción del valor de cuenta que nuestro target; Pitching+ reajusta los
  pesos con nuestro target para combinarlos.
- 2026 se miró dos veces con este modelo (local y neutral), ambas declaradas; la neutral no se eligió
  por su resultado en 2026.
