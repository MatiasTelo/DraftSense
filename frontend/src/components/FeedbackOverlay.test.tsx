/** CA-503 y CA-504 de `03-criterios-aceptacion.md` §6. */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FeedbackOverlay } from './FeedbackOverlay';

const LABELS = [
  { key: 'a', label: 'Alistar' },
  { key: 'b', label: 'Yasuo' },
  { key: 'unknown', label: 'Not sure' },
];

describe('FeedbackOverlay', () => {
  it('CA-503 — con soporte bajo el mensaje es positivo y no un panel vacío', () => {
    render(<FeedbackOverlay feedback={null} labels={LABELS} yourKey="a" streak={3} />);

    expect(screen.getByRole('status')).toHaveTextContent(
      "You're one of the first to answer this",
    );
    // No hay distribución que mostrar: durante los primeros días todas las preguntas caen acá.
    expect(screen.queryByText('Alistar')).not.toBeInTheDocument();
  });

  it('muestra el porcentaje de acuerdo cuando coincide con la mayoría', () => {
    render(
      <FeedbackOverlay
        feedback={{
          consensus: { a: 0.74, b: 0.19, unknown: 0.07 },
          agreed_with_majority: true,
          sample_size: 312,
        }}
        labels={LABELS}
        yourKey="a"
        streak={3}
      />,
    );

    const overlay = screen.getByRole('status');
    expect(overlay).toHaveTextContent('74% agree with you');
    expect(overlay).toHaveTextContent('312 answers');
  });

  it('CA-504 — la discrepancia se informa sin ninguna marca de error', () => {
    render(
      <FeedbackOverlay
        feedback={{
          consensus: { a: 0.74, b: 0.19, unknown: 0.07 },
          agreed_with_majority: false,
          sample_size: 312,
        }}
        labels={LABELS}
        yourKey="b"
        streak={3}
      />,
    );

    const overlay = screen.getByRole('status');
    expect(overlay).toHaveTextContent("You're in the 19%");
    // No hay respuesta correcta: la discrepancia es el dato, no una falla del usuario.
    expect(overlay.textContent).not.toMatch(/wrong|incorrect|oops/i);
  });

  it('el porcentaje va escrito además de dibujado, para no depender del color', () => {
    render(
      <FeedbackOverlay
        feedback={{
          consensus: { a: 0.74, b: 0.19, unknown: 0.07 },
          agreed_with_majority: true,
          sample_size: 312,
        }}
        labels={LABELS}
        yourKey="a"
        streak={1}
      />,
    );

    expect(screen.getByText('74%')).toBeInTheDocument();
    expect(screen.getByText('19%')).toBeInTheDocument();
    expect(screen.getByText('7%')).toBeInTheDocument();
  });

  it('celebra la racha sólo en los múltiplos de diez', () => {
    const { rerender } = render(
      <FeedbackOverlay feedback={null} labels={LABELS} yourKey="a" streak={10} />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('10 in a row');

    rerender(<FeedbackOverlay feedback={null} labels={LABELS} yourKey="a" streak={11} />);
    expect(screen.getByRole('status')).not.toHaveTextContent('in a row');
  });
});
