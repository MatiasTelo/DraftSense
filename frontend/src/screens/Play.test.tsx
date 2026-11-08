/** El motor de tarjetas — CA-502 de `03-criterios-aceptacion.md` §6, y los tipos 2 y 3. */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { laneMatchup, pairwise, peakTiming, traitMultiselect } from '../test-fixtures';
import { useQueue } from '../store/queue';
import { useSession } from '../store/session';
import { FEEDBACK_MS, Play } from './Play';

vi.mock('../lib/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/client')>()),
  fetchQuestions: vi.fn(),
  postResponse: vi.fn(),
  createSession: vi.fn(),
}));

const { ApiError, NetworkError, createSession, fetchQuestions, postResponse } = await import(
  '../lib/client'
);

const PROGRESS = {
  answers_count: 18,
  current_streak: 7,
  best_streak: 31,
  current_day_streak: 4,
  best_day_streak: 9,
  agreement_rate: 0.81,
};

function renderPlay() {
  return render(
    <MemoryRouter>
      <Play />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  useQueue.getState().reset();
  vi.mocked(fetchQuestions).mockResolvedValue({ questions: [] });
  vi.mocked(createSession).mockResolvedValue({
    respondent_id: 'r1',
    onboarding_seen: true,
    answers_count: 17,
    current_streak: 6,
    best_streak: 31,
    current_day_streak: 4,
    best_day_streak: 9,
  });
  useSession.setState({ ready: true });
  useQueue.setState({ questions: [pairwise(1), pairwise(2, 'Sett', 'Kayle')], status: 'ready' });
});

afterEach(async () => {
  // Avanzar de tarjeta dispara la precarga, que resuelve después de que el test terminó y
  // actualiza el componente fuera de `act`. Se deja vaciar la microcola antes de desmontar.
  await act(async () => {
    await Promise.resolve();
  });
  vi.clearAllMocks();
});

describe('Play', () => {
  it('muestra el ranking de adelante con sus cinco campeones y la salida', () => {
    renderPlay();

    expect(screen.getByRole('heading')).toHaveTextContent('Who has more engage?');
    for (const name of ['Alistar', 'Yasuo', 'Leona', 'Jax', 'Lux']) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(screen.getByText('Not sure')).toBeInTheDocument();
  });

  it('el ranking se confirma y viaja con su ranking_id (ADR-022)', async () => {
    vi.mocked(postResponse).mockResolvedValue({
      recorded: true,
      feedback: null,
      progress: PROGRESS,
    });
    renderPlay();

    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(postResponse).toHaveBeenCalledWith(
        expect.objectContaining({
          question_id: 1,
          ranking_id: 5001,
          answer: { order: [12, 157, 89, 24, 99] },
        }),
      );
    });
  });

  it('mide el tiempo de respuesta y lo manda en milisegundos (RF-109)', async () => {
    vi.mocked(postResponse).mockResolvedValue({
      recorded: true,
      feedback: null,
      progress: PROGRESS,
    });
    renderPlay();

    fireEvent.click(screen.getByText('Not sure'));

    await waitFor(() => {
      const sent = vi.mocked(postResponse).mock.calls[0]?.[0];
      expect(sent?.response_time_ms).toBeGreaterThanOrEqual(0);
      expect(sent?.answer).toEqual({ choice: 'unknown' });
    });
  });

  it('CA-502 — el doble toque devuelve 409 y la interfaz avanza sin mostrar error', async () => {
    vi.mocked(postResponse).mockRejectedValue(
      new ApiError('duplicate_response', 'already answered', 409),
    );
    renderPlay();

    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

    // Avanza a la tarjeta siguiente...
    await waitFor(() => {
      expect(screen.getByText('Sett')).toBeInTheDocument();
    });
    // ...y no aparece ningún estado de error por haber tocado dos veces.
    expect(screen.queryByText(/wasn't saved/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/broke on our end/i)).not.toBeInTheDocument();
  });

  it('un fallo de red dice que la respuesta no se guardó, y no la reencola', async () => {
    vi.mocked(postResponse).mockRejectedValue(new NetworkError());
    renderPlay();

    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(screen.getByText("You're offline. Your last answer wasn't saved.")).toBeInTheDocument();
    });
    // La pregunta sigue ahí: se puede volver a tocar, pero nadie reintenta por su cuenta (ADR-002).
    expect(screen.getByText('Alistar')).toBeInTheDocument();
  });

  it('el 503 se comunica como problema del servidor, no como falta de conexión', async () => {
    vi.mocked(postResponse).mockRejectedValue(
      new ApiError('database_unavailable', 'down', 503),
    );
    renderPlay();

    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(
        screen.getByText('Something broke on our end. Try again in a minute.'),
      ).toBeInTheDocument();
    });
  });

  it('el 429 pausa con la cuenta regresiva que manda el servidor', async () => {
    vi.mocked(postResponse).mockRejectedValue(
      new ApiError('rate_limit_exceeded', 'slow down', 429, undefined, 12),
    );
    renderPlay();

    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

    await waitFor(() => {
      expect(screen.getByText('Slow down a little — try again in 12 seconds.')).toBeInTheDocument();
    });
  });

  it('con la cola vacía invita a volver después del próximo parche', () => {
    useQueue.setState({ questions: [], status: 'empty' });
    renderPlay();

    expect(
      screen.getByText('Nothing left to ask right now. Come back after the next patch.'),
    ).toBeInTheDocument();
    expect(screen.getByText('See your profile →')).toBeInTheDocument();
  });

  it('la barra superior lleva la racha y el contador, y nada más', () => {
    useSession.setState({
      counters: {
        answers_count: 18,
        current_streak: 7,
        best_streak: 31,
        current_day_streak: 4,
        best_day_streak: 9,
      },
    });
    renderPlay();

    const header = screen.getByRole('banner');
    expect(header).toHaveTextContent('🔥 7');
    expect(header).toHaveTextContent('18 answered');
  });

  describe('tipo 2', () => {
    beforeEach(() => {
      useQueue.setState({ questions: [peakTiming(1), peakTiming(2, 'Sett')], status: 'ready' });
      vi.mocked(postResponse).mockResolvedValue({
        recorded: true,
        feedback: null,
        progress: PROGRESS,
      });
    });

    it('no registra hasta confirmar, y manda el minuto elegido', async () => {
      renderPlay();

      fireEvent.change(screen.getByRole('slider'), { target: { value: '31' } });
      expect(postResponse).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

      await waitFor(() => {
        expect(postResponse).toHaveBeenCalledWith(
          expect.objectContaining({ question_id: 1, answer: { minute: 31 } }),
        );
      });
    });

    it('Enter confirma desde el teclado, una sola vez aunque se repita', async () => {
      renderPlay();

      fireEvent.keyDown(window, { key: 'Enter' });
      fireEvent.keyDown(window, { key: 'Enter' });

      await waitFor(() => {
        expect(postResponse).toHaveBeenCalledWith(
          expect.objectContaining({ answer: { minute: 20 } }),
        );
      });
      expect(postResponse).toHaveBeenCalledTimes(1);
    });

    it('el slider no arrastra el valor de la tarjeta anterior', async () => {
      renderPlay();

      fireEvent.change(screen.getByRole('slider'), { target: { value: '35' } });
      fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
      // El feedback se saltea con un toque (ADR-030) en vez de esperar sus 4 s.
      fireEvent.click(await screen.findByRole('status'));
      // El avance dispara la precarga: se la deja resolver dentro de `act`.
      await act(async () => {
        await Promise.resolve();
      });

      expect(screen.getByRole('heading')).toHaveTextContent('When does Sett peak?');
      expect(screen.getByRole('slider')).toHaveValue('20');
    });

    it('el feedback dice la mediana', async () => {
      vi.mocked(postResponse).mockResolvedValue({
        recorded: true,
        feedback: { consensus_median: 26, your_answer: 20, sample_size: 88 },
        progress: PROGRESS,
      });
      renderPlay();

      fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

      await waitFor(() => {
        expect(screen.getByRole('status')).toHaveTextContent(
          'Most players said 26 min. You said 20.',
        );
      });
    });
  });

  describe('tipo 3', () => {
    beforeEach(() => {
      useQueue.setState({ questions: [laneMatchup(1), laneMatchup(2)], status: 'ready' });
      vi.mocked(postResponse).mockResolvedValue({
        recorded: true,
        feedback: null,
        progress: PROGRESS,
      });
    });

    it('registra al primer toque con la clave de la opción', async () => {
      renderPlay();

      fireEvent.click(screen.getByRole('button', { name: 'Syndra wins slightly' }));

      await waitFor(() => {
        expect(postResponse).toHaveBeenCalledWith(
          expect.objectContaining({ question_id: 1, answer: { choice: 'a_slight' } }),
        );
      });
    });

    it('las teclas 1 a 5 eligen la opción en el orden de la tarjeta', async () => {
      renderPlay();

      fireEvent.keyDown(window, { key: '4' });

      await waitFor(() => {
        expect(postResponse).toHaveBeenCalledWith(
          expect.objectContaining({ answer: { choice: 'b_slight' } }),
        );
      });
    });

    it('el feedback usa las etiquetas de la pregunta', async () => {
      vi.mocked(postResponse).mockResolvedValue({
        recorded: true,
        feedback: {
          consensus: { a_strong: 0.5, a_slight: 0.25, even: 0.25 },
          agreed_with_majority: true,
          sample_size: 20,
        },
        progress: PROGRESS,
      });
      renderPlay();

      fireEvent.click(screen.getByRole('button', { name: 'Syndra wins hard' }));

      await waitFor(() => {
        expect(screen.getByRole('status')).toHaveTextContent('50% agree with you');
      });
      const overlay = screen.getByRole('status');
      expect(overlay).toHaveTextContent('Zed wins hard');
      expect(overlay).toHaveTextContent('25%');
    });
  });

  describe('feedback (ADR-030)', () => {
    beforeEach(() => {
      useQueue.setState({
        questions: [peakTiming(1), peakTiming(2, 'Sett'), peakTiming(3, 'Lux')],
        status: 'ready',
      });
      vi.mocked(postResponse).mockResolvedValue({
        recorded: true,
        feedback: null,
        progress: PROGRESS,
      });
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    /** Deja resolver el envío o la precarga que disparó lo último que se hizo. */
    async function flush() {
      await act(async () => {
        await Promise.resolve();
      });
    }

    /** Confirma la tarjeta de adelante y espera a que el feedback esté en pantalla. */
    async function answer() {
      fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
      await flush();
      expect(screen.getByRole('status')).toBeInTheDocument();
    }

    it('CA-511 — dura 4 s y después entra la tarjeta siguiente', async () => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      renderPlay();
      await answer();

      act(() => {
        vi.advanceTimersByTime(FEEDBACK_MS - 1);
      });
      expect(screen.getByRole('status')).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(1);
      });
      await flush();
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
      expect(screen.getByRole('heading')).toHaveTextContent('When does Sett peak?');
    });

    it('ADR-032 — la barra de tiempo dura lo mismo que el cartel', async () => {
      renderPlay();
      await answer();

      expect(screen.getByTestId('feedback-timer')).toHaveStyle({
        animationDuration: `${FEEDBACK_MS}ms`,
      });
    });

    it('CA-511 — un toque lo saltea, y dos toques no saltean dos tarjetas', async () => {
      renderPlay();
      await answer();

      const overlay = screen.getByRole('status');
      fireEvent.click(overlay);
      fireEvent.click(overlay);
      await flush();

      expect(screen.queryByRole('status')).not.toBeInTheDocument();
      expect(screen.getByRole('heading')).toHaveTextContent('When does Sett peak?');
    });

    it('CA-511 — Enter y Espacio lo saltean; la tecla mantenida no', async () => {
      renderPlay();
      await answer();

      fireEvent.keyDown(window, { key: 'Enter', repeat: true });
      expect(screen.getByRole('status')).toBeInTheDocument();

      fireEvent.keyDown(window, { key: ' ' });
      await flush();
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
      expect(screen.getByRole('heading')).toHaveTextContent('When does Sett peak?');

      await answer();
      fireEvent.keyDown(window, { key: 'Enter' });
      await flush();
      expect(screen.getByRole('heading')).toHaveTextContent('When does Lux peak?');
      // Saltear no registra nada: sólo se mandaron las dos respuestas.
      expect(postResponse).toHaveBeenCalledTimes(2);
    });

    it('Enter lo saltea aunque el foco quede en el Confirm deshabilitado', async () => {
      renderPlay();
      const confirm = screen.getByRole('button', { name: 'Confirm' });
      confirm.focus();
      await answer();
      expect(confirm).toBeDisabled();

      fireEvent.keyDown(confirm, { key: 'Enter' });
      await flush();

      expect(screen.queryByRole('status')).not.toBeInTheDocument();
      expect(screen.getByRole('heading')).toHaveTextContent('When does Sett peak?');
    });

    it('una tecla cualquiera no lo saltea', async () => {
      renderPlay();
      await answer();

      fireEvent.keyDown(window, { key: '1' });
      fireEvent.keyDown(window, { key: 'a' });

      expect(screen.getByRole('status')).toBeInTheDocument();
    });
  });

  it('ADR-029 — la versión traducida de la tarjeta conserva lo que ya se marcó', () => {
    useQueue.setState({ questions: [traitMultiselect(1), traitMultiselect(2)], status: 'ready' });
    renderPlay();
    fireEvent.click(screen.getByRole('button', { name: 'Poke' }));

    // Es lo que hace `retranslate` al volver el servidor: mismo id, textos nuevos.
    const translated = {
      ...traitMultiselect(1),
      prompt: '¿Qué hace bien Sett?',
      subtitle: 'Elige todos los que correspondan.',
    };
    act(() => {
      useQueue.setState({ questions: [translated, traitMultiselect(2)] });
    });

    expect(screen.getByRole('heading')).toHaveTextContent('¿Qué hace bien Sett?');
    expect(screen.getByRole('button', { name: 'Poke' })).toHaveAttribute('aria-pressed', 'true');
  });
});
