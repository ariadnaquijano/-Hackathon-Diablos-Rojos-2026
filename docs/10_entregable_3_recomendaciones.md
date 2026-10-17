# Entregable 3 · Recomendaciones operativas

> **Para quién:** pitching coach y director deportivo.
> **Evidencia:** las mismas fuentes de `docs/08_entregable_1_scores.md` y
> `docs/09_entregable_2_perfil_ideal.md`, más `docs/03_target.md` (valor del conteo).
> **Herramientas:** simulador (`python src/simulador.py`, http://127.0.0.1:8050) y fichas de pitchers
> (/fichas).
> **Cómo leer la fuerza de cada recomendación:**
> - **Probado:** intervalo de 95 % fuera de cero.
> - **Tendencia:** apunta al mismo lado, pero el intervalo toca cero.
> - **Opción:** sin prueba; queda a criterio del cuerpo técnico.

## 1. ¿Qué perfiles ganan Stuff+ relativo en la CDMX?

En la CDMX todos los pitches pierden algo. "Ganar relativo" es perder menos que el resto y subir en
el orden de la liga.

| Perfil | Delta en el Harp Helú | Fuerza | Explicación física |
|---|---|---|---|
| **Curva** | −0.7 (−9.5 a +8.1) | **Probado:** pierde 0.38 carreras por 100 menos que la recta (0.10 a 0.64) | Pierde algo de movimiento (k 1.19), pero en los datos su valor casi no cambia. *Hipótesis:* depende más de la diferencia de velocidad y del ángulo que del giro. |
| **Slider** | −6.9 (−14.8 a +1.1) | Tendencia: pierde menos que la recta, sin probarse (0.21 menos, de −0.04 a +0.45) | Giro de bala (*gyro*): su movimiento vertical depende poco del Magnus (k 0.68, el más bajo). |
| **Arsenal de rompimiento** (slider + curva ≥ 40 %) | Stuff+ en la CDMX 90.9 contra 86.8 del de recta y sinker | Tendencia | Menos de su valor viene del efecto que el aire debilita. |
| **Pitcher de rolling** | Un rolling vale casi lo mismo en las dos altitudes (+0.02) | Probado a nivel liga; tendencia por pitcher | El aire hace volar los flies, no los rollings. |

## 2. ¿Qué perfiles pierden Stuff+ en altitud?

| Perfil | Delta en el Harp Helú | Fuerza | Explicación física |
|---|---|---|---|
| **Recta de "ride"** | −13.0 (−17.3 a −8.8) | Probado | Pierde unos 4 in de IVB: el "ride" que hace fallar por debajo sale del Magnus. |
| **Sinker** | −13.3 (−20.5 a −6.1) | Probado | Pierde caída y corrida hacia el brazo (k horizontal 1.75). |
| **Cambio** | −9.7 (−17.5 a −2.8) | Probado | Su corrida horizontal es lo más sensible al aire (k 2.06). **No gana valor contra la recta en altura:** pierden casi igual (H2 no concluyente). |

**Riesgo adicional de contacto duro y jonrón** (2024–2025, altitud extrema contra nivel del mar):

| Riesgo | CDMX | Nivel del mar | Diferencia |
|---|---|---|---|
| Jonrones por fly | 16.1 % | 12.8 % | **+3.3 puntos** (2.2 a 4.6) |
| Contacto duro (95+ mph) | 25.5 % | 22.4 % | **+3.0 puntos** (2.3 a 3.8) |
| Carreras por 100 batazos | 6.9 | 3.1 | **+3.7** (3.0 a 4.5) |
| Valor de un fly | 0.136 carreras | 0.039 | **3.5 veces más** |

Mismo pitcher y mismo pitch, carreras por 100 batazos en la CDMX: **rectas +3.4** (1.1 a 5.8) y
**sinkers +4.5** (1.3 a 7.6). Contacto duro con el sinker: +5.6 puntos (2.2 a 9.0).

## 3. ¿Cómo perfilar a un prospecto o agente libre para Diablos Rojos?

### Paso 1: su Stuff+ y lo que le cobra la CDMX

- **Si ya lanzó en la LMB:** abrir su ficha (/fichas).
  - Revisar Stuff+, Location+ y Pitching+, el **riesgo en el Harp Helú** (tercio bajo, medio o alto)
    y su arsenal.
- **Si viene de fuera o solo hay sus números de TrackMan:** meter cada pitch en el simulador.
  - Indicar "Dónde se midió": nivel del mar o Harp Helú.
  - Da su Stuff+ a nivel del mar y en el Harp Helú, y la mediana de cada tipo en casa como contexto.

### Paso 2: la lista de chequeo

Los umbrales de Stuff+ están en la escala de la ficha (cada pitch contra su tipo, entre pitchers).
El simulador usa su propia escala, contra perfiles promedio, así que sus números no son idénticos.

| Pregunta | Señal verde | Señal roja |
|---|---|---|
| ¿Su mejor pitch sobrevive a la altura? | Curva (probado) o slider (tendencia) con Stuff+ ≥ 100 contra su tipo | Todo su valor está en la recta o el sinker |
| ¿Cómo es su mezcla? | Rompimiento ≥ 40 % (o un rompimiento que pueda usar más) | Recta + sinker ≥ 60 % sin un rompimiento bueno |
| Si vive de la recta, ¿es élite? | Stuff+ de la recta ≥ 113 en su ficha (top 10 % de las rectas): en la CDMX queda sobre 100 | Recta promedio: en la CDMX queda unos 13 puntos abajo |
| ¿Saca rollings? | Rolling ≥ 48 % (tercio alto; la mediana es 45 %) | Rolling ≤ 41 % y mucho fly |
| ¿Cuánta muestra hay? | 450+ pitches y dos temporadas | Muestra corta: los componentes se mueven |

### Paso 3: cómo pesar la información

- **Para proyectar el año siguiente, pesa más su historia** (encogida hacia la media) que su Stuff+.
  Es lo que mejor predijo 2026.
- **El Stuff+ manda cuando no hay historia en la liga** (64 de 178 pitchers de 2026 no la tenían) o
  cuando la historia es de otra altitud. Es lo único que se traslada entre estadios sin castigar al
  pitcher.
- **Location+ se repite menos de un año a otro** (r 0.67, contra 0.83 de Stuff+). Un buen año de
  ubicación es una buena señal, no una garantía.

### Ejemplo de lectura

> Agente libre con recta de Stuff+ 105 (60 % de uso) y slider de 103. En la CDMX su recta baja a unos
> 92 y su slider a unos 96. Con un rolling de 40 % (tercio bajo de la liga), el aire le cobra más en
> el contacto. **Lectura:** tiene un pitch que resiste la altura (la
> slider), pero hoy no es su pitch principal; vale como opción si el cuerpo técnico puede trabajar su
> mezcla, no por su Stuff+ actual.

## 4. Para el plan de juego en casa (opciones)

- **Ponerse adelante vale más en la CDMX** (probado): un strike en 0-0 le quita 0.043 carreras al
  rival, contra 0.034 a nivel del mar. La cuarta bola en 3-2 regala 0.23 contra 0.18.
- **Los flies son el riesgo principal en casa** (probado a nivel liga). Cuidar el contacto elevado
  pesa más ahí que en la costa.
- **Apoyarse más en la curva, y quizá la slider, en casa** (opción): la curva pierde menos que la recta
  (probado); la slider apunta igual sin probarse. Además **no está
  probado** que usarlas más mejore el resultado. Usarlas más cambia cómo las espera el bateador.

## Lo que NO recomendamos (no hay respaldo)

- Pedir más spin para compensar la altura: el aire quita movimiento sin cambiar el spin.
- Buscar cambios "porque ganan en altura": en nuestros datos pierden casi como el sinker.
- Dar la pérdida exacta en carreras de un pitcher específico: el estimado ordena, pero no es preciso.
