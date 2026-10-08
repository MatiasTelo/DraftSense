/** `/leaderboard` — las pestañas de ventana (`docs/30-ux-flujos.md` §7 y §9). */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Leaderboard } from './Leaderboard';

vi.mock('../lib/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/client')>()),
  fetchLeaderboard: vi.fn(),
}));

const { fetchLeaderboard } = await import('../lib/client');

function renderLeaderboard() {
  return render(
    <MemoryRouter>
      <Leaderboard />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(fetchLeaderboard).mockImplementation((window) =>
    Promise.resolve({
      window,
      generated_at: '2026-09-16T12:00:00Z',
      entries: [{ rank: 1, alias: 'brave-poro-4417', answers_count: 412, is_you: false }],
    }),
  );
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('Leaderboard', () => {
  it('las tres pestañas de ventana tienen 44 px de área táctil', async () => {
    renderLeaderboard();
    await screen.findByText('brave-poro-4417');

    for (const name of ['Today', 'This week', 'All time']) {
      expect(screen.getByRole('button', { name })).toHaveClass('min-h-11');
    }
  });

  it('arranca en la semana y cambiar de pestaña pide esa ventana', async () => {
    renderLeaderboard();
    await waitFor(() => expect(fetchLeaderboard).toHaveBeenCalledWith('week'));

    fireEvent.click(screen.getByRole('button', { name: 'All time' }));

    await waitFor(() => expect(fetchLeaderboard).toHaveBeenCalledWith('all'));
    expect(screen.getByRole('button', { name: 'All time' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});
