/** El retrato y su caída cuando Data Dragon no responde (`docs/10-arquitectura.md` §7). */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { champion } from '../test-fixtures';
import { ChampionPortrait } from './ChampionPortrait';

describe('ChampionPortrait', () => {
  it('el alt es el nombre del campeón, que es lo que hace falta oír', () => {
    render(<ChampionPortrait champion={champion(12, 'Alistar')} size={130} bevel="bevel-14" />);
    expect(screen.getByAltText('Alistar')).toBeInTheDocument();
  });

  it('si la imagen no carga, cae a las iniciales y no a un hueco', () => {
    render(<ChampionPortrait champion={champion(875, 'Sett')} size={130} bevel="bevel-14" />);

    fireEvent.error(screen.getByAltText('Sett'));

    // La tarjeta sigue siendo respondible: el nombre va debajo y el marcador no la rompe.
    const fallback = screen.getByRole('img', { name: 'Sett' });
    expect(fallback).toHaveTextContent('S');
  });

  it('con nombre compuesto toma dos iniciales', () => {
    render(
      <ChampionPortrait champion={champion(555, 'Master Yi')} size={130} bevel="bevel-14" />,
    );

    fireEvent.error(screen.getByAltText('Master Yi'));

    expect(screen.getByRole('img', { name: 'Master Yi' })).toHaveTextContent('MY');
  });
});
