/**
 * Tipo 1, el ranking de cinco — `docs/20-tipos-de-pregunta.md` §2, ADR-022 y CA-213.
 *
 * El arrastre en sí no se prueba acá: jsdom no calcula posiciones y `@dnd-kit` decide sobre qué
 * fila cae cada una con ellas. Se verifica a mano a 360 px, como el resto de CA-505.
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { pairwise } from '../test-fixtures';
import { DimensionRankingCard } from './DimensionRankingCard';

function renderCard(disabled = false) {
  const onAnswer = vi.fn();
  render(
    <DimensionRankingCard
      question={pairwise(1)}
      helpOpen={false}
      onToggleHelp={() => undefined}
      onAnswer={onAnswer}
      disabled={disabled}
    />,
  );
  return onAnswer;
}

function rows(): string[] {
  return within(screen.getByRole('list'))
    .getAllByRole('button')
    .map((row) => row.getAttribute('aria-label') ?? '');
}

describe('DimensionRankingCard', () => {
  it('muestra los cinco en el orden servido, numerados, con la instrucción', () => {
    renderCard();

    expect(rows()).toEqual(['1. Alistar', '2. Yasuo', '3. Leona', '4. Jax', '5. Lux']);
    expect(screen.getByText('Drag to order: most at the top.')).toBeInTheDocument();
  });

  it('Confirm manda el orden de la lista, de más a menos', () => {
    const onAnswer = renderCard();

    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));

    expect(onAnswer).toHaveBeenCalledWith({ order: [12, 157, 89, 24, 99] });
  });

  it('CA-213 — Not sure vale para el ranking entero', () => {
    const onAnswer = renderCard();

    fireEvent.click(screen.getByRole('button', { name: 'Not sure' }));

    expect(onAnswer).toHaveBeenCalledWith({ choice: 'unknown' });
  });

  it('deshabilitada no manda nada', () => {
    const onAnswer = renderCard(true);

    fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Not sure' }));

    expect(onAnswer).not.toHaveBeenCalled();
  });
});
