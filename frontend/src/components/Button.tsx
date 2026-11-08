/**
 * Los dos botones del sistema.
 *
 * Ambos miden 54 px de alto y llevan la esquina biselada. El borde del secundario queda cortado
 * en el bisel, igual que en el maquetado: la diagonal es el recorte, no una línea más.
 *
 * Responden al puntero con color y a la presión con una escala leve (ADR-032). No hay sombras ni
 * resplandor: el bisel es un `clip-path` y recorta cualquier `box-shadow`. Los estados van con
 * `enabled:` para que un botón deshabilitado no reaccione como si se pudiera tocar.
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
  'font-bold uppercase tracking-[0.18em] disabled:opacity-50 cursor-pointer disabled:cursor-default ' +
  'transition-[background-color,color,transform,scale,opacity] duration-150 ease-out-quart ' +
  'enabled:active:scale-[0.98]';

export function PrimaryButton({ children, onClick, disabled, type = 'button' }: ButtonProps) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${SHARED} bg-gold text-surface enabled:hover:bg-gold-bright`}>
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
      className={`${SHARED} border border-gold text-gold enabled:hover:bg-gold/10 enabled:hover:text-gold-bright`}
    >
      {children}
    </button>
  );
}
