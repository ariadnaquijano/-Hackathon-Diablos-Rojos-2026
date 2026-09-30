# Glosario

Términos ordenados por tema. Si algo del proyecto no está aquí, agrégalo.

## Métricas del reto

| Término | Qué significa |
|---|---|
| **Stuff+** | Calidad de un pitch solo por su física (velocidad, movimiento, spin, release). 100 = promedio de la liga; cada 10 puntos es una desviación estándar. |
| **Location+** | Qué tan bien ubicado estuvo el pitch, dado su tipo, el conteo y el bateador. |
| **Pitching+** | Combinación de stuff, ubicación, arsenal y contexto. |
| **z-score** | Cuántas desviaciones estándar está un valor por encima o debajo del promedio. |
| **xRunValue (xRV)** | Carreras que se espera que un pitch sume o reste al rival. Se usa el valor *esperado* porque el resultado real tiene mucha suerte. |
| **Run value** | Cambio en carreras esperadas causado por un pitch (por ejemplo, pasar de 1-1 a 1-2 le quita carreras esperadas al rival). |
| **Baseline** | Modelo mínimo a superar; en este reto, el xRV promedio por conteo. |

## Física del pitch

| Término | Qué significa |
|---|---|
| **Efecto Magnus** | Fuerza que genera el giro de la pelota al empujar el aire; es lo que hace que los pitches "rompan". Es proporcional a la densidad del aire. |
| **Densidad del aire (ρ)** | Cuánta masa de aire hay por volumen. En CDMX es ~20 % menor que a nivel del mar, así que hay menos Magnus y menos arrastre. |
| **Arrastre (drag)** | Resistencia del aire que frena la pelota. Menos densidad = menos frenado = la bola llega más rápido y los batazos vuelan más. |
| **Spin rate** | Revoluciones por minuto de la pelota. |
| **Spin axis / Tilt** | Dirección del eje de giro (en grados o como reloj). Define hacia dónde se mueve el pitch. |
| **Spin efficiency / gyro** | Qué fracción del giro produce movimiento. Un pitch "gyro" gira como bala: mucho spin, poco Magnus. |
| **IVB (Induced Vertical Break)** | Movimiento vertical causado por el giro, sin contar la gravedad. Una recta con IVB alto "sube" (ride). |
| **HB (Horizontal Break)** | Movimiento horizontal causado por el giro. |
| **VertBreak** | Caída vertical total incluyendo la gravedad. |
| **Release (RelHeight, RelSide)** | Punto donde el pitcher suelta la pelota. |
| **Extensión** | Qué tan adelante del montículo suelta la pelota; más extensión = menos tiempo de reacción para el bateador. |
| **VAA (Vertical Approach Angle)** | Ángulo con el que el pitch llega al plato. Una recta "plana" arriba de la zona es difícil de conectar. |
| **Effective velocity** | Velocidad percibida por el bateador según extensión y ubicación. |

## Tipos de pitch

| Término | Qué significa |
|---|---|
| **Four-Seam** | Recta de cuatro costuras; su valor viene de velocidad y ride. |
| **Sinker** | Recta que corre hacia el lado del brazo y cae; busca roletazos. |
| **Cutter** | Recta que corta ligeramente hacia el lado del guante. |
| **Slider** | Rompimiento hacia el lado del guante, más rápido que la curva. |
| **Sweeper** | Slider con mucho movimiento horizontal ("barre"). |
| **Curveball** | Rompimiento con mucha caída. |
| **Changeup / Splitter** | Pitches lentos que imitan a la recta; engañan por diferencia de velocidad y caída. |
| **Arsenal / repertorio** | Conjunto de pitches de un lanzador. |
| **Túnel** | Qué tan parecidos se ven dos pitches al salir de la mano antes de separarse. |

## Resultados

| Término | Qué significa |
|---|---|
| **Whiff** | Swing y fallo. |
| **Chase** | Swing a un pitch fuera de la zona. |
| **Called strike** | Strike cantado sin swing. |
| **BIP (ball in play)** | Bola puesta en juego. |
| **Groundball (GB)** | Roletazo; más valioso en altitud porque no puede ser jonrón. |
| **Hard contact / barrel** | Contacto con alta velocidad de salida y buen ángulo; el tipo de batazo más peligroso. |
| **Exit speed / Launch angle** | Velocidad y ángulo del batazo al salir del bat. |

## Modelado

| Término | Qué significa |
|---|---|
| **Feature** | Variable de entrada del modelo. |
| **Target** | Lo que el modelo intenta predecir. |
| **Fuga de datos (leakage)** | Usar como entrada información que no estaría disponible al momento de predecir (por ejemplo, el resultado del pitch). Infla métricas y engaña. |
| **Holdout** | Datos apartados que el modelo nunca ve al entrenar; sirven para medir si generaliza. |
| **Pitcher holdout** | Evaluar en pitchers que no estuvieron en entrenamiento. |
| **Calibración** | Que una probabilidad predicha de 30 % ocurra ~30 % de las veces. |
| **Gradient boosting (LightGBM / XGBoost)** | Modelo de árboles que captura relaciones no lineales; estándar en Stuff+. |
| **SHAP** | Método para explicar cuánto aportó cada variable a una predicción. |
| **Contrafactual** | "¿Qué hubiera pasado si…?" — aquí, el mismo pitch lanzado en otro ambiente. |
| **Confusor** | Variable que afecta a la vez a la causa y al efecto y crea una relación falsa. |

## Conceptos propios del proyecto

| Término | Qué significa |
|---|---|
| **Traductor físico (etapa A)** | Modelo que predice cómo se moverá un pitch según la densidad del aire. |
| **Modelo de resultado (etapa B)** | Modelo que predice la efectividad de un pitch a partir de su forma. |
| **Pasaporte de altitud** | Proyección del Stuff+ de un pitcher en el Harp Helú usando solo datos de nivel del mar. |
| **Índice de dependencia del Magnus** | Qué tanto del movimiento de un pitch depende del giro; alto = frágil en altitud. |
| **Proxy de arrastre** | Medida de cuánto frena la pelota, calculada de la trayectoria de Trackman; aproxima la densidad del aire de cada juego. |
| **Corrección de punto de mira** | Cuántas pulgadas ajustar el objetivo de un pitch en altitud para que llegue donde el pitcher quiere. |
| **Residente / visitante** | Pitcher que lanza ≥ 50 % de sus pitches en altitud extrema, contra uno que no. |
| **Razón de aire (`air_ratio`)** | Arrastre de un juego ÷ arrastre típico a nivel del mar esa temporada. 1.0 = nivel del mar; ~0.84 = altitud extrema. |
| **Movimiento equivalente a nivel del mar** | Cuánto se movería el pitch con aire de nivel del mar: movimiento ÷ razón de aire. Permite comparar formas entre estadios. |
| **Recta principal** | El pitch rápido (four-seam, sinker o cutter) que más usa un pitcher; referencia para las diferencias de arsenal. |
| **Platoon** | Si el bateador batea del mismo lado que lanza el pitcher (en general favorece al pitcher). |
| **Gyro slider** | Slider con mucho spin "de bala" y poco movimiento por Magnus; en los datos casi no pierde efectividad en altitud. |
