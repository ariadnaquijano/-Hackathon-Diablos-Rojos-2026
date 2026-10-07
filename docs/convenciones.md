# Convenciones del equipo

## Código

- **Un script por etapa** en `src/`, ejecutable de principio a fin (`python src/<etapa>.py`).
- **Nombres que expliquen qué hacen**: `within_pitcher_movement_change`, no `calc2`.
- **Funciones pequeñas** con una sola responsabilidad.
- **Sin números mágicos**: umbrales como constantes con nombre al inicio del archivo.
- **Comentarios solo para el "por qué"**; el "qué" lo debe decir el código.
- **Sin código muerto** ni celdas de prueba olvidadas.
- Rutas relativas a la raíz del proyecto; nunca rutas personales (`/Users/...`).
- Los datos crudos (`data/raw/`) son de solo lectura.

## Documentos

- En español, frases cortas, pensando en alguien que no estuvo en la reunión.
- Cada etapa responde: **qué hicimos, por qué, qué descartamos y qué impacto tuvo**.
- Toda cifra debe salir de un script en `src/` e indicar de cuál.
- Términos nuevos van al [`glosario.md`](glosario.md); decisiones, a [`decisiones.md`](decisiones.md).

## Rigor estadístico

- **No inventar ni inflar.** Toda cifra sale de un script; si un resultado es débil o pierde contra
  el modelo base, se reporta igual.
- **Plan antes que datos.** La pregunta, la métrica y la comparación se escriben antes de correr.
  Lo que surge después se marca como exploratorio.
- **Modelos base siempre** (D-020): todo modelo se compara contra la media, la media por conteo, la
  media por tipo de pitch y una regresión simple.
- **2026 es intocable** hasta la evaluación final; nada se ajusta mirándolo.
- **Intervalos de 95 % remuestreando pitchers completos**, porque los pitches de un mismo pitcher no
  son independientes.
- **Tamaño del efecto en unidades de béisbol**, no solo si es "significativo".
- **Límites explícitos** al final de cada documento.

## Commits y pull requests

- Mensajes en lenguaje natural, en imperativo, explicando qué cambia y por qué.
  Ejemplo: `Agrega reglas de limpieza para rangos físicos de velocidad y spin`.
- Un cambio lógico por commit.
- Sin firmas ni atribuciones automáticas de herramientas.
- Nunca se hace commit de archivos dentro de `data/`.
