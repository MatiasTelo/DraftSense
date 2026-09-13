/** CA-005 — omitir el onboarding también es una respuesta. */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Onboarding } from './Onboarding';

vi.mock('../lib/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/client')>()),
  saveOnboarding: vi.fn(),
}));

const { saveOnboarding } = await import('../lib/client');

function renderOnboarding() {
  return render(
    <MemoryRouter>
      <Onboarding />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(saveOnboarding).mockResolvedValue({ onboarding_seen: true });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('Onboarding', () => {
  it('explica por qué se pregunta, para que no se lea como un formulario', () => {
    renderOnboarding();
    expect(
      screen.getByText('Optional. It helps us compare answers across skill levels.'),
    ).toBeInTheDocument();
  });

  it('CA-005 — Skip guarda los tres campos en null y no vuelve a preguntar', async () => {
    renderOnboarding();

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));

    await waitFor(() => {
      expect(saveOnboarding).toHaveBeenCalledWith({
        declared_rank: null,
        declared_main_role: null,
        declared_hours_bucket: null,
      });
    });
  });

  it('se puede continuar con los tres vacíos: nada es obligatorio', async () => {
    renderOnboarding();

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await waitFor(() => {
      expect(saveOnboarding).toHaveBeenCalledWith({
        declared_rank: null,
        declared_main_role: null,
        declared_hours_bucket: null,
      });
    });
  });

  it('manda los valores de las columnas, no las etiquetas de la pantalla', async () => {
    renderOnboarding();

    fireEvent.click(screen.getByRole('button', { name: 'Plat' }));
    fireEvent.click(screen.getByRole('button', { name: 'Bot' }));
    fireEvent.click(screen.getByRole('button', { name: '5-15' }));
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await waitFor(() => {
      expect(saveOnboarding).toHaveBeenCalledWith({
        declared_rank: 'platinum',
        declared_main_role: 'adc',
        declared_hours_bucket: '5-15',
      });
    });
  });

  it('«I don\'t play ranked» guarda unranked, que no es lo mismo que omitir', async () => {
    renderOnboarding();

    fireEvent.click(screen.getByRole('button', { name: "I don't play ranked" }));
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    await waitFor(() => {
      expect(saveOnboarding).toHaveBeenCalledWith(
        expect.objectContaining({ declared_rank: 'unranked' }),
      );
    });
  });

  it('volver a tocar el chip elegido lo deselecciona', async () => {
    renderOnboarding();

    const gold = screen.getByRole('button', { name: 'Gold' });
    fireEvent.click(gold);
    expect(gold).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(gold);
    expect(gold).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await waitFor(() => {
      expect(saveOnboarding).toHaveBeenCalledWith(
        expect.objectContaining({ declared_rank: null }),
      );
    });
  });

  it('ofrece los once rangos y los cinco roles: el dominio exacto de cada columna', () => {
    renderOnboarding();

    for (const label of ['Iron', 'Master', 'Grandmaster', 'Challenger', "I don't play ranked"]) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
    // `Fill` no existe en `lane_role`: se habría guardado como null y sería indistinguible de
    // omitir (`docs/25-agregacion.md` §12, punto 4).
    expect(screen.queryByRole('button', { name: 'Fill' })).not.toBeInTheDocument();
  });
});
