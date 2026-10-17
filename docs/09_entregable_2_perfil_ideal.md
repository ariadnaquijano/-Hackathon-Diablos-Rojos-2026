# Entregable 2 · Perfil físico ideal para Diablos Rojos

> **Evidencia:** `reportes/etapa_05_pasaporte.json` (pérdida por tipo), `reportes/etapa_06_scores.json`
> (arquetipos, D-038), `reportes/etapa_06_perfil_ideal.json` (rasgos dentro de cada tipo),
> `reportes/etapa_06_riesgo_contacto.json` (contacto en altura), `docs/02_features.md` (exponente k).
> **Datos:** 2024–2025. 2026 no se usó.

## El perfil, en una frase

**Un pitcher para el Harp Helú es aquel cuyo valor no depende del efecto Magnus.** Mientras menos
viva de la recta y el sinker, más rompimiento de calidad tenga y más rolling provoque, menos le cobra
la altura.

## 1. Lo que dice la física

- En el Harp Helú el aire es ~21 % menos denso que a nivel del mar (densidad relativa 0.785 con la
  atmósfera estándar; el frenado de las rectas cae 16 %). La fuerza de Magnus es proporcional a la
  densidad y la pelota llega 1.3 % antes, así que el movimiento inducido cae casi igual que la
  densidad: k en densidad 1.05 para la recta y 1.10 en la liga, contra 1.11 que predice la física
  (D-041, `docs/06_fisica_densidad.md`).
- **Cuánto cae cada pitch** (exponente k: movimiento ∝ aire^k):

| Tipo | k vertical | k horizontal | Qué pasa en la CDMX |
|---|---|---|---|
| Recta | 1.50 | 1.64 | Pierde "ride": unos 4 in de IVB |
| Sinker | 1.40 | 1.75 | Pierde caída y corrida hacia el brazo |
| Cambio | 1.30 | **2.06** | La corrida horizontal es lo más sensible de la liga |
| Curva | 1.19 | 1.67 | Pierde movimiento, pero su valor depende menos de él |
| Slider | **0.68** | 1.22 | Casi no pierde vertical: es de giro de bala (*gyro*) |

- **El spin no compensa:** el aire baja el movimiento sin cambiar el spin, y con el mismo spin lo que
  decide el resultado es el movimiento (H4, `docs/hipotesis_h4.md`).

## 2. Lo que dicen los datos

**Entre tipos de pitch (evidencia fuerte, mismo pitcher en las dos altitudes):**

| Tipo | Delta de Stuff+ en el Harp Helú |
|---|---|
| Recta | −13.0 (−17.3 a −8.8) |
| Sinker | −13.3 (−20.5 a −6.1) |
| Cambio | −9.7 (−17.5 a −2.8) |
| Slider | −6.9 (−14.8 a +1.1) |
| Curva | −0.7 (−9.5 a +8.1) |

**El contacto (evidencia fuerte, toda la liga):**

- En altitud extrema hay **3.3 puntos más de jonrones por fly** (16.1 % contra 12.8 %) y 3.0 más de
  contacto duro.
- **Un fly vale 0.136 carreras en la CDMX y 0.039 a nivel del mar.** Un rolling cambia poco (+0.020).
  Inducir rolling protege más en altura (H3).

**Arsenal (D-038, tendencia):** el arquetipo de rompimiento conserva más Stuff+ en el Harp Helú (90.9
contra 86.8 del de recta y sinker) y pierde menos en lo real (+0.07 contra +0.30 carreras por 100),
aunque esa diferencia toca cero con 15 y 24 pitchers.

**Dentro de un mismo tipo (sin evidencia):** probamos si la velocidad, el spin, el IVB, el HB, la
extensión, la dependencia del Magnus, el VAA relativo o la diferencia de velocidad con la recta hacen
que un pitch pierda menos. **Ningún rasgo tiene evidencia:** todos los intervalos tocan cero (210
pares de rectas, 97 de sinkers, 129 de sliders, 51 de cambios).

- El modelo cree que las rectas con más IVB y más dependencia del Magnus pierden más (r 0.74 y 0.66
  con el costo predicho). Los datos apuntan al mismo lado, sin significancia.
- **No lo presentamos como hallazgo.**

## 3. El perfil ideal

| Rasgo | Qué buscar | Respaldo |
|---|---|---|
| **Pitch principal de rompimiento** | Slider o curva con Stuff+ ≥ 100 contra su tipo | Delta de −0.7 y −6.9 contra −13 de la recta |
| **Mezcla** | Slider + curva ≥ 40 % de sus pitches (arquetipo de rompimiento) | D-038: 90.9 de Stuff+ en el Harp Helú, el más alto |
| **Rolling** | % de rolling en el tercio alto de la liga (≥ 48 %) | El fly cuesta 3.5 veces más en la CDMX |
| **Si vive de la recta** | Que su recta sea élite a nivel del mar (Stuff+ ≥ 114, top 10 %), porque llega a la CDMX con unos 13 puntos menos | Delta de la recta |
| **Comando** | Location+ alto | El modelo de ubicación predice en altitud extrema aunque no la haya visto (D-037). Ojo: Location+ se repite menos de un año a otro (r 0.67) que Stuff+ (0.83) |

**Por qué estas features importan más en altitud:** el aire quita la parte del valor que viene del
giro (movimiento inducido y "ride"), pero no la que viene de la velocidad, el ángulo, la ubicación o
el engaño de velocidad. Y en la CDMX el error se paga más caro: la pelota vuela más (34 ft más con el
mismo contacto, D-021) y un fly cuesta 3.5 veces más.

## Límites

- La evidencia entre tipos es fuerte; la de arsenal es una tendencia; dentro de cada tipo no hay
  evidencia.
- Que la slider pierda poco **no prueba** que lanzar más sliders mejore a un pitcher: es asociación.
- 15 y 24 pitchers en la prueba real de arquetipos: suficientes para la dirección, no para la cifra.
