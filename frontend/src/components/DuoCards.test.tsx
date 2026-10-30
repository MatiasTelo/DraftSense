/** Las tarjetas de duplas de la semana 8: el 2v2 del tipo 3 y el tipo 4 (`20-tipos-de-pregunta.md`
 * §4.2 y §5, CA-105). */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { botLane, duoSynergy } from '../test-fixtures';
import { DuoSynergyCard } from './DuoSynergyCard';
import { LaneMatchupCard } from './LaneMatchupCard';

function optionTexts(): (string | null)[] {
  return screen
    .getAllByRole('button')
    .map((button) => button.textContent)
    .filter((text) => text !== '?');
}

describe('LaneMatchupCard, variante 2v2', () => {
  it('apila las duplas con los dos nombres y las etiquetas de pareja', () => {
    const onChoose = vi.fn();
    render(
      <LaneMatchupCard
        question={botLane(1)}
        helpOpen={false}
        onToggleHelp={() => undefined}
        onChoose={onChoose}
        disabled={false}
      />,
    );

    expect(screen.getByText('Caitlyn + Lux')).toBeInTheDocument();
    expect(screen.getByText('Samira + Nautilus')).toBeInTheDocument();
    expect(screen.getByText('vs')).toBeInTheDocument();
    expect(screen.getByText('BOT')).toBeInTheDocument();
    expect(optionTexts()).toEqual([
      'Top pair wins hard',
      'Top pair wins slightly',
      'Even',
      'Bottom pair wins slightly',
      'Bottom pair wins hard',
    ]);

    fireEvent.click(screen.getByRole('button', { name: 'Bottom pair wins slightly' }));
    expect(onChoose).toHaveBeenCalledWith('b_slight');
  });
});

describe('DuoSynergyCard', () => {
  it('muestra las dos duplas sin vs y registra al primer toque', () => {
    const onChoose = vi.fn();
    render(
      <DuoSynergyCard
        question={duoSynergy(2)}
        helpOpen={false}
        onToggleHelp={() => undefined}
        onChoose={onChoose}
        disabled={false}
      />,
    );

    expect(screen.getByText('Orianna + Jarvan IV')).toBeInTheDocument();
    expect(screen.getByText('Twisted Fate + Hecarim')).toBeInTheDocument();
    expect(screen.getByText('MID + JUNGLE')).toBeInTheDocument();
    expect(screen.queryByText('vs')).not.toBeInTheDocument();
    expect(optionTexts()).toEqual(['Top pair', 'About the same', 'Bottom pair']);

    fireEvent.click(screen.getByRole('button', { name: 'About the same' }));
    expect(onChoose).toHaveBeenCalledWith('similar');
  });

  it('deshabilitada no registra nada', () => {
    const onChoose = vi.fn();
    render(
      <DuoSynergyCard
        question={duoSynergy(2)}
        helpOpen={false}
        onToggleHelp={() => undefined}
        onChoose={onChoose}
        disabled
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Top pair' }));
    expect(onChoose).not.toHaveBeenCalled();
  });
});
