# ADR-014 — La tabla de posiciones filtra por confianza, sin exponerla

> Estado: **aceptada** · Fecha: 01/09/2026

## Contexto

La tabla de posiciones es el instrumento de la meta M5 —al menos 1 000 respuestas reales— y ordena
por cantidad de respuestas. El límite de tasa permite 1 500 respuestas por día y por respondedor.

De ahí sale un agujero de incentivos: **alguien que conteste al azar a toda velocidad lidera la
tabla**. Sus respuestas se descartan en la exportación por tener trust bajo, pero públicamente gana,
y la tabla es la pantalla que el sistema usa para decirle a la gente qué comportamiento valora.
Estaríamos premiando en primer plano exactamente lo que el módulo de calidad existe para descartar.

La restricción que complica la solución obvia es RF-207: **el trust score no se expone en ninguna
interfaz pública**, porque exponerlo convierte la calidad en una métrica a optimizar y le enseña al
que responde mal a evadir la detección en vez de a responder mejor.

## Decisión

La tabla de posiciones excluye a los respondedores con `is_flagged = true` **y** a los que están por
debajo de `export.min_trust` (0.30). El orden sigue siendo por cantidad de respuestas de la ventana.

El umbral es **literalmente la misma clave de `app_settings`** que usa el filtro de la exportación,
no una copia. Así la tabla significa "quién contribuyó al conjunto de datos", y ese significado no
se puede desincronizar en la primera recalibración.

## Alternativas consideradas

- **Ordenar por `answers_count × trust_score`.** Alinea los incentivos a la perfección y es la
  primera idea de cualquiera. **Viola RF-207 de frente**: quien vea su puntaje y sepa su cantidad de
  respuestas —que su propio perfil le muestra— despeja su trust con una división.
- **Dejar la tabla como estaba**, filtrando sólo por `is_flagged`. Cero riesgo de filtración, cero
  alineación. Deja el agujero abierto y obliga a documentarlo como límite conocido.
- **Contar sólo las respuestas que entraron al último export.** Equivalente en efecto, pero la tabla
  se congela entre corridas de agregación y se vuelve incomprensible para quien responde hoy y no ve
  moverse su número.

## Consecuencias

- La tabla premia **volumen con calidad mínima**, no volumen a secas.
- Se filtra **un bit**: quien desaparece de la tabla puede inferir que está bajo el umbral. Es un bit
  y no un valor — no se puede saber si se está en 0.29 o en 0.05, ni qué acción movió la aguja, así
  que no habilita optimizar contra la métrica. Es la diferencia entre esta opción y la de ordenar por
  trust.
- **Nadie honesto lo ve nunca.** Un respondedor nuevo arranca en 0.500 y cruzar 0.300 hacia abajo
  exige fallar unas cinco honeypots.
- RF-304 cambia de redacción: excluye a los marcados **y** a los que quedan fuera del export por
  confianza.
- Si el laboratorio recalibra `export.min_trust` con los datos del piloto, la tabla de posiciones
  cambia con él. Es la consecuencia buscada de compartir la clave, pero conviene tenerlo presente:
  subir el umbral saca gente de la tabla, y alguien lo va a notar.
