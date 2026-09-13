/**
 * El enunciado y su definición a un toque.
 *
 * El texto llega **ya compuesto** desde el servidor, con los nombres de campeón sustituidos: acá
 * no se arma ningún string (`docs/12-api.md` §1.1). La definición sale de `dimensions`, no del
 * código, que es lo que permite agregar una dimensión sin desplegar (CA-601, CA-506).
 *
 * La definición no es decorativa: **es lo que hace que dos personas midan lo mismo**. El acuerdo
 * inter-anotador que se reporta en el Informe de Calidad de Datos depende de que «engage»
 * signifique lo mismo para todos. Por eso está a un toque y no escondida, y por eso tampoco está
 * siempre abierta: compite con la regla de los cinco segundos
 * (`docs/20-tipos-de-pregunta.md` §1.2).
 */

import type { Help } from '../api';

interface Props {
  prompt: string;
  subtitle?: string;
  help: Help | null;
  open: boolean;
  onToggle: () => void;
  /** 27 px en el tipo 1, 25 en los enunciados de dos líneas. */
  size?: string;
}

export function QuestionPrompt({ prompt, subtitle, help, open, onToggle, size = 'text-[27px]' }: Props) {
  return (
    <div className="flex flex-col">
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <h1 className={`font-display ${size} leading-tight font-semibold text-pretty text-ink`}>
            {prompt}
          </h1>
          {subtitle !== undefined && (
            <p className="mt-1.5 text-[13px] leading-snug text-mute-2">{subtitle}</p>
          )}
        </div>
        {help !== null && (
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            aria-label={`What ${help.label.toLowerCase()} means`}
            className={`flex size-9 shrink-0 items-center justify-center rounded-full border font-mono text-[15px] font-semibold ${
              open ? 'border-cyan text-cyan' : 'border-edge-strong text-mute'
            }`}
          >
            ?
          </button>
        )}
      </div>
      {open && help !== null && (
        <p className="mt-3.5 border-l-2 border-cyan bg-control px-4 py-3.5 text-[13px] leading-relaxed text-ink-4">
          {help.text}
        </p>
      )}
    </div>
  );
}
