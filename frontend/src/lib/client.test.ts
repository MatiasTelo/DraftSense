import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, NetworkError, fetchQuestions, postResponse } from './client';

function respondWith(status: number, body: unknown, headers: Record<string, string> = {}) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json', ...headers },
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('client', () => {
  it('manda las credenciales para que viaje la cookie de sesión', async () => {
    const fetchMock = respondWith(200, { questions: [] });

    await fetchQuestions(5);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/questions/next?count=5',
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('convierte el sobre de error en un ApiError con su código', async () => {
    respondWith(400, {
      error: { code: 'answer_shape_mismatch', message: 'nope', field: 'answer' },
    });

    const failure = await postResponse({
      question_id: 1,
      answer: { choice: 'a' },
      response_time_ms: 100,
    }).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    const error = failure as ApiError;
    expect(error.code).toBe('answer_shape_mismatch');
    expect(error.field).toBe('answer');
    expect(error.status).toBe(400);
  });

  it('distingue el duplicado del resto sin mirar el status', async () => {
    respondWith(409, { error: { code: 'duplicate_response', message: 'already answered' } });

    const error = (await postResponse({
      question_id: 1,
      answer: { choice: 'a' },
      response_time_ms: 100,
    }).catch((caught: unknown) => caught)) as ApiError;

    // Es lo que `/play` necesita para avanzar en silencio en vez de mostrar un error (CA-502).
    expect(error.code).toBe('duplicate_response');
  });

  it('lee Retry-After en el límite de tasa', async () => {
    respondWith(
      429,
      { error: { code: 'rate_limit_exceeded', message: 'slow down' } },
      { 'Retry-After': '12' },
    );

    const error = (await postResponse({
      question_id: 1,
      answer: { choice: 'a' },
      response_time_ms: 100,
    }).catch((caught: unknown) => caught)) as ApiError;

    expect(error.retryAfter).toBe(12);
  });

  it('un error sin el sobre no revienta el cliente', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>502</html>', { status: 502 })));

    const error = (await fetchQuestions().catch((caught: unknown) => caught)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
  });

  it('un fallo de red es NetworkError, no ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    const error = await fetchQuestions().catch((caught: unknown) => caught);

    // La distinción manda dos mensajes distintos en §8: «no se guardó tu respuesta» contra
    // «el problema es nuestro».
    expect(error).toBeInstanceOf(NetworkError);
    expect(error).not.toBeInstanceOf(ApiError);
  });
});
