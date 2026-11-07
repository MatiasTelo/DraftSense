/** La cola y su precarga — CA-501 al nivel que puede verificarse sin navegador. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pairwise } from '../test-fixtures';
import { BATCH_SIZE, PREFETCH_AT, useQueue } from './queue';

vi.mock('../lib/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/client')>()),
  fetchQuestions: vi.fn(),
  fetchQueuedQuestions: vi.fn(),
}));

const { fetchQuestions, fetchQueuedQuestions } = await import('../lib/client');
const mocked = vi.mocked(fetchQuestions);
const queued = vi.mocked(fetchQueuedQuestions);

beforeEach(() => {
  useQueue.getState().reset();
  mocked.mockReset();
  queued.mockReset();
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

  it('con la cola vacía pide el lote diciendo que no tiene nada pendiente', async () => {
    mocked.mockResolvedValue({ questions: [pairwise(1)] });

    await useQueue.getState().fetchMore();

    expect(mocked).toHaveBeenCalledWith(BATCH_SIZE, [], 'en');
  });

  it('al precargar manda las preguntas que le quedan sin contestar', async () => {
    // Sin este dato el servidor ubica las preguntas nuevas dos posiciones antes de donde caen —y
    // las cadencias de honeypots y retests se corren— y puede volver a mandar lo que ya está en la
    // cola (ADR-020, `docs/12-api.md` §2.3).
    mocked.mockResolvedValue({
      questions: [pairwise(1), pairwise(2), pairwise(3), pairwise(4)],
    });
    await useQueue.getState().fetchMore();
    mocked.mockClear();
    mocked.mockResolvedValue({ questions: [] });

    useQueue.getState().advance();
    useQueue.getState().advance();

    expect(mocked).toHaveBeenCalledExactlyOnceWith(BATCH_SIZE, [3, 4], 'en');
    expect(useQueue.getState().questions).toHaveLength(PREFETCH_AT);
  });
});

/** Una pregunta como la mandaría el servidor en español. */
function spanish(question_id: number) {
  return { ...pairwise(question_id), prompt: '¿Quién tiene más engage?' };
}

describe('retranslate (ADR-029)', () => {
  it('reemplaza cada pregunta por su versión traducida, en el mismo orden', async () => {
    useQueue.setState({ questions: [pairwise(1), pairwise(2), pairwise(3)], status: 'ready' });
    queued.mockResolvedValue({ questions: [spanish(1), spanish(2), spanish(3)] });
    mocked.mockResolvedValue({ questions: [] });

    await useQueue.getState().retranslate('es');

    expect(queued).toHaveBeenCalledExactlyOnceWith([1, 2, 3], 'es');
    const { questions, status } = useQueue.getState();
    expect(questions.map((q) => q.question_id)).toEqual([1, 2, 3]);
    expect(questions.map((q) => q.prompt)).toEqual(Array(3).fill('¿Quién tiene más engage?'));
    expect(status).toBe('ready');
  });

  it('saca de la cola las que el servidor ya no puede armar', async () => {
    useQueue.setState({ questions: [pairwise(1), pairwise(2), pairwise(3)], status: 'ready' });
    queued.mockResolvedValue({ questions: [spanish(1), spanish(3)] });
    mocked.mockResolvedValue({ questions: [] });

    await useQueue.getState().retranslate('es');

    expect(useQueue.getState().questions.map((q) => q.question_id)).toEqual([1, 3]);
  });

  it('si el pedido falla, la cola queda como estaba', async () => {
    const before = [pairwise(1), pairwise(2), pairwise(3)];
    useQueue.setState({ questions: before, status: 'ready' });
    queued.mockRejectedValue(new Error('caída'));

    await useQueue.getState().retranslate('es');

    expect(useQueue.getState().questions).toEqual(before);
    expect(useQueue.getState().status).toBe('ready');
  });

  it('descarta el lote que venía en el idioma anterior y lo vuelve a pedir', async () => {
    // Un lote en inglés en vuelo que llega después del cambio no puede entrar a la cola.
    let late: (value: { questions: ReturnType<typeof pairwise>[] }) => void = () => {};
    mocked.mockReturnValueOnce(new Promise((resolve) => (late = resolve)));
    useQueue.setState({ questions: [pairwise(1)], status: 'ready' });
    const english = useQueue.getState().fetchMore();
    queued.mockResolvedValue({ questions: [spanish(1)] });
    mocked.mockResolvedValue({ questions: [spanish(7)] });

    await useQueue.getState().retranslate('es');
    late({ questions: [pairwise(9)] });
    await english;
    await Promise.resolve();

    expect(useQueue.getState().questions.map((q) => q.question_id)).toEqual([1, 7]);
  });

  it('con la cola vacía no pide nada y deja que se cargue en el idioma nuevo', async () => {
    await useQueue.getState().retranslate('es');

    expect(queued).not.toHaveBeenCalled();
    expect(useQueue.getState().status).toBe('idle');
  });
});
