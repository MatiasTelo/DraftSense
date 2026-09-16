/**
 * El cliente HTTP contra la API.
 *
 * Dos reglas gobiernan este archivo:
 *
 * 1. **Se ramifica por `code`, no por status.** Toda respuesta de error trae el sobre
 *    `{ error: { code, message, field? } }` (`docs/12-api.md` §3), y el código dice qué hacer:
 *    `duplicate_response` avanza en silencio, `rate_limit_exceeded` pausa, `database_unavailable`
 *    ofrece reintentar. El status HTTP es un detalle de transporte.
 * 2. **Todo va con `credentials: 'include'`.** La cookie `ds_session` es `HttpOnly`: el cliente no
 *    puede leerla y no necesita hacerlo. Sin esto la sesión se pierde en cada petición y el
 *    servidor crea un respondedor nuevo cada vez.
 *
 * No hace falta llamar a `createSession()` antes que nada: los endpoints que necesitan identidad
 * la crean al vuelo y devuelven la cookie (`docs/12-api.md` §1.3). Se llama igual al arrancar
 * porque es lo que da `onboarding_seen`.
 */

import { API_BASE } from '../api';
import type {
  LeaderboardResponse,
  LeaderboardWindow,
  MeResponse,
  OnboardingRequest,
  QuestionBatch,
  RecordedResponse,
  ResponseRequest,
  SessionResponse,
} from '../api';
import { clientFingerprint } from './fingerprint';

/** Un error que el servidor explicó. Siempre trae un `code` de la tabla de `12-api.md` §3. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly field: string | undefined;
  /** Segundos de `Retry-After`, sólo en el `429`. */
  readonly retryAfter: number | undefined;

  constructor(
    code: string,
    message: string,
    status: number,
    field?: string,
    retryAfter?: number,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.field = field;
    this.retryAfter = retryAfter;
  }
}

/**
 * La petición nunca llegó al servidor.
 *
 * Es una clase aparte y no un `ApiError` con un código inventado: los códigos de error son los
 * tabulados en el contrato y no se agregan desde el cliente. Además la interfaz los trata distinto
 * — «You're offline. Your last answer wasn't saved.» contra «Something broke on our end»
 * (`docs/30-ux-flujos.md` §8).
 */
export class NetworkError extends Error {
  constructor(message = 'the request never reached the server') {
    super(message);
    this.name = 'NetworkError';
  }
}

function parseRetryAfter(response: Response): number | undefined {
  const header = response.headers.get('Retry-After');
  if (header === null) return undefined;
  const seconds = Number.parseInt(header, 10);
  return Number.isFinite(seconds) ? seconds : undefined;
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = 'unexpected_error';
  let message = response.statusText || 'request failed';
  let field: string | undefined;

  // Un error sin el sobre es un bug del servidor o un intermediario (un 502 del proxy, por
  // ejemplo). Se trata igual que cualquier otro en vez de reventar acá.
  try {
    const body: unknown = await response.json();
    if (body !== null && typeof body === 'object' && 'error' in body) {
      const envelope = (body as { error: { code?: string; message?: string; field?: string } })
        .error;
      code = envelope.code ?? code;
      message = envelope.message ?? message;
      field = envelope.field;
    }
  } catch {
    /* cuerpo vacío o no-JSON: quedan los valores por defecto */
  }

  return new ApiError(code, message, response.status, field, parseRetryAfter(response));
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { credentials: 'include', ...init });
  } catch {
    throw new NetworkError();
  }

  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

async function postJson<T>(path: string, body: unknown, extra?: HeadersInit): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...extra },
    body: JSON.stringify(body),
  });
}

export async function createSession(): Promise<SessionResponse> {
  const fingerprint = await clientFingerprint();
  return request<SessionResponse>('/sessions', {
    method: 'POST',
    headers: fingerprint === null ? {} : { 'X-Client-Fingerprint': fingerprint },
  });
}

export async function saveOnboarding(body: OnboardingRequest): Promise<{ onboarding_seen: boolean }> {
  return postJson<{ onboarding_seen: boolean }>('/sessions/onboarding', body);
}

export async function fetchQuestions(count = 5): Promise<QuestionBatch> {
  return request<QuestionBatch>(`/questions/next?count=${count}`);
}

export async function postResponse(body: ResponseRequest): Promise<RecordedResponse> {
  return postJson<RecordedResponse>('/responses', body);
}

export async function fetchMe(): Promise<MeResponse> {
  return request<MeResponse>('/me');
}

export async function fetchLeaderboard(window: LeaderboardWindow): Promise<LeaderboardResponse> {
  return request<LeaderboardResponse>(`/leaderboard?window=${window}`);
}
