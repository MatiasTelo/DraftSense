/** Las dos barras de `/play`, `/me` y `/leaderboard` — ADR-031 y `30-ux-flujos.md` §5. */

import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { BottomNav, TopBar } from './Chrome';

const DESTINATIONS = [
  ['Play', '/play'],
  ['Profile', '/me'],
  ['Ranks', '/leaderboard'],
] as const;

describe('Chrome', () => {
  // jsdom no aplica CSS: acá se ven las dos navegaciones juntas. Cuál se muestra en cada tamaño
  // lo deciden `hidden lg:flex` y `lg:hidden`, y eso se verifica a mano.
  it('ADR-031 — la barra superior lleva los tres destinos para el escritorio', () => {
    render(
      <MemoryRouter initialEntries={['/me']}>
        <TopBar streak={3} answers={12} />
      </MemoryRouter>,
    );

    const header = screen.getByRole('banner');
    expect(header).toHaveTextContent('🔥 3');
    expect(header).toHaveTextContent('12 answered');
    for (const [name, href] of DESTINATIONS) {
      expect(within(header).getByRole('link', { name })).toHaveAttribute('href', href);
    }
    expect(within(header).getByRole('link', { name: 'Profile' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('la barra inferior sigue llevando los tres destinos para el celular', () => {
    render(
      <MemoryRouter initialEntries={['/play']}>
        <BottomNav />
      </MemoryRouter>,
    );

    const nav = screen.getByRole('navigation');
    for (const [name, href] of DESTINATIONS) {
      expect(within(nav).getByRole('link', { name })).toHaveAttribute('href', href);
    }
  });
});
