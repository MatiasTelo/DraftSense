/**
 * Tipo 3 — enfrentamiento de línea (`docs/20-tipos-de-pregunta.md` §4), en sus dos variantes.
 *
 * Registra al primer toque, como el tipo 4: la escala de cinco niveles es una lista de opciones,
 * no un control que haya que ajustar (`docs/30-ux-flujos.md` §10). El tipo 1 dejó de registrar
 * así cuando pasó a ser un ranking (ADR-022).
 *
 * - **1v1**: dos retratos lado a lado. Las etiquetas llegan con el nombre del campeón ya puesto
 *   —«Syndra wins hard»— y se muestran tal cual: el nombre en el botón elimina el paso mental de
 *   mapear letra a retrato (CA-104), y armar el texto acá rompería `docs/12-api.md` §1.1. Un
 *   nombre largo **se parte en dos líneas** y no se trunca.
 * - **2v2 de bot** (semana 8): las duplas apiladas de `DuoStack`, que comparte con el tipo 4. El
 *   servidor la distingue con `context.duo_context`.
 *
 * Las opciones se dibujan en el orden en que llegan: el *straightlining* se cuenta por su clave
 * (`docs/22-calidad-de-datos.md` §5.2).
 */

import type { LaneChoice, LaneMatchupQuestion } from '../api';
import { useT } from '../store/lang';
import { ChampionPortrait } from './ChampionPortrait';
import { DuoStack, OptionList } from './DuoStack';
import { QuestionPrompt } from './QuestionPrompt';

interface Props {
  question: LaneMatchupQuestion;
  helpOpen: boolean;
  onToggleHelp: () => void;
  onChoose: (choice: LaneChoice) => void;
  disabled: boolean;
}

export function LaneMatchupCard({ question, helpOpen, onToggleHelp, onChoose, disabled }: Props) {
  const t = useT();
  const duo = question.context.duo_context !== undefined;
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

      {duo ? (
        <div className="flex flex-1 flex-col justify-center py-3">
          <DuoStack sides={question.sides} separator={t.play.versus} />
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center gap-4 py-3">
          {[a, b].map((champion, index) =>
            champion === undefined ? null : (
              <div key={champion.id} className="contents">
                {index === 1 && (
                  <span className="font-display text-sm font-semibold tracking-[0.12em] text-faint uppercase">
                    {t.play.versus}
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
      )}

      <OptionList options={question.options} onChoose={onChoose} disabled={disabled} />
    </div>
  );
}
