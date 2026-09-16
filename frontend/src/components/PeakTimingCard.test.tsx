/** Tipo 2 — `docs/20-tipos-de-pregunta.md` §3 y `docs/30-ux-flujos.md` §9 y §10. */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { peakTiming } from '../test-fixtures';
import { PeakTimingCard } from './PeakTimingCard';

function renderCard(disabled = false) {
  const onConfirm = vi.fn();
  render(
    <PeakTimingCard
      question={peakTiming(1)}
      helpOpen={false}
      onToggleHelp={() => undefined}
      onConfirm={onConfirm}
      disabled={disabled}
    />,
  );
  return onConfirm;
}

describe('PeakTimingCard', () => {
  it('arranca en el valor por defecto que manda el servidor', () => {
    renderCard();

    expect(screen.getByRole('slider')).toHaveValue('20');
    expect(screen.getByText('Kayle')).toBeInTheDocument();
  });

  it('mover el slider no registra: la respuesta sale con Confirm', () => {
    const onConfirm = renderCard();

    fireEvent.change(screen.getByRole('slider'), { target: { value: '27' } });
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(onConfirm).toHaveBeenCalledWith(27);
  });

  it('confirmar sin mover el slider es una respuesta válida y manda el valor por defecto', () => {
    const onConfirm = renderCard();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    expect(onConfirm).toHaveBeenCalledWith(20);
  });

  it('Enter confirma con el valor actual', () => {
    const onConfirm = renderCard();

    fireEvent.change(screen.getByRole('slider'), { target: { value: '33' } });
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(onConfirm).toHaveBeenCalledExactlyOnceWith(33);
  });

  it('Enter sobre un botón no confirma por su cuenta: el botón ya lo convierte en clic', () => {
    const onConfirm = renderCard();

    fireEvent.keyDown(screen.getByRole('button', { name: 'Confirm' }), { key: 'Enter' });

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('deshabilitada, ni Confirm ni Enter registran', () => {
    const onConfirm = renderCard(true);

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole('slider')).toBeDisabled();
  });

  it('el slider se anuncia con el enunciado y con el valor en minutos', () => {
    renderCard();

    const slider = screen.getByRole('slider', { name: 'When does Kayle peak?' });
    expect(slider).toHaveAttribute('aria-valuetext', '20 min');

    fireEvent.change(slider, { target: { value: '8' } });
    expect(slider).toHaveAttribute('aria-valuetext', '8 min');
  });

  it('las marcas de la escala vienen del servidor', () => {
    renderCard();

    expect(screen.getByText('laning')).toBeInTheDocument();
    expect(screen.getByText('mid game')).toBeInTheDocument();
    expect(screen.getByText('late game')).toBeInTheDocument();
    // El extremo derecho lleva su número aunque no tenga marca.
    expect(screen.getByText('40')).toBeInTheDocument();
  });
});
