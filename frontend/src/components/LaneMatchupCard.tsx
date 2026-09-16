/**
 * Tipo 3, variante 1v1 — enfrentamiento de línea (`docs/20-tipos-de-pregunta.md` §4.1).
 *
 * Registra al primer toque, como el tipo 1: la escala de cinco niveles es una lista de opciones,
 * no un control que haya que ajustar (`docs/30-ux-flujos.md` §10).
 *
 * Las etiquetas llegan con el nombre del campeón ya puesto —«Syndra wins hard»— y se muestran tal
 * cual: el nombre en el botón elimina el paso mental de mapear letra a retrato (CA-104), y armar
 * el texto acá rompería `docs/12-api.md` §1.1. Un nombre largo **se parte en dos líneas** y no se
 * trunca: una opción cortada no dice por quién se está votando.
 *
 * La variante 2v2, con las duplas apiladas, llega en la semana 8 junto con el tipo 4, que comparte
 * ese maquetado (§8).
 */

import type { LaneChoice, LaneMatchupQuestion } from '../api';
import { ChampionPortrait } from './ChampionPortrait';
import { QuestionPrompt } from './QuestionPrompt';

interface Props {
  question: LaneMatchupQuestion;
  helpOpen: boolean;
  onToggleHelp: () => void;
  onChoose: (choice: LaneChoice) => void;
  disabled: boolean;
}

export function LaneMatchupCard({ question, helpOpen, onToggleHelp, onChoose, disabled }: Props) {
  const [a, b] = question.sides.map((side) => side.champions[0]);

  return (
    <div className="flex flex-1 flex-col px-[22px] py-[22px]">
      <QuestionPrompt
        prompt={question.prompt}
        help={question.help}
        open={helpOpen}
        onToggle={onToggleHelp}
        size="text-[25px]"
      />

      <p className="mt-3 self-center border border-edge px-2.5 py-1 font-mono text-[11px] font-semibold tracking-[0.2em] text-gold uppercase">
        {question.context.label}
      </p>

      <div className="flex flex-1 items-center justify-center gap-4 py-3">
        {[a, b].map((champion, index) =>
          champion === undefined ? null : (
            <div key={champion.id} className="contents">
              {index === 1 && (
                <span className="font-display text-sm font-semibold tracking-[0.12em] text-faint uppercase">
                  vs
                </span>
              )}
              <div className="flex w-[112px] flex-col items-center gap-1.5">
                <ChampionPortrait champion={champion} size={64} bevel="bevel-12" />
                <span className="text-center font-display text-[15px] leading-tight font-semibold text-ink">
                  {champion.name}
                </span>
              </div>
            </div>
          ),
        )}
      </div>

      <div className="flex flex-col divide-y divide-edge border border-edge">
        {question.options.map((option) => (
          <button
            key={option.key}
            type="button"
            disabled={disabled}
            onClick={() => onChoose(option.key)}
            className="flex min-h-[52px] w-full items-center px-4 py-2 text-left text-[15px] leading-snug font-medium text-ink-2 hover:bg-control hover:text-gold-bright disabled:opacity-60"
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
