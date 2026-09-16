/** CA-503 y CA-504 de `03-criterios-aceptacion.md` §6, y los textos de `30-ux-flujos.md` §5.1. */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Feedback } from '../api';
import { FeedbackOverlay } from './FeedbackOverlay';

const LABELS = [
  { key: 'a', label: 'Alistar' },
  { key: 'b', label: 'Yasuo' },
  { key: 'unknown', label: 'Not sure' },
];

const LANE_LABELS = [
  { key: 'a_strong', label: 'Nunu & Willump wins hard' },
  { key: 'a_slight', label: 'Nunu & Willump wins slightly' },
  { key: 'even', label: 'Even' },
  { key: 'b_slight', label: 'Aurelion Sol wins slightly' },
  { key: 'b_strong', label: 'Aurelion Sol wins hard' },
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

  it('tipo 2 — dice la mediana y la respuesta propia, sin porcentajes', () => {
    render(
      <FeedbackOverlay
        feedback={{ consensus_median: 26, your_answer: 27, sample_size: 88 }}
        labels={[]}
        yourKey=""
        streak={3}
        unit="min"
      />,
    );

    const overlay = screen.getByRole('status');
    expect(overlay).toHaveTextContent('Most players said 26 min. You said 27.');
    expect(overlay).toHaveTextContent('88 answers');
    expect(overlay.textContent).not.toMatch(/%|in the/);
  });

  it('una clave de consenso nula no rompe el panel', () => {
    // El contrato omite las claves que no aplican; si alguna llegara en `null`, la tarjeta
    // siguiente tiene que aparecer igual.
    const legacy = {
      consensus: null,
      consensus_median: 26,
      your_answer: 27,
      agreed_with_majority: null,
      sample_size: 20,
    } as unknown as Feedback;

    render(<FeedbackOverlay feedback={legacy} labels={[]} yourKey="" streak={1} unit="min" />);

    expect(screen.getByRole('status')).toHaveTextContent('Most players said 26 min. You said 27.');
  });

  it('tipo 3 — las etiquetas largas se muestran completas, con su porcentaje', () => {
    render(
      <FeedbackOverlay
        feedback={{
          consensus: { a_strong: 0.31, a_slight: 0.35, even: 0.1, b_slight: 0.19, b_strong: 0.05 },
          agreed_with_majority: false,
          sample_size: 42,
        }}
        labels={LANE_LABELS}
        yourKey="b_slight"
        streak={2}
        layout="stacked"
      />,
    );

    const overlay = screen.getByRole('status');
    expect(overlay).toHaveTextContent("You're in the 19%");
    for (const { label } of LANE_LABELS) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText('35%')).toBeInTheDocument();
    expect(overlay).toHaveTextContent('42 answers');
  });
});
