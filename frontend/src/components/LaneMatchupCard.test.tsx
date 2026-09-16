/** Tipo 3, variante 1v1 — `docs/20-tipos-de-pregunta.md` §4.1 y CA-104. */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { laneMatchup } from '../test-fixtures';
import { LaneMatchupCard } from './LaneMatchupCard';

function renderCard(disabled = false) {
  const onChoose = vi.fn();
  render(
    <LaneMatchupCard
      question={laneMatchup(1)}
      helpOpen={false}
      onToggleHelp={() => undefined}
      onChoose={onChoose}
      disabled={disabled}
    />,
  );
  return onChoose;
}

describe('LaneMatchupCard', () => {
  it('CA-104 — las cinco opciones llevan el nombre del campeón, no «A» y «B»', () => {
    renderCard();

    const options = screen
      .getAllByRole('button')
      .map((button) => button.textContent)
      .filter((text) => text !== '?');
    expect(options).toEqual([
      'Syndra wins hard',
      'Syndra wins slightly',
      'Even',
      'Zed wins slightly',
      'Zed wins hard',
    ]);
    expect(screen.queryByText(/\bA wins\b/)).not.toBeInTheDocument();
  });

  it('muestra el carril y a los dos campeones', () => {
    renderCard();

    expect(screen.getByText('MID')).toBeInTheDocument();
    expect(screen.getByAltText('Syndra')).toBeInTheDocument();
    expect(screen.getByAltText('Zed')).toBeInTheDocument();
  });

  it('registra al primer toque con la clave de la opción', () => {
    const onChoose = renderCard();

    fireEvent.click(screen.getByRole('button', { name: 'Zed wins slightly' }));

    expect(onChoose).toHaveBeenCalledExactlyOnceWith('b_slight');
  });

  it('no tiene botón de confirmar', () => {
    renderCard();

    expect(screen.queryByRole('button', { name: /confirm/i })).not.toBeInTheDocument();
  });

  it('deshabilitada no registra', () => {
    const onChoose = renderCard(true);

    fireEvent.click(screen.getByRole('button', { name: 'Even' }));

    expect(onChoose).not.toHaveBeenCalled();
  });
});
