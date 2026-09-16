/** El motor de tarjetas — CA-502 de `03-criterios-aceptacion.md` §6. */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pairwise } from '../test-fixtures';
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
});
