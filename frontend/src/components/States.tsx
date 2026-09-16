/**
 * El esqueleto de carga y las tarjetas de estado — `docs/30-ux-flujos.md` §8.
 *
 * El esqueleto dibuja **la forma de la tarjeta**, no un spinner centrado: tener el maquetado a la
 * vista reduce la sensación de espera y evita el salto cuando la pregunta llega. Sólo se ve en el
 * primer render; entre tarjetas nunca hay carga visible porque la cola se precarga.
 */

import type { ReactNode } from 'react';

export function CardSkeleton() {
  return (
    <div className="flex flex-1 flex-col px-[22px] py-[30px]" aria-hidden="true">
      <div className="h-[26px] w-[78%] bg-skeleton" />
      <div className="mt-3 h-[26px] w-[46%] bg-control" />
      <div className="flex flex-1 items-center gap-3.5 py-6">
        {[0, 1].map((i) => (
          <div key={i} className="flex flex-1 flex-col items-center gap-3">
            <div className="size-[130px] bevel-14 bg-skeleton" />
            <div className="h-3.5 w-[70px] bg-control" />
          </div>
        ))}
      </div>
      <div className="h-12 border border-edge-soft" />
    </div>
  );
}

interface StateCardProps {
  /** Etiqueta en versalita: qué situación es. */
  kind: string;
  title: string;
  children?: ReactNode;
}

export function StateCard({ kind, title, children }: StateCardProps) {
  return (
    <div className="flex flex-col gap-3 border border-white/7 bg-panel px-[18px] py-5">
      <p className="font-mono text-[10px] font-medium tracking-[0.18em] text-faint uppercase">
        {kind}
      </p>
      <p className="font-display text-[17px] leading-snug font-semibold text-ink">{title}</p>
      {children}
    </div>
  );
}

export function RetryButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-11 min-h-11 items-center self-start border border-gold px-5 font-mono text-xs font-semibold tracking-[0.16em] text-gold uppercase"
    >
      Retry
    </button>
  );
}

/**
 * La espera del `429`.
 *
 * La barra acompaña al número en vez de reemplazarlo: comunica cuánto falta sin depender sólo del
 * texto, y el texto sigue estando para quien no ve la barra.
 */
export function Countdown({ seconds, total }: { seconds: number; total: number }) {
  const remaining = total > 0 ? Math.max(0, Math.min(1, seconds / total)) : 0;
  return (
    <div className="h-1 bg-rail">
      <div style={{ width: `${remaining * 100}%` }} className="h-1 bg-cyan transition-[width]" />
    </div>
  );
}
