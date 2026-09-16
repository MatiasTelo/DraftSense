/**
 * La huella que viaja en `X-Client-Fingerprint`.
 *
 * `docs/12-api.md` §2.1 la define como «un hash calculado localmente a partir de user-agent y
 * resolución de pantalla»; el servidor la combina con un hash de la IP antes de almacenarla y la
 * usa sólo para detectar identidades duplicadas (`docs/22-calidad-de-datos.md` §6).
 *
 * **No identifica a nadie y no tiene que hacerlo.** Es a propósito una señal grosera: miles de
 * personas comparten el mismo user-agent y la misma resolución. Refinarla hasta que fuera única
 * sería fingerprinting de verdad y violaría RNF-05.
 */

const SOURCE = () =>
  `${navigator.userAgent}|${screen.width}x${screen.height}x${screen.colorDepth}`;

let cached: Promise<string | null> | null = null;

async function compute(): Promise<string | null> {
  // `crypto.subtle` sólo existe en contexto seguro. Si no está, el header se omite: es opcional
  // del lado del servidor, que cae a user-agent más IP. Romper el arranque por esto sería peor.
  if (!globalThis.crypto?.subtle) return null;
  try {
    const bytes = new TextEncoder().encode(SOURCE());
    const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, '0'))
      .join('');
  } catch {
    return null;
  }
}

/** Se calcula una sola vez por carga: el user-agent y la pantalla no cambian a mitad de sesión. */
export function clientFingerprint(): Promise<string | null> {
  cached ??= compute();
  return cached;
}

/** Sólo para los tests, que necesitan partir de cero en cada caso. */
export function resetFingerprint(): void {
  cached = null;
}
