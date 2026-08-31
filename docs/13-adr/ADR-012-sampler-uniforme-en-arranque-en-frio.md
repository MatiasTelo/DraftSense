# ADR-012 — Sampler uniforme durante el arranque en frío

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

La función de prioridad del sampler pondera escasez, entropía y déficit de cobertura. Dos de esos
tres términos **necesitan datos que al arrancar no existen**: la entropía de una pregunta sin
respuestas no está definida, y el déficit de cobertura se calcula contra una mediana global que con
cero respuestas es cero.

Lo mismo pasa con el feedback post-respuesta: mostrar "el 74 % coincidió con vos" requiere un
consenso que todavía no hay.

Sin una regla explícita, el sampler arranca operando sobre ruido y toma decisiones fuertes a partir
de las dos o tres primeras respuestas de cada pregunta.

## Decisión

El sampler opera en dos regímenes:

- **Arranque en frío.** Mientras una pregunta tiene menos de **5 respuestas**, se selecciona por
  muestreo uniforme sobre el pool de candidatas, sin función de prioridad.
- **Régimen normal.** A partir de la quinta respuesta, entra la función de prioridad completa.

El feedback de consenso se omite mientras la pregunta tiene menos de **20 respuestas**; en su lugar
la interfaz muestra *"you're one of the first to answer this"*.

Los datos de arranque los genera el **lanzamiento cerrado de la semana 7** con usuarios del ámbito
académico, antes de la difusión pública.

## Alternativas consideradas

- **Sembrar con el etiquetado actual de 7 tags** como prior del sampler. Arranca más dirigido, pero
  hereda el sesgo del anotador único que el proyecto viene justamente a reemplazar. Aunque el prior
  se usara sólo para ordenar preguntas y nunca para el export, contaminaría qué se pregunta y por lo
  tanto qué se puede descubrir.
- **Ronda de calibración interna** con el equipo del laboratorio respondiendo una tanda dirigida.
  Datos de arranque de buena calidad pero de muy pocos anotadores, con el mismo problema de sesgo en
  menor escala. Queda como complemento del lanzamiento cerrado, no como sustituto.

## Consecuencias

- Las primeras respuestas se reparten **parejo**, que es lo mejor que se puede hacer sin información.
- El umbral de 5 es un juicio: bajo suficiente para salir rápido del régimen uniforme, alto
  suficiente para que la entropía inicial no sea puro ruido de muestreo.
- El lanzamiento cerrado de la semana 7 pasa a tener una función estadística además de la de
  detectar problemas de usabilidad, y su tamaño debe alcanzar para sembrar el pool del tier 1.
- Los dos umbrales (5 para el régimen, 20 para el feedback) son parámetros de configuración, no
  constantes en el código.
