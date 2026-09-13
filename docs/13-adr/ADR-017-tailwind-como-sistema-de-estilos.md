# ADR-017 — Tailwind CSS como sistema de estilos del frontend

> Estado: **aceptada** · Fecha: 15/09/2026

## Contexto

La semana 3 escribe las primeras pantallas reales del proyecto. Hasta acá `frontend/src/` era
andamiaje: un landing estático sin una sola clase ni un solo archivo de estilos.

La `DraftSense_Especificacion_Tecnica.md` fija Tailwind CSS como sistema de estilos mobile-first,
pero **nunca estuvo instalado**: `frontend/package.json` no lo tiene entre las dependencias y no hay
`tailwind.config` ni `postcss.config`. La contradicción estaba registrada como pendiente en la skill
`draftsense-frontend` con la instrucción explícita de no resolverla por cuenta propia, porque es una
decisión de stack que pesa sobre RNF-03 —el bundle inicial no puede superar los 200 KB gzip— y
porque empezar a acumular CSS ad-hoc dando por sentada una respuesta habría hecho irreversible la
elección sin haberla tomado.

Hay además un insumo que no existía cuando se escribió la Especificación Técnica: el maquetado
completo de las cinco rutas públicas y los cinco tipos de pregunta está resuelto en un canvas de
Claude Design, con paleta, tipografía, espaciado y geometría ya definidos. Cualquiera sea el sistema
de estilos, los tokens salen de ahí y no se re-derivan.

## Decisión

**Tailwind CSS v4, integrado con el plugin `@tailwindcss/vite`.**

- Los tokens del canvas —paleta, las tres familias tipográficas y los tamaños del bisel— se declaran
  en un bloque `@theme` de `frontend/src/index.css`. Esa es la única fuente de verdad de los valores
  de diseño en el código.
- La esquina biselada, que es la firma visual del sistema y aparece en botones, retratos y chips, se
  expresa como utilidades propias (`@utility bevel-8 / bevel-12 / bevel-14`) en vez de repetir el
  `clip-path` en cada componente.
- Las tres familias se cargan desde Google Fonts con un `<link>` en `index.html`.
- La versión exacta queda pinneada en `package-lock.json` al instalar.

## Alternativas consideradas

- **CSS propio con variables.** Cero dependencias y control total, que con un presupuesto de bundle
  ajustado es un argumento real. Se descartó porque se aparta del documento paraguas sin una
  necesidad técnica que lo justifique, y porque a lo largo de las semanas 4 a 8 entran cuatro tipos
  de pregunta más: sin un sistema de utilidades, cada tarjeta nueva agrega su propia hoja y la
  consistencia pasa a depender de la disciplina.
- **CSS Modules.** Aislamiento por componente sin librería, soportado de fábrica por Vite. Resuelve
  las colisiones de nombres, que no son el problema acá, y deja sin resolver el que sí lo es: tener
  una escala compartida de color, espaciado y tipografía.
- **Una librería de componentes** (MUI, Chakra, shadcn). Se descartó de plano: el diseño ya está
  hecho y no se parece a ningún sistema genérico —bisel en vez de radio, tres tipografías, paleta
  oscura propia—, así que la librería se pagaría entera en bytes para después pelearse con ella.

## Consecuencias

- Una dependencia de build más. El CSS purgado de un sistema de este tamaño ronda los 10 KB gzip,
  pero **hay que medirlo**: el job `frontend` de CI ya falla por encima de 200 KB y esa es la
  comprobación que manda.
- Las utilidades viven en el JSX, así que el `className` de un componente es parte de su contrato
  visual y no se refactoriza a la ligera.
- Los valores de diseño dejan de estar dispersos: un cambio de paleta se hace en `@theme` y alcanza
  a toda la aplicación. El corolario es que **escribir un color literal en un componente es un error**,
  no una abreviatura.
- Cargar las tipografías desde el CDN de Google expone la IP del visitante a un tercero. No lo
  prohíbe ningún requerimiento vigente, pero es un punto que hay que resolver explícitamente al
  escribir [`33-privacidad-y-legal.md`](../33-privacidad-y-legal.md) en la semana 7. Si ahí se decide
  autohospedarlas, el cambio es local a `index.html` y no afecta al presupuesto, que mide sólo
  `dist/assets/*.js`.
