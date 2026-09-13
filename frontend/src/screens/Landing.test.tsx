/** El landing — `docs/30-ux-flujos.md` §3. */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { useSession } from '../store/session';
import { Landing } from './Landing';

function renderLanding() {
  return render(
    <MemoryRouter>
      <Landing />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  useSession.setState({ ready: false, onboardingSeen: false });
});

describe('Landing', () => {
  it('muestra la promesa, la fricción y el propósito', () => {
    renderLanding();

    expect(screen.getByText(/Help rank every champion/i)).toBeInTheDocument();
    expect(screen.getByText(/No account/i)).toBeInTheDocument();
    // El motivo del proyecto es parte del gancho, no un crédito al pie.
    expect(screen.getByText(/public research at UTN Mendoza/i)).toBeInTheDocument();
  });

  it('a quien llega por primera vez le ofrece Start', () => {
    useSession.setState({ ready: true, onboardingSeen: false });
    renderLanding();

    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  });

  it('a quien ya pasó por el onboarding le ofrece Continue', () => {
    useSession.setState({ ready: true, onboardingSeen: true });
    renderLanding();

    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument();
  });

  it('mientras la sesión no contestó, no adivina: muestra Start', () => {
    useSession.setState({ ready: false, onboardingSeen: true });
    renderLanding();

    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  });
});
