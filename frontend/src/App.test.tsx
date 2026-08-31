import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import App from './App';

describe('App', () => {
  it('muestra la promesa y la fricción en el landing', () => {
    render(<App />);
    expect(screen.getByText(/Help rank every champion/i)).toBeInTheDocument();
    expect(screen.getByText(/No account/i)).toBeInTheDocument();
  });
});
