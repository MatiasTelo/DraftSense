/** El idioma — CA-510, ADR-028 y ADR-029. */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Landing } from '../screens/Landing';
import { useLang } from '../store/lang';
import { useQueue } from '../store/queue';
import { pairwise } from '../test-fixtures';

vi.mock('../lib/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/client')>()),
  fetchQuestions: vi.fn(),
  fetchQueuedQuestions: vi.fn(),
}));

const { fetchQuestions, fetchQueuedQuestions } = await import('../lib/client');

afterEach(() => {
  useLang.getState().setLang('en');
  window.localStorage.clear();
  vi.clearAllMocks();
});

describe('LanguageToggle', () => {
  it('CA-510 — elegir ES cambia la interfaz, se recuerda y traduce la cola (ADR-029)', async () => {
    const translated = { ...pairwise(1), prompt: '¿Quién tiene más engage?' };
    vi.mocked(fetchQueuedQuestions).mockResolvedValue({
      questions: [translated, { ...pairwise(2), prompt: '¿Quién tiene más engage?' }],
    });
    vi.mocked(fetchQuestions).mockResolvedValue({ questions: [] });
    useQueue.setState({ questions: [pairwise(1), pairwise(2)], status: 'ready' });
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Help rank every champion/)).toBeInTheDocument();

    // El pedido de la cola traducida, y la precarga que dispara, resuelven después del clic: se
    // los deja terminar dentro de `act`.
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'es' }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.getByText(/Ayuda a clasificar a cada campeón/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'es' })).toHaveAttribute('aria-pressed', 'true');
    expect(window.localStorage.getItem('draftsense.lang')).toBe('es');
    // Las mismas preguntas, armadas en español: la de adelante no cambia.
    expect(fetchQueuedQuestions).toHaveBeenCalledExactlyOnceWith([1, 2], 'es');
    await waitFor(() => {
      expect(useQueue.getState().questions[0]).toEqual(translated);
    });
    expect(useQueue.getState().questions).toHaveLength(2);
  });

  it('volver a elegir el idioma activo no descarta nada', () => {
    useQueue.setState({ questions: [pairwise(1)], status: 'ready' });
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'en' }));

    expect(useQueue.getState().questions).toHaveLength(1);
    expect(fetchQueuedQuestions).not.toHaveBeenCalled();
  });
});
