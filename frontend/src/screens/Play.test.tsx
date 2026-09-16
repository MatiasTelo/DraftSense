/** El motor de tarjetas — CA-502 de `03-criterios-aceptacion.md` §6, y los tipos 2 y 3. */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { laneMatchup, pairwise, peakTiming } from '../test-fixtures';
import { useQueue } from '../store/queue';
import { useSession } from '../store/session';
import { Play } from './Play';

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
  it('muestra la tarjeta de adelante con sus dos campeones y la salida', () => {
    renderPlay();

    expect(screen.getByRole('heading')).toHaveTextContent('Who has more engage?');
    expect(screen.getByText('Alistar')).toBeInTheDocument();
    expect(screen.getByText('Yasuo')).toBeInTheDocument();
    expect(screen.getByText('Not sure')).toBeInTheDocument();
  });

  it('registra al primer toque, sin botón de confirmar', async () => {
    vi.mocked(postResponse).mockResolvedValue({
      recorded: true,
      feedback: null,
      progress: PROGRESS,
    });
    renderPlay();

    fireEvent.click(screen.getByText('Alistar'));

    await waitFor(() => {
      expect(postResponse).toHaveBeenCalledWith(
        expect.objectContaining({ question_id: 1, answer: { choice: 'a' } }),
      );
    });
    expect(screen.queryByRole('button', { name: /confirm/i })).not.toBeInTheDocument();
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

    fireEvent.click(screen.getByText('Alistar'));

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

    fireEvent.click(screen.getByText('Alistar'));

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

    fireEvent.click(screen.getByText('Alistar'));

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

    fireEvent.click(screen.getByText('Alistar'));

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

      await waitFor(
        () => {
          expect(screen.getByRole('heading')).toHaveTextContent('When does Sett peak?');
        },
        { timeout: 2500 },
      );
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
});
