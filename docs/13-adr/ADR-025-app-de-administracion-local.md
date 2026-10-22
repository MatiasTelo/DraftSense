# ADR-025 — La administración es una aplicación local del servidor del laboratorio, sin clave

> Estado: **aceptada** · Fecha: 21/10/2026

## Contexto

Hasta la semana 6 la administración estaba especificada como **parte de la API pública**: seis
endpoints `/admin/*` en [`12-api.md`](../12-api.md) §2.7, protegidos con el header `X-Admin-Key`
(§1.3 y RF-404), y una ruta `/admin` en la SPA pública que no se enlazaba desde ninguna parte
([`30-ux-flujos.md`](../30-ux-flujos.md)). El pipeline de agregación, en cambio, era un CLI que no
se desplegaba ([`10-arquitectura.md`](../10-arquitectura.md) §1).

Ninguno de los seis endpoints llegó a implementarse. Antes de hacerlo, en la semana 7, el tutor de
la organización pidió otra forma: **una aplicación que corra en local en el servidor del
laboratorio**, que reúna el panel de administración y el botón para generar los CSV, **sin claves**.
El criterio es físico: quien puede usar esa aplicación es porque está en la computadora del
servidor, y por lo tanto es administrador.

Ese pedido toca tres cosas que ya estaban escritas: dónde vive la administración, cómo se
autentica, y el idioma de su interfaz.

## Decisión

**La administración es una aplicación aparte, en la carpeta `admin/` del repositorio**, con dos
piezas:

- `admin/backend/`: una aplicación FastAPI propia que **se conecta directo a Postgres** y reutiliza
  los services, models y seeds de `backend/app/`. No pasa por la API pública.
- `admin/frontend/`: una SPA Vite + React + TypeScript con los mismos tokens de Tailwind que la
  pública ([ADR-017](ADR-017-tailwind-como-sistema-de-estilos.md)). En el servidor la sirve el
  propio backend del admin como estáticos: un solo proceso.

Las reglas:

1. **Sin clave ni login.** La aplicación **escucha sólo en `127.0.0.1`**. Es esa restricción, y no
   una credencial, lo que hace verdadero que «quien llega es administrador». El script de arranque
   fija el host; no hay una opción para escuchar en otra interfaz.
2. **La API pública no tiene endpoints de administración.** Los seis `/admin/*` de `12-api.md` §2.7
   salen del contrato público y su contenido pasa al contrato interno de la app admin, en
   [`24-panel-admin.md`](../24-panel-admin.md). `X-Admin-Key`, `Settings.admin_key` y el error
   `admin_key_required` dejan de existir. La SPA pública no tiene ruta `/admin`.
3. **Mismos services que el CLI.** Cada acción del panel llama al mismo service que su comando de
   CLI —`services/patches.py` para activar un parche, como fija
   [ADR-024](ADR-024-activacion-explicita-de-parche.md), y los seeds y jobs de la semana 5—. El
   panel no reimplementa reglas.
4. **Toda acción se audita**, incluidas las que hoy sólo existen en el CLI: correr un job y cargar
   un seed. La migración `0005` amplía el `CHECK` de `admin_audit.action`.
5. **Credenciales propias.** La app admin lee su DSN de `admin/.env`, que no se versiona, igual que
   `backend/.env`.
6. **La interfaz del panel va en español.** Es una herramienta interna del laboratorio, no
   interfaz pública: [ADR-010](ADR-010-interfaz-en-ingles.md) sigue rigiendo para la SPA pública.
   El código y los identificadores siguen en inglés.
7. **El botón de exportación está desde la semana 7, deshabilitado** hasta que exista el paquete
   `aggregation/` (semana 9). Lo que hace al habilitarse sigue siendo CU-08.

## Alternativas consideradas

- **`/admin/*` en la API pública con `X-Admin-Key`**, como estaba especificado. Deja la superficie
  de administración expuesta a internet detrás de una clave compartida que hay que repartir, rotar
  y no filtrar, y obliga a que la corrida de agregación —minutos de CPU— se dispare contra el mismo
  proceso que atiende el camino crítico. El tutor de la organización la descartó.
- **Vía mixta**: las acciones de operación por la API pública y sólo la agregación en local. Mantiene
  la clave y suma una segunda vía para lo mismo; las dos desventajas juntas.
- **Una interfaz local que llame a la API pública.** Sigue necesitando los `/admin/*` públicos y su
  clave; sólo mueve dónde se dibuja el panel.
- **Escuchar en la red del laboratorio** (`0.0.0.0`). Cualquiera en esa red sería administrador sin
  estar en el servidor, que no es lo que se pidió.

## Consecuencias

- **RF-404 cambia de forma.** Ya no es «los endpoints de administración requieren una clave», sino
  «la administración sólo es accesible desde la máquina del servidor». Se anota en
  [`01-requerimientos.md`](../01-requerimientos.md).
- **La app admin necesita acceso de red a la base de producción** desde el servidor del
  laboratorio. Como el despliegue a producción quedó pendiente por decisión del 21/10/2026 —no está
  confirmado dónde va a correr—, esto se resuelve al desplegar.
- **`admin_audit` sigue sin guardar quién.** Antes era porque la clave era compartida; ahora porque
  no hay identidad. El motivo cambia, el diseño no.
- **Hay dos procesos de Python que importan `backend/app/`.** Un cambio de firma en un service
  rompe los dos, y por eso los dos corren en CI.
- **Los tokens de ADR-017 se mudan a `frontend/src/tokens.css`**, que importan las dos SPA. Sigue
  habiendo una sola representación de los valores de diseño; lo que cambia es el archivo, porque
  `index.css` importa Tailwind y el panel no puede resolverlo desde `frontend/node_modules`. Los
  colores de los gráficos del panel se sumaron a ese mismo bloque `@theme`.
- **El pipeline de agregación pasa a dispararse desde el panel** (cuando se habilite en la semana 9),
  en el mismo servidor. `10-arquitectura.md` decía que se corría desde la máquina del desarrollador
  o una GitHub Action manual: eso queda como alternativa, no como camino principal.
