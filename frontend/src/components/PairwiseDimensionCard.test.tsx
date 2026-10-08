/** Tipo 1 — la posición en pantalla de cada opción (`docs/22-calidad-de-datos.md` §5.2). */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { PairwiseDimensionQuestion } from '../api';
import { pairwise } from '../test-fixtures';
import { PairwiseDimensionCard } from './PairwiseDimensionCard';

function renderCard(question: PairwiseDimensionQuestion) {
  const onChoose = vi.fn();
  render(
    <PairwiseDimensionCard
      question={question}
      helpOpen={false}
      onToggleHelp={() => undefined}
      onChoose={onChoose}
      disabled={false}
    />,
  );
  return onChoose;
}

describe('PairwiseDimensionCard', () => {
  it('«a» va siempre a la izquierda, aunque el arreglo llegue en otro orden', () => {
    // El straightlining se cuenta por la clave de la opción porque `a` ocupa siempre el mismo
    // lugar. Si esta tarjeta ubicara los lados según el orden del arreglo, un cambio inocente en
    // el servidor rompería la detección sin que ningún test del backend lo notara.
    const question = pairwise(1, 'Alistar', 'Yasuo');
    const shuffled = { ...question, options: [...question.options].reverse() };
    const onChoose = renderCard(shuffled);

    const [left, right] = screen
      .getAllByRole('button')
      .filter((button) => button.querySelector('img') !== null);
    expect(left).toHaveTextContent('Alistar');
    expect(right).toHaveTextContent('Yasuo');

    fireEvent.click(left!);
    expect(onChoose).toHaveBeenCalledExactlyOnceWith('a');
  });

  it('«Not sure» es una opción aparte, debajo de los retratos', () => {
    const onChoose = renderCard(pairwise(2));

    fireEvent.click(screen.getByRole('button', { name: 'Not sure' }));

    expect(onChoose).toHaveBeenCalledExactlyOnceWith('unknown');
  });
});
