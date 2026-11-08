# ADR-028 — El idioma lo elige la persona con un selector, y viaja como parámetro `lang`

> Estado: **aceptada** · Fecha: 29/10/2026 · El punto 5 fue sustituido por
> [ADR-029](ADR-029-cambiar-de-idioma-traduce-la-cola.md) el 07/11/2026

## Contexto

[ADR-010](ADR-010-interfaz-en-ingles.md) construyó la interfaz en inglés y dejó el español para la
semana 8, con el esquema preparado: `dimensions` y `traits` tienen `label_es` y `description_es`
nulables. [`12-api.md`](../12-api.md) §1.1 fija que **el servidor arma los textos y el cliente los
muestra**, para que la internacionalización viva en un solo lugar, y
[ADR-018](ADR-018-textos-fijos-de-los-tipos-2-y-3.md) dice que el español de los tipos 2 a 4 entra
en `question_texts.py`, junto a las constantes en inglés.

Ningún documento decía **cómo pide el cliente un idioma**, ni qué pasa con el microcopy de las
pantallas, que no viene del servidor.

## Decisión

1. **La persona elige con un selector `EN | ES`**, visible en la landing (`/`) y en la barra
   superior de `/play` ([`30-ux-flujos.md`](../30-ux-flujos.md) §10, nota del 29/10). El idioma por
   defecto es el inglés. La elección se recuerda en `localStorage` del navegador; si el
   almacenamiento no está disponible, la sesión arranca en inglés.
2. **`GET /questions/next` acepta `lang=en|es`**, por defecto `en`. Un valor distinto responde
   `400 invalid_parameter` con `field: "lang"`. Es el único endpoint que devuelve textos para
   mostrar: el feedback de `POST /responses` y los datos de `/me` y `/leaderboard` son números y
   claves, y los textos que los rodean son del cliente.
3. **El servidor arma enunciado, opciones y ayudas en el idioma pedido.** Las dimensiones y los
   atributos usan `label_es`, `description_es` y `prompt_es`. Si falta un texto en español, sale el
   inglés: una celda nula nunca deja una pregunta sin enunciado.
4. **El microcopy de las pantallas vive en el cliente**, en un diccionario por idioma
   (`frontend/src/i18n/`), sin biblioteca de internacionalización, para no gastar el presupuesto de
   200 KB (RNF-03).
5. **Al cambiar de idioma se descarta la cola de preguntas ya cargadas** y se pide un lote nuevo:
   las que estaban en cola vienen armadas en el idioma anterior.
6. **El idioma no se guarda en la base ni toca la respuesta.** `responses.answer` guarda claves
   (`a_strong`, `pair_1`, `engage`), nunca textos, así que una misma pregunta contestada en inglés
   y en español es el mismo dato.
7. **Los términos del juego no se traducen** (ADR-010): *engage*, *poke*, *pick*, *peel*, *dive*,
   *split push*, *waveclear* y los nombres de campeón quedan en inglés dentro del texto en español.

## Alternativas consideradas

- **El header `Accept-Language` del navegador.** No pide interfaz, pero quien tiene el navegador
  en inglés y prefiere español no tiene cómo cambiarlo.
- **Guardar la preferencia en `respondents`.** Daría persistencia entre dispositivos, pero no hay
  login ([ADR-001](ADR-001-sin-autenticacion.md)) y la sesión ya es por navegador.
- **Una biblioteca de internacionalización** (`i18next`, `react-intl`). Resuelve plurales y
  formatos que la interfaz no usa, a costa de varias decenas de KB del presupuesto.

## Consecuencias

- `question_texts.py` duplica cada constante en dos idiomas, y un test verifica que las dos tengan
  las mismas claves y los mismos marcadores de sustitución.
- La segmentación por idioma no existe en los datos: el Informe de Calidad de Datos no puede
  separar respuestas por idioma, porque el idioma no se registra.
- Agregar un tercer idioma (RF-W05) es sumar una constante por texto, una columna `_xx` por
  catálogo y un diccionario en el cliente.
