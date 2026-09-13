/**
 * Tipo 1 — comparación pareada por dimensión (`docs/20-tipos-de-pregunta.md` §2).
 *
 * Es el 50 % de la sesión y la fuente de 56 de las 126 columnas de `champion_features.csv`.
 *
 * **Registra al primer toque, sin botón de confirmar**: con cinco a diez segundos por tarjeta, un
 * paso de confirmación cuesta respuestas y no evita ningún error, porque no hay respuesta
 * incorrecta que corregir (`docs/30-ux-flujos.md` §10).
 *
 * `Not sure` es una opción explícita y no la ausencia de respuesta: su tasa por campeón se exporta
 * como `D_unknown_rate` y dice que la dimensión no aplica bien a ese campeón. Por eso ocupa lugar
 * en la tarjeta en vez de resolverse salteando.
 */

import type { PairwiseDimensionQuestion, Side } from '../api';
import { ChampionPortrait } from './ChampionPortrait';
import { QuestionPrompt } from './QuestionPrompt';

export type PairwiseChoice = 'a' | 'b' | 'unknown';

interface Props {
  question: PairwiseDimensionQuestion;
  helpOpen: boolean;
  onToggleHelp: () => void;
  onChoose: (choice: PairwiseChoice) => void;
  disabled: boolean;
}

function side(question: PairwiseDimensionQuestion, key: string): Side | undefined {
  return question.options.find((option) => option.key === key);
}

export function PairwiseDimensionCard({
  question,
  helpOpen,
  onToggleHelp,
  onChoose,
  disabled,
}: Props) {
  const a = side(question, 'a')?.champions[0];
  const b = side(question, 'b')?.champions[0];
  const unknown = side(question, 'unknown');

  return (
    <div className="flex flex-1 flex-col px-[22px] py-[30px]">
      <QuestionPrompt
        prompt={question.prompt}
        help={question.help}
        open={helpOpen}
        onToggle={onToggleHelp}
      />

      <div className="flex flex-1 items-center gap-3.5 py-6">
        {[a, b].map((champion, index) => {
          if (champion === undefined) return null;
          const choice: PairwiseChoice = index === 0 ? 'a' : 'b';
          return (
            <button
              key={champion.id}
              type="button"
              disabled={disabled}
              onClick={() => onChoose(choice)}
              className="group flex flex-1 flex-col items-center gap-3 disabled:opacity-60"
            >
              <span className="block transition-[filter] group-hover:brightness-110">
                <ChampionPortrait champion={champion} size={130} bevel="bevel-14" />
              </span>
              <span className="font-display text-lg font-semibold tracking-[0.04em] text-ink group-hover:text-gold-bright">
                {champion.name}
              </span>
            </button>
          );
        })}
      </div>

      {unknown !== undefined && (
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChoose('unknown')}
          className="flex h-12 w-full items-center justify-center border border-white/12 text-[13px] font-medium tracking-[0.04em] text-mute hover:text-ink-3 disabled:opacity-60"
        >
          {unknown.label ?? 'Not sure'}
        </button>
      )}
    </div>
  );
}
