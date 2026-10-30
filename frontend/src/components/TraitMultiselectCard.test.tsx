/** Tipo 5 — `20-tipos-de-pregunta.md` §6, CA-509 y ADR-027. */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { traitMultiselect } from '../test-fixtures';
import { TraitMultiselectCard } from './TraitMultiselectCard';

function renderCard(disabled = false) {
  const onConfirm = vi.fn();
  render(<TraitMultiselectCard question={traitMultiselect(1)} onConfirm={onConfirm} disabled={disabled} />);
  return onConfirm;
}

const confirm = () => screen.getByRole('button', { name: 'Confirm' });

describe('TraitMultiselectCard', () => {
  it('muestra el enunciado, el subtítulo y los siete atributos', () => {
    renderCard();

    expect(screen.getByText('What does Sett do well?')).toBeInTheDocument();
    expect(screen.getByText('Pick all that apply.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { pressed: false })).toHaveLength(7);
  });

  it('CA-509 — sin ningún atributo marcado, Confirm está deshabilitado y Enter no envía', () => {
    const onConfirm = renderCard();

    expect(confirm()).toBeDisabled();
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Dive/ }));
    expect(confirm()).toBeEnabled();
  });

  it('envía los marcados en el orden de la grilla, no en el que se tocaron', () => {
    const onConfirm = renderCard();

    fireEvent.click(screen.getByRole('button', { name: /Dive/ }));
    fireEvent.click(screen.getByRole('button', { name: /Engage/ }));
    fireEvent.click(confirm());

    expect(onConfirm).toHaveBeenCalledWith(['engage', 'dive']);
  });

  it('volver a tocar un atributo lo desmarca', () => {
    renderCard();
    const poke = screen.getByRole('button', { name: /Poke/ });

    fireEvent.click(poke);
    expect(poke).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(poke);
    expect(poke).toHaveAttribute('aria-pressed', 'false');
    expect(confirm()).toBeDisabled();
  });

  it('las teclas 1 a 7 marcan en el orden de la grilla y Enter confirma', () => {
    const onConfirm = renderCard();

    fireEvent.keyDown(window, { key: '1' });
    fireEvent.keyDown(window, { key: '7' });
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(onConfirm).toHaveBeenCalledWith(['engage', 'split_push']);
  });

  it('cada atributo tiene su definición a un toque (CA-506)', () => {
    renderCard();

    fireEvent.click(screen.getByRole('button', { name: 'What peel means' }));
    expect(screen.getByText('Keeps divers off their carries.')).toBeInTheDocument();
  });
});
