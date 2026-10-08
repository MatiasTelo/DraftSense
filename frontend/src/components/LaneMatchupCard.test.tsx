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

  it('dibuja la escala en el orden en que llega, sin reordenarla', () => {
    // El straightlining se cuenta por la clave de la opción (`docs/22-calidad-de-datos.md` §5.2):
    // eso vale sólo si la tarjeta muestra cada clave siempre en el mismo lugar, el que manda el
    // servidor. Si la tarjeta ordenara por su cuenta, la posición en pantalla dejaría de ser la clave.
    const question = laneMatchup(1);
    const reversed = { ...question, options: [...question.options].reverse() };
    render(
      <LaneMatchupCard
        question={reversed}
        helpOpen={false}
        onToggleHelp={() => undefined}
        onChoose={() => undefined}
        disabled={false}
      />,
    );

    const labels = screen
      .getAllByRole('button')
      .map((button) => button.textContent)
      .filter((text) => text !== '?');
    expect(labels).toEqual(reversed.options.map((option) => option.label));
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
