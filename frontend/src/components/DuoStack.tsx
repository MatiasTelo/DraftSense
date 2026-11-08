/**
 * Las duplas apiladas, que comparten la variante 2v2 del tipo 3 y el tipo 4
 * (`docs/20-tipos-de-pregunta.md` §4.2 y §5, `docs/30-ux-flujos.md` §5, nota del 29/10).
 *
 * **Una dupla por bloque, una arriba de la otra**, no cuatro retratos en fila: a 360 px cuatro
 * íconos en línea quedan por debajo del área táctil y no dicen quién va con quién. Cada bloque
 * lleva los dos retratos y «Caitlyn + Lux», en el orden en que llegan, que es el de los roles del
 * contexto (ADR-026). El cliente no reordena: el servidor ya puso primero al adc, al top o al mid.
 */

import type { Side } from '../api';
import { ChampionPortrait } from './ChampionPortrait';

function Duo({ side }: { side: Side }) {
  return (
    <div className="flex items-center gap-3 border border-white/7 bg-panel px-3 py-2.5">
      <div className="flex shrink-0 gap-1.5">
        {side.champions.map((champion) => (
          <ChampionPortrait key={champion.id} champion={champion} size={48} bevel="bevel-12" />
        ))}
      </div>
      <span className="min-w-0 font-display text-[15px] leading-tight font-semibold text-ink">
        {side.champions.map((champion) => champion.name).join(' + ')}
      </span>
    </div>
  );
}

interface Props {
  sides: Side[];
  /** El separador entre las dos duplas: `vs` en el 2v2, nada en la sinergia. */
  separator?: string;
}

export function DuoStack({ sides, separator }: Props) {
  const [top, bottom] = sides;
  if (top === undefined || bottom === undefined) return null;
  return (
    <div className="flex flex-col gap-2">
      <Duo side={top} />
      {separator !== undefined && (
        <span className="self-center font-display text-sm font-semibold tracking-[0.12em] text-faint uppercase">
          {separator}
        </span>
      )}
      <Duo side={bottom} />
    </div>
  );
}

/**
 * La lista de opciones de una tarjeta que registra al primer toque, en el orden en que llega.
 *
 * Las opciones entran escalonadas (40 ms cada una, ADR-032) y se pueden tocar mientras entran. El
 * escalonado sigue el orden de la lista y **no lo cambia**: la posición de cada opción es fija
 * porque el *straightlining* se cuenta por su clave (`docs/22-calidad-de-datos.md` §5.2). En hover,
 * un acento dorado crece desde el borde izquierdo.
 */
export function OptionList<K extends string>({
  options,
  onChoose,
  disabled,
}: {
  options: { key: K; label: string }[];
  onChoose: (key: K) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col divide-y divide-edge border border-edge">
      {options.map((option, index) => (
        <button
          key={option.key}
          type="button"
          disabled={disabled}
          onClick={() => onChoose(option.key)}
          style={{ animationDelay: `${index * 40}ms` }}
          className="relative flex min-h-[52px] w-full animate-rise cursor-pointer items-center px-4 py-2 text-left text-[15px] leading-snug font-medium text-ink-2 transition-[background-color,color,padding] duration-150 ease-out-quart before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:origin-center before:scale-y-0 before:bg-gold before:transition-transform before:duration-200 enabled:hover:bg-control enabled:hover:pl-5 enabled:hover:text-gold-bright enabled:hover:before:scale-y-100 enabled:active:bg-rail disabled:cursor-default disabled:opacity-60"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
