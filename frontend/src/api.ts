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
  /** Las dos rachas miden cosas distintas: respuestas seguidas y dias consecutivos. */
  current_day_streak: number;
  best_day_streak: number;
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

/** Lo que devuelve `POST /sessions`. La cookie `ds_session` viaja aparte, y es HttpOnly. */
export interface SessionResponse {
  respondent_id: string;
  onboarding_seen: boolean;
  answers_count: number;
  current_streak: number;
  best_streak: number;
  current_day_streak: number;
  best_day_streak: number;
}

/** Los tres campos son opcionales: `null` significa que prefirio no decir. */
export interface OnboardingRequest {
  declared_rank: string | null;
  declared_main_role: string | null;
  declared_hours_bucket: string | null;
}

export interface QuestionBatch {
  questions: Question[];
}

export interface ResponseRequest {
  question_id: number;
  answer: Answer;
  response_time_ms: number;
}

export interface MeResponse {
  answers_count: number;
  current_streak: number;
  best_streak: number;
  current_day_streak: number;
  best_day_streak: number;
  agreement_rate: number;
  /** Un conteo por cada uno de los cinco tipos; los que no tienen respuestas van en 0. */
  coverage: Record<QuestionType, number>;
  rank_percentile: number;
  alias: string | null;
}

export interface LeaderboardEntry {
  rank: number;
  alias: string | null;
  answers_count: number;
  is_you: boolean;
}

export interface LeaderboardResponse {
  window: LeaderboardWindow;
  generated_at: string;
  entries: LeaderboardEntry[];
}

export type LeaderboardWindow = 'day' | 'week' | 'all';

/**
 * El sobre uniforme de error del servidor. **Toda** respuesta de error tiene esta forma, asi que
 * el cliente puede ramificar por `code` y no por el status HTTP.
 */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    field?: string;
  };
}

export const API_BASE = '/api/v1';
