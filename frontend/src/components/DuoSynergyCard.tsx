/**
 * Tipo 4 — sinergia de dupla (`docs/20-tipos-de-pregunta.md` §5).
 *
 * Mismo maquetado apilado que el 2v2, con tres opciones —*Top pair*, *About the same*, *Bottom
 * pair*— y sin `vs`: las dos duplas no se enfrentan, se comparan. Registra al primer toque y las
 * opciones van en el orden en que llegan, porque el *straightlining* se cuenta por su clave
 * (`docs/22-calidad-de-datos.md` §5.2, nota del 29/10).
 */

import type { DuoChoice, DuoSynergyQuestion } from '../api';
import { DuoStack, OptionList } from './DuoStack';
import { QuestionPrompt } from './QuestionPrompt';

interface Props {
  question: DuoSynergyQuestion;
  helpOpen: boolean;
  onToggleHelp: () => void;
  onChoose: (choice: DuoChoice) => void;
  disabled: boolean;
}

export function DuoSynergyCard({ question, helpOpen, onToggleHelp, onChoose, disabled }: Props) {
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

      <div className="flex flex-1 flex-col justify-center py-3">
        <DuoStack sides={question.sides} />
      </div>

      <OptionList options={question.options} onChoose={onChoose} disabled={disabled} />
    </div>
  );
}
