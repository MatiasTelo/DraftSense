# 03 — Criterios de aceptación

> Estado: **v1** · Última revisión: 31/08/2026

Criterios verificables en formato Dado/Cuando/Entonces. Tienen doble uso: son la **definición de
«terminado»** de cada funcionalidad y el **guion de los tests automatizados**.

Cada criterio referencia el requerimiento que verifica y el nivel de prueba que le corresponde:
`U` unitaria · `I` integración · `C` componente de UI · `E2E` extremo a extremo.

---

## 1. Sesión e identidad

### CA-001 · Crear sesión anónima — RF-001 · `I`
**Dado** un visitante sin cookie
**Cuando** solicita una sesión
**Entonces** el sistema responde `201`, envía una cookie `HttpOnly; Secure; SameSite=Lax` con
vencimiento a 180 días, y crea un respondedor con trust score `0.500`.

### CA-002 · La creación de sesión es idempotente — RF-002 · `I`
**Dado** un visitante con cookie válida
**Cuando** vuelve a solicitar una sesión
**Entonces** el sistema **no** crea un respondedor nuevo, devuelve el mismo `respondent_id` y
actualiza `last_seen`.

### CA-003 · El token no se almacena en claro — RF-003 · `I`
**Dado** una sesión recién creada
**Cuando** se inspecciona la fila del respondedor
**Entonces** `session_token_hash` tiene 64 caracteres hexadecimales y **no** coincide con el valor
de la cookie.

### CA-004 · El esquema no admite datos personales — RF-006, RNF-05 · `I`
**Dado** el esquema completo de la base
**Cuando** se recorren todas las columnas
**Entonces** no existe ninguna que almacene email, nombre, dirección IP en claro ni identificador
de cuenta de Riot.

> Este criterio se automatiza como un test que lee el catálogo de Postgres y falla ante una columna
> nueva cuyo nombre coincida con una lista de patrones prohibidos. Es una salvaguarda contra el
> descuido futuro, no contra el diseño actual.

### CA-005 · Omitir el onboarding es una respuesta — RF-005 · `I`
**Dado** un respondedor que toca *Skip*
**Cuando** se guarda el onboarding con los tres campos nulos
**Entonces** `onboarding_seen` queda en `true` y no se le vuelve a preguntar en sesiones futuras.

---

## 2. Entrega de preguntas

### CA-101 · Entrega por lotes — RF-101 · `I`
**Dado** un respondedor con sesión activa
**Cuando** pide 5 preguntas
**Entonces** recibe exactamente 5, todas del parche vigente y ninguna repetida dentro del lote.

### CA-102 · Las primeras tres son de tipo 1 — `20-tipos-de-pregunta.md` §7 · `I`
**Dado** un respondedor sin respuestas previas
**Cuando** pide su primer lote
**Entonces** las tres primeras preguntas son de tipo `pairwise_dimension`.

### CA-103 · Los honeypots son indistinguibles — RF-202 · `I`
**Dado** un lote que contiene una pregunta honeypot
**Cuando** se inspecciona la respuesta HTTP completa
**Entonces** no aparece el campo `is_honeypot` ni `expected_answer` en ninguna forma.

### CA-104 · Los enunciados llegan compuestos — RF-112 · `I`
**Dado** una pregunta de tipo `lane_matchup` entre Syndra y Zed
**Cuando** se recibe del servidor
**Entonces** las etiquetas de las opciones dicen `"Syndra wins hard"` y `"Zed wins hard"`, no
`"A wins hard"` ni una plantilla sin resolver.

### CA-105 · Las duplas se entregan como arreglo — RF-105, RF-106 · `I`
**Dado** una pregunta de tipo 3 variante 2v2 o de tipo 4
**Cuando** se recibe del servidor
**Entonces** cada lado tiene exactamente dos elementos en `champions`, y los cuatro campeones son
distintos entre sí.

### CA-106 · Latencia de entrega — RNF-01 · `E2E`
**Dado** una base con 10 000 preguntas y 8 000 respuestas
**Cuando** se piden 100 lotes consecutivos
**Entonces** el percentil 95 del tiempo de respuesta es menor a 100 ms.

---

## 3. Registro de respuestas

### CA-201 · Registro correcto — RF-108, RF-109 · `I`
**Dado** una pregunta de tipo 1
**Cuando** se responde `{"choice": "a"}` con 2 140 ms
**Entonces** se crea una fila en `responses` con ese `answer`, ese tiempo, el `type` y el `patch_id`
de la pregunta, y el contador del respondedor sube en uno.

### CA-202 · Forma inválida rechazada — RF-108 · `I`
**Dado** una pregunta de tipo `peak_timing`
**Cuando** se responde `{"choice": "a"}`
**Entonces** el sistema responde `400` con código `answer_shape_mismatch` y **no se crea ninguna
fila**.

### CA-203 · La base rechaza la forma inválida por sí sola — RF-108, RNF-04 · `I`
**Dado** un `INSERT` directo en `responses` con `type = 'peak_timing'` y `answer = '{"minute": 99}'`
**Cuando** se ejecuta saltando la capa de aplicación
**Entonces** Postgres lo rechaza por violación de `responses_answer_shape`.

> Este criterio es el que garantiza que la validación no dependa de la disciplina del código. Con
> una tabla append-only, un dato mal formado no se puede corregir después
> ([ADR-002](13-adr/ADR-002-responses-append-only.md)).

### CA-204 · Respuesta duplicada rechazada — RF-110 · `I`
**Dado** un respondedor que ya contestó la pregunta 88412
**Cuando** la responde otra vez sin marcarla como retest
**Entonces** el sistema responde `409` con código `duplicate_response`.

### CA-205 · El retest sí se admite — RF-203 · `I`
**Dado** el mismo escenario, pero con la respuesta marcada como repetición de la anterior
**Entonces** el sistema la registra correctamente y `is_retest_of` apunta a la respuesta original.

### CA-206 · Traits inexistentes rechazados — RF-108 · `I`
**Dado** una pregunta de tipo 5
**Cuando** se responde con un código de atributo que no existe o está inactivo
**Entonces** el sistema responde `400` con código `unknown_trait_code`.

### CA-207 · La lista vacía de traits es válida — `20-tipos-de-pregunta.md` §6 · `I`
**Dado** una pregunta de tipo 5
**Cuando** se responde `{"traits": []}`
**Entonces** se registra correctamente: significa "ninguno de estos", que es información real.

### CA-208 · El crudo es inmutable — RNF-04 · `I`
**Dado** una conexión con el rol de aplicación
**Cuando** se intenta `UPDATE` o `DELETE` sobre `responses`
**Entonces** Postgres lo rechaza por permisos insuficientes.

### CA-209 · Límite de tasa — RF-209 · `I`
**Dado** un respondedor que envió 40 respuestas en el último minuto
**Cuando** envía la número 41
**Entonces** el sistema responde `429` con `Retry-After`, y las cabeceras `X-RateLimit-*` reflejan
el estado real.

---

## 4. Calidad de datos

### CA-301 · Cadencia de honeypots — RF-201 · `I`
**Dado** un respondedor que contesta 60 preguntas seguidas
**Cuando** se cuentan los honeypots recibidos
**Entonces** son entre 4 y 6, y ninguna ventana de 15 preguntas queda sin ninguno.

### CA-302 · El honeypot fallado baja el trust — RF-205 · `U`
**Dado** un respondedor con trust `0.500` y sin honeypots previos
**Cuando** falla su primer honeypot
**Entonces** su trust score baja, y el nuevo valor coincide con el que produce la fórmula
especificada.

### CA-303 · El trust score no se expone — RF-207 · `I`
**Dado** un respondedor con trust `0.812`
**Cuando** consulta su perfil o la tabla de posiciones
**Entonces** el valor no aparece en la respuesta, ni directamente ni por medio de ninguna métrica
derivada.

### CA-304 · Respuesta apurada detectada — RF-204 · `U`
**Dado** una respuesta con menos de 800 ms
**Cuando** corre la detección de patrones degenerados
**Entonces** el contador de respuestas apuradas del respondedor sube y su trust se recalcula.

### CA-305 · Straightlining detectado — RF-204 · `U`
**Dado** ocho respuestas consecutivas del mismo respondedor en la misma posición de opción
**Cuando** corre la detección
**Entonces** la racha se marca como *straightlining* y el trust se recalcula.

### CA-306 · Huella duplicada marcada — RF-208 · `I`
**Dado** una huella con seis identidades distintas en 24 horas
**Cuando** corre el job diario
**Entonces** las seis quedan marcadas, y **ninguna respuesta se borra**.

### CA-307 · Los marcados quedan fuera del export — RF-206 · `I`
**Dado** un respondedor marcado con 50 respuestas
**Cuando** se genera una exportación
**Entonces** sus respuestas no entran en la agregación, pero siguen presentes en `responses`.

### CA-308 · `unknown` en una honeypot es neutro — RF-205 · `U`
**Dado** un respondedor que recibe una honeypot
**Cuando** responde `unknown`
**Entonces** `honeypot_attempts` y `honeypot_passed` quedan iguales y su trust score no cambia.

### CA-309 · La honeypot mala se retira sola — RF-205 · `U`
**Dado** una honeypot cuyo *pass rate* cae a `0.80` sobre 40 respuestas
**Cuando** corre el refresco de estadísticas
**Entonces** queda con `is_honeypot = false` y el trust de todos los que la habían recibido se
recalcula como si nunca hubiera existido.

---

## 5. Agregación y exportación

### CA-401 · Bradley-Terry produce un orden coherente — RF-501 · `U`
**Dado** un conjunto sintético donde A le gana a B y B le gana a C de forma consistente
**Cuando** se ajusta el modelo de la dimensión
**Entonces** el score de A es mayor al de B y el de B mayor al de C.

### CA-402 · El trust pondera — RF-206 · `U`
**Dado** dos conjuntos idénticos salvo por el trust de los respondedores
**Cuando** se ajustan ambos modelos
**Entonces** los scores difieren en la dirección de las respuestas mejor ponderadas.

### CA-403 · Grafo desconectado reportado, no forzado — RF-506 · `U`
**Dado** una dimensión donde los campeones forman dos componentes sin comparaciones entre sí
**Cuando** corre la agregación
**Entonces** el pipeline reporta dos componentes y marca esos scores como `insufficient`, **sin**
producir un orden global inventado.

### CA-404 · Toda estimación lleva incertidumbre — RF-506 · `I`
**Dado** cualquier archivo exportado
**Cuando** se recorre cada magnitud medida
**Entonces** todas tienen `_ci_low`, `_ci_high`, `_n` y `_support`, y se cumple
`_ci_low ≤ valor ≤ _ci_high`.

### CA-405 · Vacío no es cero — `26-esquema-de-salida.md` §2.3 · `I`
**Dado** un campeón sin respuestas en la dimensión `engage`
**Cuando** se exporta
**Entonces** la celda `engage` está **vacía**, no en `0`; `engage_n` es `0` y `engage_support` es
`insufficient`.

### CA-406 · Observado y predicho se distinguen — RF-510 · `I`
**Dado** un par de campeones sobre el que nunca se preguntó
**Cuando** aparece en la matriz de matchups
**Entonces** `is_observed` es `false`, `n_responses` es `0` y el intervalo es más ancho que el de
los pares observados.

### CA-407 · La exportación es trazable — RF-509 · `I`
**Dado** una corrida completada
**Cuando** se consulta la tabla de exportaciones
**Entonces** hay una fila por archivo con su SHA-256, sus conteos, la ventana de parches, el umbral
de confianza, la vida media del decaimiento y la versión del paquete de agregación.

### CA-408 · La exportación es reproducible — RF-512, RNF-08 · `I`
**Dado** una exportación previa y sus parámetros registrados
**Cuando** se vuelve a correr con exactamente esos parámetros sobre el mismo crudo
**Entonces** el SHA-256 del archivo resultante es idéntico al registrado.

> Implica que el pipeline no puede tener fuentes de aleatoriedad sin semilla: el bootstrap se
> inicializa con una semilla derivada de los parámetros de la corrida.

### CA-409 · La ventana de parches se respeta — RF-507 · `U`
**Dado** respuestas de los parches 16.18, 16.19 y 16.20
**Cuando** se corre con ventana `16.19..16.20`
**Entonces** las respuestas de 16.18 quedan excluidas, y las de 16.19 pesan menos que las de 16.20
según el decaimiento configurado.

---

## 6. Interfaz

### CA-501 · Nunca se espera entre tarjetas — `30-ux-flujos.md` §1 · `E2E`
**Dado** un respondedor contestando de forma continua
**Cuando** termina una tarjeta
**Entonces** la siguiente aparece sin estado de carga visible, porque la cola se precargó.

### CA-502 · El doble toque no se ve como error — `30-ux-flujos.md` §8 · `C`
**Dado** un respondedor que toca dos veces la misma opción
**Cuando** el segundo envío devuelve `409`
**Entonces** la interfaz avanza a la siguiente tarjeta sin mostrar ningún mensaje de error.

### CA-503 · Soporte bajo se comunica en positivo — RF-114 · `C`
**Dado** una pregunta con menos de 20 respuestas
**Cuando** el respondedor contesta
**Entonces** se muestra `You're one of the first to answer this`, no un panel de consenso vacío.

### CA-504 · La discrepancia no se presenta como error — `30-ux-flujos.md` §5.1 · `C`
**Dado** un respondedor cuya respuesta está en minoría
**Cuando** se muestra el feedback
**Entonces** el texto es `You're in the 19%`, sin ninguna marca de incorrecto.

### CA-505 · Usable a 360 px — RNF-06 · `E2E`
**Dado** una ventana de 360 px de ancho
**Cuando** se recorren todas las pantallas
**Entonces** no hay scroll horizontal y toda opción táctil mide al menos 44 px de lado.

### CA-506 · La definición está a un toque — RF-113 · `C`
**Dado** cualquier pregunta con concepto medido
**Cuando** se toca el ícono de ayuda
**Entonces** se despliega la definición correspondiente, tomada de la base y no del código.

---

## 7. Extensibilidad y operación

### CA-601 · Una dimensión nueva no requiere código — RF-603, RNF-12 · `I`
**Dado** el sistema desplegado
**Cuando** se inserta una fila en `dimensions` con su código, etiqueta y descripción
**Entonces** el sampler empieza a generar preguntas de esa dimensión y la interfaz muestra su
definición, **sin desplegar nada**.

### CA-602 · El pool es un parámetro de datos — RF-604 · `I`
**Dado** un campeón con `pool_tier = 3`
**Cuando** se lo promueve a `pool_tier = 1`
**Entonces** el sampler empieza a incluirlo en preguntas nuevas sin reiniciar la aplicación.

### CA-603 · Los parámetros operativos viven en datos — RF-606, RNF-12 · `I`
**Dado** el sistema desplegado y en marcha
**Cuando** se cambia `sampler.enabled_pool_tiers` de `1` a `2` por el panel
**Entonces** la siguiente pregunta generada puede incluir campeones de tier 2, **sin reiniciar el
proceso ni desplegar código**.

### CA-604 · Toda acción de administración queda auditada — RF-405 · `I`
**Dado** un administrador que activa un parche, promueve un campeón de tier y cambia un parámetro
**Cuando** se consulta `admin_audit`
**Entonces** hay tres filas con su `action`, su `payload` y su timestamp, y el rol de aplicación no
tiene permiso de `UPDATE` ni `DELETE` sobre esa tabla.

---

## 8. Gamificación

### CA-310 · La racha de respuestas corta con la pausa — RF-301 · `U`
**Dado** un respondedor con `current_streak = 12` y `best_streak = 12`
**Cuando** responde de nuevo 31 minutos después de su última respuesta
**Entonces** `current_streak` vuelve a `1` y `best_streak` sigue en `12`.

### CA-311 · La racha de días suma una vez por día — RF-301 · `U`
**Dado** un respondedor que contesta 20 preguntas en un mismo día
**Cuando** se consulta su perfil
**Entonces** `current_day_streak` subió exactamente `1`; y si saltea un día calendario completo,
vuelve a `1`.

### CA-312 · El alias no es un identificador — RF-304 · `I`
**Dado** cualquier respondedor
**Cuando** se compara su alias con su `respondent_id` y su `fingerprint_hash`
**Entonces** no es derivable de ninguno de los dos.

### CA-313 · La tabla de posiciones filtra dos veces — RF-303, RF-304 · `I`
**Dado** un respondedor marcado con el mayor volumen de respuestas, y otro con `trust_score = 0.20`
también entre los primeros por volumen
**Cuando** se consulta la tabla de posiciones en cualquiera de sus tres ventanas
**Entonces** ninguno de los dos aparece, y ninguna respuesta del endpoint permite despejar el trust
score de nadie.

---

## 9. Resumen de cobertura

| Grupo | Criterios | Requerimientos cubiertos |
|---|---|---|
| Sesión e identidad | CA-001 a CA-005 | RF-001 a RF-006, RNF-05 |
| Entrega de preguntas | CA-101 a CA-106 | RF-101, RF-105, RF-106, RF-112, RF-202, RNF-01 |
| Registro de respuestas | CA-201 a CA-209 | RF-108 a RF-110, RF-203, RF-209, RNF-04 |
| Calidad de datos | CA-301 a CA-309 | RF-201, RF-202, RF-204 a RF-208 |
| Agregación y exportación | CA-401 a CA-409 | RF-501, RF-506, RF-507, RF-509, RF-510, RF-512, RNF-08 |
| Interfaz | CA-501 a CA-506 | RF-113, RF-114, RNF-06, RNF-07 |
| Extensibilidad y operación | CA-601 a CA-604 | RF-405, RF-603, RF-604, RF-606, RNF-12 |
| Gamificación | CA-310 a CA-313 | RF-301, RF-303, RF-304 |

Los requerimientos de administración restantes (RF-401 a RF-404) y los de catálogo (RF-601, RF-602,
RF-605) se verifican manualmente durante la operación; sus criterios se agregan al escribir
[`24-panel-admin.md`](24-panel-admin.md).
