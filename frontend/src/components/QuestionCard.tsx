/**
 * El despachador de tarjetas: una rama por tipo de pregunta.
 *
 * El `switch` **no tiene `default`**, y eso es deliberado. Con `noFallthroughCasesInSwitch` y el
 * chequeo de exhaustividad de TypeScript, sumar un sexto tipo al contrato hace fallar la
 * compilación exactamente acá, que es donde hay que tocar. Un `default` que devolviera algo
 * genérico silenciaría ese aviso y el tipo nuevo saldría a producción sin tarjeta.
 *
 * Los cuatro tipos que todavía devuelven `null` llegan en las semanas 4 y 8, en el orden de
 * `docs/20-tipos-de-pregunta.md` §8. **Hoy el servidor no puede mandarlos**: `next_batch` sólo
 * materializa `pairwise_dimension`. Cada uno se implementa completo —de la tabla a la tarjeta—
 * antes de empezar el siguiente.
 */

import type { Answer, Question } from '../api';
import { PairwiseDimensionCard } from './PairwiseDimensionCard';

interface Props {
  question: Question;
  helpOpen: boolean;
  onToggleHelp: () => void;
  onAnswer: (answer: Answer) => void;
  disabled: boolean;
}

export function QuestionCard({ question, helpOpen, onToggleHelp, onAnswer, disabled }: Props) {
  switch (question.type) {
    case 'pairwise_dimension':
      return (
        <PairwiseDimensionCard
          question={question}
          helpOpen={helpOpen}
          onToggleHelp={onToggleHelp}
          onChoose={(choice) => onAnswer({ choice })}
          disabled={disabled}
        />
      );
    case 'peak_timing':
      return null;
    case 'lane_matchup':
      return null;
    case 'duo_synergy':
      return null;
    case 'trait_multiselect':
      return null;
  }
}
