# 00 · Contexto del reto y enfoque elegido

> **Para qué sirve este documento:** que cualquier integrante del equipo pueda explicar, sin notas,
> qué nos piden, qué encontramos en los datos y por qué atacamos el problema así.
> Todas las cifras salen de `src/exploracion_preliminar.py` (datos crudos, sin limpiar).

---

## 1. El reto en una frase

Construir un **Stuff+ calibrado para la LMB** que diga qué tan bueno es cada pitch
**en las condiciones físicas del Harp Helú** y que el club pueda usar para decidir.

La escala es `Stuff+ = 100 + 10 × z(score)`: 100 es el promedio de la liga, 110 es una
desviación estándar mejor, 120+ es élite.

## 2. Qué tenemos que entregar

| # | Entregable | Qué debe contener |
|---|---|---|
| 1 | Scores | Stuff+, Location+ y Pitching+ por pitch, pitcher y arsenal; delta CDMX vs. resto de estadios |
| 2 | Perfil físico ideal | Qué características y arsenal maximizan Stuff+ en el Harp Helú, con argumento físico y estadístico |
| 3 | Recomendaciones | Qué perfiles ganan y pierden en altitud (con riesgo de jonrón) y cómo evaluar prospectos |
| 4 | Dashboard | Ingresar un pitch y ver su Stuff+ en CDMX vs. nivel del mar; mapa de movimiento |
| 5 | Documento técnico | 6–10 páginas: teoría, decisiones de modelado, escala, validación, límites |

## 3. Cómo nos califican (25 % cada uno)

| Criterio | Qué buscan | Cómo destacamos |
|---|---|---|
| Calidad del modelo | Scores calibrados que distinguen pitches buenos de malos | Superar el baseline (xRunValue promedio por conteo) |
| Robustez fuera de muestra | Generaliza a pitchers y estadios no vistos | Holdout por pitcher, temporada y altitud |
| Arsenal + altitud | Features relacionales y efecto de altitud cuantificado | Delta Stuff+ por forma de pitch, con evidencia LMB |
| Aplicabilidad | Que el coach y el director deportivo cambien decisiones | Herramientas concretas (ver sección 6) |

## 4. Qué datos tenemos y qué nos falta

**Tenemos:** 635,002 pitches de Trackman, 1,134 pitchers, 2,127 juegos, temporadas 2024, 2025 y
2026 (parcial). Física completa del pitch (velocidad, spin, movimiento, release, trayectoria),
resultado del pitch y del batazo, conteo y ubicación.

**Nos falta, y hay que decirlo en el documento técnico:**

- **No hay estadio.** Solo `altitude_category` con tres niveles (`Extreme`, `Medium`, `No Altitude`).
  El nivel `Extreme` probablemente mezcla CDMX con otros parques altos (≈ 223 juegos por temporada
  no caben en un solo estadio). No podemos aislar el Harp Helú directamente.
- **No hay corredores en base**, clima, ni equipo local.
- **No hay fecha ni número de pitch** en ninguna columna. *Corrección del 6 de octubre:* el orden sí
  existe, en el orden de las filas: dentro de cada juego los pitches vienen en orden cronológico y
  los juegos vienen por fecha (decisión D-015). Eso permite secuencias, turnos al bat y series.

## 5. Qué encontramos al explorar (por qué el enfoque es válido)

### 5.1 La altitud le quita ~22–30 % del movimiento a todos los pitches

Comparamos **al mismo pitcher con el mismo tipo de pitch** en altitud extrema contra nivel del mar.
Así eliminamos el efecto de que en cada estadio lancen pitchers distintos.

| Pitch | Pares | Δ IVB | Δ HB | % IVB | % HB | Δ velocidad |
|---|---|---|---|---|---|---|
| Four-Seam | 404 | −3.7" | −2.8" | −22 % | −27 % | +0.1 mph |
| Slider | 299 | −0.7" | −1.0" | −22 % | −23 % | +0.3 mph |
| Sinker | 202 | −2.6" | −4.1" | −23 % | −25 % | 0.0 mph |
| Changeup | 137 | −2.0" | −4.2" | −26 % | −31 % | −0.2 mph |
| Curveball | 100 | +1.7" (cae menos) | −3.1" | −22 % | −30 % | 0.0 mph |

**Lectura:** la velocidad no cambia; lo que cambia es la *forma*. Es exactamente lo que predice la
física: el efecto Magnus es proporcional a la densidad del aire, que en CDMX es ~20 % menor.

**Contradice la hipótesis H2 del reto:** el changeup pierde tanto o más movimiento que la recta.

### 5.2 Los resultados empeoran para el pitcher

| Altitud | Whiff/swing | HR por bola en juego | Hit por bola en juego | Carreras/juego |
|---|---|---|---|---|
| Extreme | 23.1 % | 4.3 % | 38.7 % | 13.7 |
| Medium | 24.0 % | 4.2 % | 37.9 % | 12.5 |
| No Altitude | 24.8 % | 3.7 % | 33.1 % | 9.1 |

### 5.3 Podemos medir la densidad del aire con los propios datos de Trackman

De la trayectoria (`vx0, vy0, vz0, ax0, ay0, az0`, quitando la gravedad) calculamos cuánto frena
cada recta. Ese frenado es proporcional a la densidad del aire.

| Altitud | Juegos | Proxy de arrastre (media ± desv.) |
|---|---|---|
| Extreme | 602 | 0.181 ± 0.008 |
| Medium | 508 | 0.192 ± 0.010 |
| No Altitude | 1,002 | 0.215 ± 0.010 |

**Por qué importa:** nos da una variable **continua** de ambiente por juego en vez de tres cajas,
y podría ayudarnos a agrupar juegos por estadio.
*Por validar:* que la diferencia no sea un artefacto de calibración de Trackman en cada parque.

### 5.4 Lo que la altitud castiga es la dependencia del Magnus, no el tipo de pitch

Dividimos cada tipo de pitch en tres grupos según cuánto movimiento genera por unidad de spin
(tercil 3 = más dependiente del Magnus).

| Pitch | Tercil | Whiff/swing nivel del mar | Whiff/swing altitud extrema |
|---|---|---|---|
| Four-Seam | 3 (mucho "ride") | 26.8 % | **19.9 %** |
| Four-Seam | 1 (poco Magnus) | 16.9 % | 17.2 % |
| Slider | 3 ("sweepy") | 33.5 % | **29.2 %** |
| Slider | 1 ("gyro") | 33.9 % | 33.0 % |

**Lectura:** los pitches que dependen del spin para moverse pierden efectividad; los que no, casi
no cambian. Confirma y extiende la H4 del reto.
*Precaución:* los terciles se calculan dentro de cada altitud, así que no son exactamente los
mismos pitches en ambas columnas. Hay que repetirlo con controles.

### 5.5 Las curvas llegan más altas (se "cuelgan")

Dentro del mismo pitcher, la curva cruza el plato **~0.9" más alta** en altitud; las rectas y
cambios llegan más bajos. El pitcher apunta igual, pero el pitch no rompe lo que espera.

### 5.6 Posible aclimatación

Pitchers con ≥ 50 % de sus pitches en altitud extrema (probablemente de equipos de altura) rinden
mejor ahí que los visitantes: curva con 34.8 % vs 32.1 % de whiff y **2.9 % vs 4.3 % de HR por bola
en juego**.
*Precaución:* mezcla aclimatación con calidad del pitcher. Es una pista, no una conclusión.

## 6. El enfoque elegido

### 6.1 Columna vertebral: modelo en dos etapas

```
Características de release           Forma del pitch             Resultado esperado
(velo, spin, eje, release,   ──A──►  (IVB, HB, VAA)      ──B──►  (whiff, strike, GB,
 extensión, densidad aire)            en ese ambiente              contacto duro, xRV)
```

- **Etapa A — traductor físico:** predice cómo se moverá el pitch según el aire.
- **Etapa B — modelo de resultado:** predice qué tan efectivo es un pitch con esa forma.
- **Contrafactual:** el mismo pitch pasa por A con aire de nivel del mar y de CDMX; ambas formas
  pasan por B. La diferencia es el **ΔStuff+ por altitud**, físicamente coherente.

*Por qué no basta con agregar una variable de altitud:* si solo "prendemos" la altitud dejando el
movimiento igual, estamos evaluando un pitch que no puede existir en CDMX.

### 6.2 Lo que nos diferencia (herramientas para el club)

| Herramienta | Pregunta que responde | Usuario |
|---|---|---|
| **Pasaporte de altitud** | "Si ficho a este pitcher de nivel del mar, ¿cuánto vale en el Harp Helú?" | Director deportivo |
| **Índice de dependencia del Magnus** | "¿Qué tan frágil es este arsenal en altura?" | Scouting |
| **Corrección de punto de mira** | "¿Cuántas pulgadas más abajo debo apuntar mi curva en casa?" | Pitching coach |
| Optimizador de rotación y mezcla | "¿Quién abre en casa y quién de gira? ¿Qué pitch usar más en casa?" | Manager |
| Densidad del aire del día | "¿Cómo estará el aire hoy?" | Staff (a futuro) |
| Valor de aclimatación | "¿Cuánto tarda en adaptarse un fichaje?" | Director deportivo (a futuro) |

**Prioridad para la entrega:** Stuff+ base + pasaporte + índice Magnus + punto de mira.
El optimizador va en versión simple (carreras ahorradas). Los dos últimos, como trabajo futuro.

**Validación estrella del pasaporte:** ~400 pitchers lanzan en ambos ambientes. Predecimos su
rendimiento en altitud usando **solo** sus pitches a nivel del mar y lo comparamos con lo real.

## 7. Plan de trabajo

| Semana | Del | Al | Qué |
|---|---|---|---|
| 1 | 29 sep | 5 oct | Limpieza, densidad del aire por juego, xRunValue + baseline, traductor físico |
| 2 | 6 oct | 12 oct | Modelo de resultado, Stuff+/Location+/Pitching+, validaciones, SHAP |
| 3 | 13 oct | 22 oct | Herramientas, dashboard, documento técnico, ensayo de entrevista |

## 8. Referencias clave

- Convocatoria oficial: `referencias/convocatoria_isac_diablos_2026.pdf`
- Nathan, A. — física del efecto Magnus y altitud (Coors Field).
- SABR — *High Altitude Offense*, Baseball Research Journal.
- Huang & Hsu (2021) — *Big data analytics in baseball: A review*, SAGE Open.
