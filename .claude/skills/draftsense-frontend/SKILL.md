---
name: draftsense-frontend
description: >-
  Frontend de DraftSense: SPA en React 18 + TypeScript 5.7 + Vite 6, con Zustand para estado,
  React Router 6, Vitest 3 y Testing Library, ESLint 9 flat config. Usar SIEMPRE al escribir,
  revisar o refactorizar cualquier cosa bajo `frontend/`: componentes, pantallas, rutas, store,
  tipos del contrato con la API, tests de componente o configuración de Vite/ESLint/TypeScript.
  Activar también ante las pantallas del sistema (`/`, `/start`, `/play`, `/me`, `/leaderboard`),
  el motor de tarjetas de pregunta, la unión discriminada por `type`, el feedback post-respuesta,
  mobile-first, accesibilidad, o el presupuesto de bundle de 200 KB gzip. Complementa a `draftsense`
  (alcance y ruteo a la documentación): los wireframes y el microcopy se leen de
  `docs/30-ux-flujos.md` y el contrato de `docs/12-api.md`; esta skill dice CÓMO escribir el código
  que los implementa.
---

# Frontend de DraftSense

SPA de una sola página, **mobile-first**: la mayoría del tráfico esperado viene de teléfonos, porque
la difusión es por Reddit y Discord.

## Estado actual

**Las cinco pantallas existen** desde la semana 3: `/` landing, `/start` onboarding, `/play` motor
de tarjetas, `/me` perfil y `/leaderboard`. React Router monta las rutas en `App.tsx`; el maquetado
sale del canvas de Claude Design, que las diseñó a partir de `docs/30-ux-flujos.md`.

| Carpeta | Qué hay |
|---|---|
| `src/lib/` | `client.ts` (una función por endpoint, `ApiError` y `NetworkError`) y `fingerprint.ts` |
| `src/store/` | `session.ts` (identidad y contadores) y `queue.ts` (cola de preguntas y precarga) |
| `src/components/` | `AppFrame`, `Button`, `Chrome` (las dos barras), `QuestionCard`, `PairwiseDimensionCard`, `QuestionPrompt`, `ChampionPortrait`, `FeedbackOverlay`, `States` |
| `src/screens/` | Una por ruta |

**Del motor de tarjetas sólo está el tipo 1.** `QuestionCard` tiene una rama por tipo y las otras
cuatro devuelven `null`: llegan en las semanas 4 y 8, y hoy el servidor no puede mandarlas.

`api.ts` cubre el contrato entero y **es espejo de `docs/12-api.md`**. La API está en pie
(`uvicorn app.main:app --reload` en `:8000`, con el proxy de Vite apuntando ahí), así que las
pantallas se escriben y se prueban contra un servidor real.

Dos cosas a tener en cuenta al escribirlas:

- **No hace falta llamar a `POST /sessions` antes de nada.** Los endpoints que necesitan identidad
  crean la sesión al vuelo y devuelven la cookie (`docs/12-api.md` §1.3). Llamarlo igual al
  arrancar es correcto y es lo que da el `onboarding_seen`.
- **Todo error trae el sobre `{ error: { code, message, field? } }`.** Ramificá por `code`, no por
  el status: el `409 duplicate_response` del doble toque, por ejemplo, no se muestra como error
  sino que avanza a la tarjeta siguiente (CA-502).

## Comandos

```bash
cd frontend
npm install
npm run dev         # http://localhost:5173, con proxy de /api a http://localhost:8000
npm run lint        # eslint .
npm run typecheck   # tsc --noEmit
npm test            # vitest run
npm run build       # tsc --noEmit && vite build
```

Las cuatro últimas son las que corre CI, en ese orden, más el presupuesto de bundle.

## Estilos: Tailwind v4

Decidido en [ADR-017](../../../docs/13-adr/ADR-017-tailwind-como-sistema-de-estilos.md). Se integra
con `@tailwindcss/vite`, no con PostCSS, y **no hay `tailwind.config.js`**: todo vive en
`src/index.css`.

- **Los tokens están en el bloque `@theme`** y son la única representación de los valores de diseño
  en el código. Escribir `#E4B457` dentro de un componente es un error, no una abreviatura: usá
  `bg-gold`. Lo mismo con las tres familias (`font-display`, `font-sans`, `font-mono`).
- **La esquina biselada es la firma visual** y va como utilidad propia: `bevel-8`, `bevel-12`,
  `bevel-14`. **No hay `border-radius` en ninguna parte** salvo el círculo del ícono de ayuda y el
  *thumb* del slider del tipo 2.
- Los bordes son siempre blanco con alfa (`border-edge`, `border-white/7`…), nunca un gris opaco:
  tienen que funcionar sobre cualquiera de las seis superficies.
- El área táctil mínima es de 44 px (`min-h-11`) en toda opción seleccionable, y las opciones de
  lista miden 52 (`min-h-[52px]`).

## Las reglas que no se negocian

1. **Interfaz en inglés.** Todo texto visible al usuario va en inglés desde el día 1; el español
   entra por i18n hacia la semana 8 ([ADR-010](../../../docs/13-adr/ADR-010-interfaz-en-ingles.md)).
   Los comentarios y los nombres de los tests van en español, como el resto del proyecto.
2. **El cliente no compone enunciados.** El servidor manda el texto ya renderizado, con los nombres
   de campeón sustituidos. Si te encontrás concatenando strings para armar una pregunta, el problema
   está en el backend, no acá (`docs/12-api.md` §1.1).
3. **Presupuesto de 200 KB gzip para el bundle inicial** (RNF-03). **CI hace fallar el build si se
   pasa**, midiendo `gzip -c dist/assets/*.js`. Antes de agregar una dependencia, pensá cuánto pesa.
   Los íconos de campeones se cargan bajo demanda desde el CDN de Riot, no se empaquetan.
4. **`src/api.ts` es espejo de `docs/12-api.md`.** Si cambia el contrato, cambia el archivo, y al
   revés no: el documento manda.
5. **No existe "deshacer una respuesta".** `responses` es append-only y una corrección tardía es peor
   dato que la primera reacción (`docs/30-ux-flujos.md` §10). No agregues esa afordancia.

## Decisiones de interfaz ya cerradas

De `docs/30-ux-flujos.md` §10. No se replantean:

| Decisión | Elegido |
|---|---|
| Registro | No hay |
| Onboarding | Al inicio, salteable |
| Confirmación de respuesta | Sólo tipos 2 y 5; los demás registran al primer toque |
| Duración del feedback | 1,2 s |
| Orden del leaderboard | Cantidad de respuestas, no acuerdo |
| Trust score visible | No, nunca |
| Deshacer una respuesta | No existe |

El feedback de consenso **se omite mientras la pregunta tiene menos de 20 respuestas**; en su lugar
va el mensaje de "sos de los primeros en responder"
([ADR-012](../../../docs/13-adr/ADR-012-sampler-uniforme-en-arranque-en-frio.md), texto exacto en
`docs/30-ux-flujos.md`).

## Cuándo leer la referencia

- **`references/convenciones-tsx.md`** — al escribir cualquier `.ts`/`.tsx`: configuración de
  TypeScript, estado, ruteo, tests y las trampas de la unión discriminada.

Los wireframes, los estados de cada pantalla y el microcopy están en `docs/30-ux-flujos.md` §3 a §8;
el enunciado y la UI de cada tipo de pregunta, en `docs/20-tipos-de-pregunta.md` §2 a §6.

## Mantener esta skill al día

Si cambian `docs/30-ux-flujos.md`, `docs/20-tipos-de-pregunta.md`, `docs/12-api.md` o
`frontend/package.json`, revisar que lo de acá siga siendo cierto — sobre todo el inventario de
`src/`, que crece con cada tipo de pregunta nuevo.
