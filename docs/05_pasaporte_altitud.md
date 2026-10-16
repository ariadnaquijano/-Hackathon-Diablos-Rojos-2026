# Etapa 5 · Pasaporte de altitud

> **Estado:** probado con la regla D-034. La forma no le gana a la base más simple. El costo ordena
> a los pitches (correlación fuera de cero), pero su error no baja con intervalo fuera de cero.
> **Evidencia:** `src/pasaporte_altitud.py`; cifras en `reportes/etapa_05_pasaporte.json`. El costo por
> pitcher y tipo de pitch está en `data/processed/pasaporte.parquet` (no se sube al repo).
> **Datos:** solo 2024–2025; 2026 no se tocó.

## Qué responde

> "Este pitcher solo lo hemos visto a nivel del mar. ¿Cuánto va a perder cada uno de sus pitches en el
> Harp Helú?"

1. **Forma:** cada pitch a nivel del mar se traduce al aire de la altitud extrema (mediana 0.84 en
   2025) con movimiento × aire^k. El k es el de su tipo de pitch (D-016). La recta de referencia se
   traduce igual.
2. **Valor:** un Stuff+ local evalúa el pitch original y el traducido. Tiene los mismos componentes
   que D-027, pero usa el movimiento observado. El costo es la diferencia en carreras por 100 pitches.

**Prueba:** 535 pares pitcher–pitch de 299 pitchers que lanzaron el mismo tipo de pitch en altitud
extrema y a nivel del mar en 2024–2025, con 50+ pitches por lado. Los modelos de valor no vieron al
pitcher (5 pliegues por pitcher). Los intervalos remuestrean pitchers completos.

## 1. Forma: el pasaporte acierta, pero no mejor que la pérdida promedio

| Movimiento en altura | Error (pulgadas²) del pasaporte | Suponer que no cambia | Pérdida promedio de la liga por tipo |
|---|---|---|---|
| IVB (cambio real promedio: −2.2 in) | 1.32 | 9.49 (pasaporte mejor: −8.8 a −7.4) | **1.10** (pasaporte **peor**: +0.11 a +0.32) |
| HB (cambio real promedio: −1.8 in) | 1.51 | 11.40 (pasaporte mejor: −10.8 a −8.9) | 1.65 (empate: −0.47 a +0.13) |

- La física funciona: reduce el error 7 veces contra suponer que el pitch no cambia.
- **Según la regla, no gana.** Aplicar a cada tipo de pitch su pérdida proporcional promedio acierta
  igual en HB y mejor en IVB. Esa base se calculó con los mismos pares, lo que la favorece. Aun así,
  el k por tipo no le agrega nada a una proporción simple por tipo.

## 2. Valor: el costo ordena a los pitches, pero con poca fuerza

| Prueba | Pasaporte | Base | Resultado |
|---|---|---|---|
| r entre el costo predicho y el cambio real del xRV sin contacto | **0.13** (0.05 a 0.22) | — | **positiva, fuera de cero** |
| Error, calibrado en otros pitchers | 0.951 | 0.967 (mismo costo para todos) | −0.038 a +0.004 (toca cero) |
| Costo promedio por 100 pitches | 0.39 predicho | 0.28 real | — |

Con el xRV total como referencia (incluye el contacto, que es ruido): r 0.09 (0.01 a 0.17); error
−0.080 a +0.028.

- El costo predicho apunta a los pitchers correctos más que al azar, pero el cambio real de cada
  pitcher es muy ruidoso. El xRV real del mismo pitcher entre altitudes solo se correlaciona 0.15, así
  que el error no baja lo suficiente para probarlo.
- El nivel promedio es razonable: predice 0.39 carreras por 100 pitches perdidas y el cambio real es
  0.28.

## 3. Chequeo descriptivo por tipo de pitch

Se agregó después de la prueba.

| Tipo | Pares | Costo predicho por 100 | Cambio real sin contacto por 100 | IC 95 % del real |
|---|---|---|---|---|
| **Recta** | 210 | **0.69** | **0.40** | 0.27 a 0.53 |
| Sinker | 97 | 0.42 | 0.32 | 0.14 a 0.49 |
| Cambio | 51 | 0.38 | 0.32 | 0.09 a 0.58 |
| Slider | 129 | 0.04 | 0.18 | −0.03 a +0.39 |
| Curva | 35 | −0.07 | 0.02 | −0.24 a +0.28 |

- **El orden coincide.** Las rectas, sinkers y cambios pierden valor en altura, con el cambio real
  fuera de cero. Las sliders y curvas casi no pierden: su intervalo toca cero. Es lo mismo que mostró
  el análisis exploratorio: la recta que depende del efecto Magnus pierde más, y la slider de giro
  (gyro) casi no se afecta.
- El pasaporte **exagera la pérdida de la recta** (0.69 contra 0.40, fuera del intervalo real). En los
  otros tipos, lo predicho cae dentro del intervalo real.

## Qué significa para el club

1. **Lo probado:**
   - El aire cambia la forma de forma predecible: el error es 7 veces menor que suponer que no cambia.
   - El costo predicho ordena a los pitches mejor que el azar.
   - Las rectas, sinkers y cambios pierden valor en altura; las sliders y curvas casi no.
2. **Lo que no:** para un pitcher específico, el pasaporte no le gana con claridad a "aplica la pérdida
   promedio de su tipo de pitch".
3. **Uso práctico:** al traer a un pitcher de la costa, su arsenal dice cuánto riesgo corre en la CDMX.
   - Un pitcher de rectas y sinkers tiene más que perder que uno de sliders y curvas.
   - El orden de magnitud es de 0.3 a 0.4 carreras por 100 pitches para los pitches rápidos.

## Límites

- El cambio real de cada par mezcla el aire con otras diferencias (rivales, estadios, momento de la
  temporada).
- La mediana del aire de la altitud extrema no es el aire de cada juego.
- La base de la pérdida promedio se calculó con los mismos pares.
- Las cifras del cambio real por tipo son descriptivas; no estaban en la regla.
