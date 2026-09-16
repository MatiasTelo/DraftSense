/** La cola y su precarga — CA-501 al nivel que puede verificarse sin navegador. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pairwise } from '../test-fixtures';
import { PREFETCH_AT, useQueue } from './queue';

vi.mock('../lib/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/client')>()),
  fetchQuestions: vi.fn(),
}));

const { fetchQuestions } = await import('../lib/client');
const mocked = vi.mocked(fetchQuestions);

beforeEach(() => {
  useQueue.getState().reset();
  mocked.mockReset();
});

afterEach(() => {
  useQueue.getState().reset();
});

describe('useQueue', () => {
  it('carga el primer lote y queda listo', async () => {
    mocked.mockResolvedValue({ questions: [pairwise(1), pairwise(2)] });

    await useQueue.getState().fetchMore();

    expect(useQueue.getState().questions).toHaveLength(2);
    expect(useQueue.getState().status).toBe('ready');
  });

  it('un lote vacío es cola vacía, no un error', async () => {
    mocked.mockResolvedValue({ questions: [] });

    await useQueue.getState().fetchMore();

    expect(useQueue.getState().status).toBe('empty');
  });

  it('no encola dos veces la misma pregunta si dos precargas se cruzan', async () => {
    mocked.mockResolvedValue({ questions: [pairwise(1), pairwise(2)] });
    await useQueue.getState().fetchMore();

    mocked.mockResolvedValue({ questions: [pairwise(2), pairwise(3)] });
    await useQueue.getState().fetchMore();

    expect(useQueue.getState().questions.map((q) => q.question_id)).toEqual([1, 2, 3]);
  });

  it('precarga al quedar dos, no cuando se vacía', async () => {
    mocked.mockResolvedValue({
      questions: [pairwise(1), pairwise(2), pairwise(3), pairwise(4)],
    });
    await useQueue.getState().fetchMore();
    mocked.mockClear();
    mocked.mockResolvedValue({ questions: [] });

    useQueue.getState().advance(); // quedan 3
    expect(mocked).not.toHaveBeenCalled();

    useQueue.getState().advance(); // quedan 2: es el umbral
    expect(mocked).toHaveBeenCalledTimes(1);
    expect(useQueue.getState().questions).toHaveLength(PREFETCH_AT);
  });

  it('un fallo de precarga con la cola llena no se le muestra al usuario', async () => {
    mocked.mockResolvedValue({ questions: [pairwise(1), pairwise(2), pairwise(3)] });
    await useQueue.getState().fetchMore();

    mocked.mockRejectedValue(new Error('caída'));
    await useQueue.getState().fetchMore();

    // Sigue respondiendo con lo que tiene; el próximo intento resuelve.
    expect(useQueue.getState().status).toBe('ready');
    expect(useQueue.getState().questions).toHaveLength(3);
  });

  it('un fallo con la cola vacía sí es un estado de error', async () => {
    mocked.mockRejectedValue(new Error('caída'));

    await useQueue.getState().fetchMore();

    expect(useQueue.getState().status).toBe('error');
  });
});
