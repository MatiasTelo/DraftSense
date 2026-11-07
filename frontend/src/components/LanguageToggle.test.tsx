/** El idioma — CA-510 y ADR-028. */

import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { Landing } from '../screens/Landing';
import { useLang } from '../store/lang';
import { useQueue } from '../store/queue';
import { pairwise } from '../test-fixtures';

afterEach(() => {
  useLang.getState().setLang('en');
  window.localStorage.clear();
});

describe('LanguageToggle', () => {
  it('CA-510 — elegir ES cambia la interfaz, se recuerda y descarta la cola', () => {
    useQueue.setState({ questions: [pairwise(1), pairwise(2)], status: 'ready' });
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Help rank every champion/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'es' }));

    expect(screen.getByText(/Ayuda a clasificar a cada campeón/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'es' })).toHaveAttribute('aria-pressed', 'true');
    expect(window.localStorage.getItem('draftsense.lang')).toBe('es');
    // Las preguntas en cola vinieron armadas en inglés: se descartan.
    expect(useQueue.getState().questions).toHaveLength(0);
    expect(useQueue.getState().status).toBe('idle');
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
  });
});
