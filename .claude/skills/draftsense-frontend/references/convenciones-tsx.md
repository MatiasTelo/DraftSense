# Convenciones de TypeScript y React

## TypeScript, en modo exigente

`tsconfig.json` no es el default de Vite. Además de `strict: true`:

| Opción | Qué implica al escribir código |
|---|---|
| `noUncheckedIndexedAccess` | `array[0]` es `T` o `undefined`. Hay que chequearlo, no castearlo |
| `noUnusedLocals` / `noUnusedParameters` | Una variable sin usar rompe el build |
| `noFallthroughCasesInSwitch` | Cada `case` cierra |
| `verbatimModuleSyntax` | Los imports de sólo-tipo van con `import type` |
| `isolatedModules` | Nada de `const enum` ni re-exports de tipo sin `export type` |

`target` y `lib` en ES2022, `jsx: "react-jsx"` (no hace falta importar React para usar JSX),
`moduleResolution: "bundler"`.

`npm run build` corre `tsc --noEmit` **antes** de `vite build`: un error de tipos no llega a
producción.

## La unión discriminada

`src/api.ts` define `Question` como unión de los cinco tipos, discriminada por `type`. Al renderizar,
usá un `switch` sobre `question.type` con un caso por variante. Con `noFallthroughCasesInSwitch` y el
chequeo de exhaustividad de TypeScript, agregar un sexto tipo al contrato hace fallar la compilación
en todos los lugares que hay que tocar. Eso es deliberado: **no lo desarmes con un `default` que
silencie el caso faltante**.

`Side` siempre lleva `champions: ChampionRef[]`, tenga uno o dos elementos. Es lo que permite
renderizar duplas y campeones individuales con el mismo componente — no escribas dos.

`RecordedResponse.feedback` es `Feedback | null`: **es `null` mientras la pregunta tiene menos de 20
respuestas**, y ahí va el mensaje de "sos de los primeros en responder". No lo trates como un error.

## Estilos

Tailwind v4 con `@tailwindcss/vite` (ADR-017). No hay `tailwind.config.js`: los tokens están en el
bloque `@theme` de `src/index.css` y las utilidades propias (`bevel-8/12/14`, `portrait-hatch`,
`range-slider`) en bloques `@utility` del mismo archivo.

La regla práctica al escribir un componente: **si estás por poner un valor literal —un hex, un
`clip-path`, un nombre de fuente— el token ya existe o hay que agregarlo a `@theme`**. Lo que sí va
literal son las medidas del maquetado que no se repiten, con la sintaxis de corchetes:
`h-[54px]`, `px-[22px]`, `tracking-[0.18em]`.

## Estado

**Zustand**, para lo mínimo global: sesión, cola de preguntas y racha. El resto es estado local del
componente. Si algo lo usa una sola pantalla, no va al store.

La cookie `ds_session` es `HttpOnly`: **el cliente no puede leerla ni necesita hacerlo**. Las
peticiones van con credenciales y el servidor resuelve la identidad.

## Ruteo

React Router 6. Las cinco rutas están fijadas en `docs/30-ux-flujos.md` §2:
`/` landing, `/start` onboarding, `/play` motor de tarjetas, `/me` perfil, `/leaderboard`.

## Tests

Vitest con `globals: true` y entorno `jsdom`; `src/test-setup.ts` carga los matchers de
`@testing-library/jest-dom`. `vite.config.ts` importa `defineConfig` de `vitest/config`, no de
`vite`: es la variante que acepta el bloque `test`.

El estilo está en `src/screens/Play.test.tsx` y en los tests de `src/components/`: `describe` con
el nombre del componente, `it` describiendo la conducta **en español**, y consultas por rol o por
texto visible (`screen.getByRole`, `screen.getByText`) en vez de por clase o por test-id. Se testea
lo que ve el usuario. Las preguntas de prueba salen de `src/test-fixtures.ts` (`pairwise`,
`peakTiming`, `laneMatchup`), con la forma exacta de `docs/12-api.md`.

## ESLint

Flat config (`eslint.config.js`): `js.configs.recommended` más `tseslint.configs.recommended` más el
recomendado de `react-hooks`, sobre `**/*.{ts,tsx}`, ignorando `dist` y `node_modules`.

## Desarrollo contra el backend

`npm run dev` levanta en el puerto 5173 con proxy de `/api` a `http://localhost:8000`, así que en
desarrollo no hay CORS. En producción sí: el backend responde con el dominio concreto y
`Allow-Credentials: true`, nunca con comodín (`docs/12-api.md` §5).

## El presupuesto de bundle

CI mide `gzip -c dist/assets/*.js` y falla por encima de **200 KB**. `vite.config.ts` pone
`chunkSizeWarningLimit: 250` para avisar antes. Para medirlo local:

```bash
npm run build && gzip -c dist/assets/*.js | wc -c
```
