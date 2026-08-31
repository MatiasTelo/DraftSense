/**
 * Tipos del contrato con la API, según `docs/12-api.md`.
 *
 * La pregunta es una union discriminada por `type`: el servidor manda el enunciado ya compuesto,
 * con los nombres de campeón sustituidos, y el cliente sólo lo muestra.
 */

export type QuestionType =
  | 'pairwise_dimension'
  | 'peak_timing'
  | 'lane_matchup'
  | 'duo_synergy'
  | 'trait_multiselect';

export interface ChampionRef {
  id: number;
  key: string;
  name: string;
  image_url: string;
}

export interface Help {
  label: string;
  text: string;
}

/** Toda opción que representa una entidad comparable lleva un arreglo, tenga 1 o 2 campeones. */
export interface Side {
  key: string;
  label?: string;
  champions: ChampionRef[];
}

interface QuestionBase {
  question_id: number;
  prompt: string;
  help: Help | null;
}

export interface PairwiseDimensionQuestion extends QuestionBase {
  type: 'pairwise_dimension';
  options: Side[];
}

export interface PeakTimingQuestion extends QuestionBase {
  type: 'peak_timing';
  subject: { champions: ChampionRef[] };
  slider: {
    min: number;
    max: number;
    step: number;
    default: number;
    unit: string;
    marks: { at: number; label: string }[];
  };
}

export interface LaneMatchupQuestion extends QuestionBase {
  type: 'lane_matchup';
  context: { role?: string; duo_context?: string; label: string };
  sides: Side[];
  options: { key: string; label: string }[];
}

export interface DuoSynergyQuestion extends QuestionBase {
  type: 'duo_synergy';
  context: { duo_context: string; label: string };
  sides: Side[];
  options: { key: string; label: string }[];
}

export interface TraitMultiselectQuestion extends QuestionBase {
  type: 'trait_multiselect';
  subtitle: string;
  subject: { champions: ChampionRef[] };
  traits: { code: string; label: string; help: string }[];
}

export type Question =
  | PairwiseDimensionQuestion
  | PeakTimingQuestion
  | LaneMatchupQuestion
  | DuoSynergyQuestion
  | TraitMultiselectQuestion;

export type Answer =
  | { choice: 'a' | 'b' | 'unknown' }
  | { minute: number }
  | { choice: 'a_strong' | 'a_slight' | 'even' | 'b_slight' | 'b_strong' }
  | { choice: 'pair_1' | 'pair_2' | 'similar' }
  | { traits: string[] };

export interface Progress {
  answers_count: number;
  current_streak: number;
  best_streak: number;
  agreement_rate: number;
}

export interface Feedback {
  consensus?: Record<string, number>;
  consensus_median?: number;
  your_answer?: number;
  agreed_with_majority?: boolean;
  sample_size: number;
}

export interface RecordedResponse {
  recorded: true;
  /** Ausente mientras la pregunta tiene menos de 20 respuestas. */
  feedback: Feedback | null;
  progress: Progress;
}

export const API_BASE = '/api/v1';
