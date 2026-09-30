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

## Commits y pull requests

- Mensajes en lenguaje natural, en imperativo, explicando qué cambia y por qué.
  Ejemplo: `Agrega reglas de limpieza para rangos físicos de velocidad y spin`.
- Un cambio lógico por commit.
- Sin firmas ni atribuciones automáticas de herramientas.
- Nunca se hace commit de archivos dentro de `data/`.
