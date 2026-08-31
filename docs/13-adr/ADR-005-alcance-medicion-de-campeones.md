# ADR-005 — El alcance es la medición de campeones, no el análisis de partidas

> Estado: **aceptada** · Fecha: 31/08/2026

## Contexto

La propuesta original y el Informe Inicial contemplaban dos artefactos de salida: un
`champion_features.csv` con la medición de cada campeón, y un `match_features.csv` con
aproximadamente 117 features por partida, construido cruzando esa medición con el dataset histórico
de partidas del laboratorio.

El segundo artefacto tiene tres dependencias que **no están bajo control de la práctica**: que el
dataset exista, que esté disponible a tiempo, y que incluya el rol que jugó cada campeón en cada
partida —sin lo cual las features de matchup y sinergia son incalculables—. Además, construir
features por partida es una decisión de modelado que pertenece a quien entrena el modelo.

## Decisión

**DraftSense mide campeones y entrega esa medición.** No consume el dataset de partidas del
laboratorio, no construye features por partida, no se integra con el modelo predictivo y no
interpreta resultados.

La salida son tres archivos —`champion_features`, `matchup_matrix` y `duo_features`— más el Informe
de Calidad de Datos. La frontera de la práctica es el CSV.

## Alternativas consideradas

- **Mantener `match_features.csv` en el alcance.** Entregable más vistoso, pero con una dependencia
  externa crítica en la semana 9 de un cronograma de 12, y sobre una decisión de modelado que es
  del laboratorio.
- **Entregar el módulo `build_match_features` sin ejecutarlo**, documentado y probado contra datos
  sintéticos. Desacopla del dataset pero deja código sin uso real y una promesa a medio cumplir.

## Consecuencias

- **Difiere del Informe Inicial firmado**, que compromete `match_features.csv` en el objetivo de
  §3.2, en las actividades de §6 y en los entregables de las semanas 10 y 11. El ajuste debe
  registrarse y justificarse en el **Informe de Avance de la semana 6**.
- La métrica de impacto se reformula: en vez de "~117 features por partida frente a 14", pasa a ser
  **20 magnitudes medidas por campeón, todas continuas, con intervalo de confianza y soporte
  muestral, versionadas por parche (126 columnas), frente a 7 etiquetas binarias de un anotador
  único**. Es una afirmación más chica en apariencia y más fuerte en sustancia, porque describe
  exactamente lo que el sistema hace y no depende de nadie más.
- Se liberan las semanas 10 y 11, que pasan a reforzar la validación de confiabilidad y la segunda
  oleada de recolección — que es donde está el verdadero cuello de botella del proyecto.
- El riesgo de quedar bloqueado por una dependencia externa desaparece.
