/**
 * Los dos botones del sistema.
 *
 * Ambos miden 54 px de alto y llevan la esquina biselada. El borde del secundario queda cortado
 * en el bisel, igual que en el maquetado: la diagonal es el recorte, no una línea más.
 */

import type { ReactNode } from 'react';

interface ButtonProps {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: 'button' | 'submit';
}

const SHARED =
  'flex h-[54px] w-full items-center justify-center bevel-12 font-display text-[15px] ' +
  'font-bold uppercase tracking-[0.18em] disabled:opacity-50';

export function PrimaryButton({ children, onClick, disabled, type = 'button' }: ButtonProps) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${SHARED} bg-gold text-surface`}>
      {children}
    </button>
  );
}

export function SecondaryButton({ children, onClick, disabled, type = 'button' }: ButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${SHARED} border border-gold text-gold`}
    >
      {children}
    </button>
  );
}
