# ADR-013 — Las honeypots se derivan del kit del campeón, no del juicio experto

> Estado: **aceptada** · Fecha: 01/09/2026

## Contexto

El control de calidad depende de intercalar preguntas de respuesta conocida (RF-201). Hace falta
decidir **de dónde sale esa respuesta conocida**, y la decisión es más delicada de lo que parece,
porque una honeypot mal elegida no mide calidad: castiga a quien opina distinto.

DraftSense existe para reemplazar el etiquetado de **un solo anotador** por una medición
crowdsourced. Si las honeypots salieran del criterio de una sola persona —el alumno, o el tutor—
el instrumento que valida las respuestas tendría exactamente el defecto que el proyecto viene a
corregir, y cualquier respondedor que discrepe con esa persona sería penalizado como si no estuviera
prestando atención.

## Decisión

Cada honeypot se redacta a partir de un **hecho verificable en el kit del campeón**, y el hecho se
escribe en un campo `rationale` obligatorio del seed. "Yasuo tiene un dash y Malphite no" entra;
"Yasuo se siente más móvil" no.

Consecuencias directas del criterio:

- Sólo seis de las ocho dimensiones admiten honeypots: `mobility`, `cc`, `poke`, `waveclear`,
  `engage` y `peel`. **`scaling` y `pick` no tienen ninguna**, porque no hay un hecho del kit que las
  resuelva sin discusión.
- **Todas las honeypots son de tipo 1.** Un slider de minuto de pico no tiene respuesta incorrecta,
  un matchup depende del parche, y los atributos son una proporción por definición.

Como red de seguridad, el sistema **vigila el *pass rate* de sus propias honeypots** y retira
automáticamente cualquiera que baje de 0.85, recalculando el trust de quienes la recibieron. El
monitoreo **sólo puede retirar honeypots, nunca crearlas**.

## Alternativas consideradas

- **Catálogo redactado por criterio experto y revisado por el tutor.** Cubre las ocho dimensiones y
  es rápido de producir. Se descartó como fuente principal por lo dicho en el contexto: reintroduce
  al anotador único en el mecanismo de validación. Sobrevive como **revisión**, no como origen: el
  tutor verifica que cada `rationale` describa lo que la habilidad efectivamente hace.
- **Promoción por consenso emergente** — convertir en honeypot toda pregunta real que alcance 95 %
  de acuerdo entre respondedores de trust alto. Es tentadora porque se calibra sola y no tiene sesgo
  de autor, pero es **circular**: convierte al consenso en verdad y penaliza a quien disiente, que
  es justamente lo que las honeypots no deben hacer. Además no existe el día 1, que es cuando más
  falta hace.
- **Honeypots de atención explícitas** del tipo "seleccioná la tercera opción". Detectan bots con
  certeza, pero son inmediatamente reconocibles y rompen RF-202: una pregunta que se ve distinta
  invalida el mecanismo entero para todas las demás.

## Consecuencias

- La respuesta esperada es **auditable por cualquiera**, sin apelar a la autoridad de quien la
  escribió. Es lo que hace que el módulo de calidad se pueda defender ante el tutor de la
  Universidad.
- **Dos dimensiones quedan sin honeypots**, y no importa: la honeypot mide al respondedor, no a la
  dimensión. Que alguien conteste con atención no depende de qué dimensión se le preguntó.
- El catálogo es **más chico y más caro de escribir** que uno de juicio experto: cada par exige
  encontrar y redactar el hecho que lo sostiene. ~40 pares por parche es un trabajo de horas, no de
  minutos.
- Un **rework de campeón puede invalidar honeypots**. El monitoreo del pass rate lo detecta solo,
  pero con retraso: entre el parche y la detección, algunos respondedores pierden trust
  injustamente. Por eso el retiro **recalcula hacia atrás** el trust de los afectados.
- El criterio se apoya en leer descripciones de habilidades a mano. **Data Dragon no expone un campo
  `dash` ni una taxonomía de control de masas**, así que la verificación es humana; lo que el
  `rationale` garantiza es que sea reproducible, no que sea automática.
