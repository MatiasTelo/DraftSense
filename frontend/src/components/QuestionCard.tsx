/**
 * El despachador de tarjetas: una rama por tipo de pregunta.
 *
 * El `switch` **no tiene `default`**, y eso es deliberado. Con `noFallthroughCasesInSwitch` y el
 * chequeo de exhaustividad de TypeScript, sumar un sexto tipo al contrato hace fallar la
 * compilación exactamente acá, que es donde hay que tocar. Un `default` que devolviera algo
 * genérico silenciaría ese aviso y el tipo nuevo saldría a producción sin tarjeta.
 *
 * Desde la semana 8 están los cinco: el tipo 1 es un ranking de cinco (ADR-022), el 3 tiene la
 * variante 1v1 y la 2v2 de bot en la misma tarjeta, el 4 son duplas apiladas y el 5 una grilla de
 * atributos con confirmación.
 */

import type { Answer, Question } from '../api';
import { DimensionRankingCard } from './DimensionRankingCard';
import { DuoSynergyCard } from './DuoSynergyCard';
import { LaneMatchupCard } from './LaneMatchupCard';
import { PeakTimingCard } from './PeakTimingCard';
import { TraitMultiselectCard } from './TraitMultiselectCard';

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
        <DimensionRankingCard
          question={question}
          helpOpen={helpOpen}
          onToggleHelp={onToggleHelp}
          onAnswer={onAnswer}
          disabled={disabled}
        />
      );
    case 'peak_timing':
      return (
        <PeakTimingCard
          question={question}
          helpOpen={helpOpen}
          onToggleHelp={onToggleHelp}
          onConfirm={(minute) => onAnswer({ minute })}
          disabled={disabled}
        />
      );
    case 'lane_matchup':
      return (
        <LaneMatchupCard
          question={question}
          helpOpen={helpOpen}
          onToggleHelp={onToggleHelp}
          onChoose={(choice) => onAnswer({ choice })}
          disabled={disabled}
        />
      );
    case 'duo_synergy':
      return (
        <DuoSynergyCard
          question={question}
          helpOpen={helpOpen}
          onToggleHelp={onToggleHelp}
          onChoose={(choice) => onAnswer({ choice })}
          disabled={disabled}
        />
      );
    case 'trait_multiselect':
      return (
        <TraitMultiselectCard
          question={question}
          onConfirm={(traits) => onAnswer({ traits })}
          disabled={disabled}
        />
      );
  }
}
