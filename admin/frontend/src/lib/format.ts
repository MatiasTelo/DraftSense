import type { QuestionType } from '../api';

/** Los nombres de los cinco tipos, como los nombra la documentación. */
export const TYPE_LABELS: Record<QuestionType, string> = {
  pairwise_dimension: 'Ranking por dimensión',
  peak_timing: 'Pico de poder',
  lane_matchup: 'Enfrentamiento de línea',
  duo_synergy: 'Sinergia de dupla',
  trait_multiselect: 'Atributos',
};

/** Un color por tipo, fijo y en el orden de `QuestionType` (tokens `series-*`). */
export const TYPE_COLORS: Record<QuestionType, string> = {
  pairwise_dimension: 'bg-series-1',
  peak_timing: 'bg-series-2',
  lane_matchup: 'bg-series-3',
  duo_synergy: 'bg-series-4',
  trait_multiselect: 'bg-series-5',
};

const dateTime = new Intl.DateTimeFormat('es-AR', { dateStyle: 'short', timeStyle: 'short' });
const time = new Intl.DateTimeFormat('es-AR', { timeStyle: 'short' });
const number = new Intl.NumberFormat('es-AR');

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTime.format(new Date(value)) : '—';
}

export function formatTime(value: Date): string {
  return time.format(value);
}

export function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : number.format(value);
}

/** `2026-10-21` → `21/10`. Sin `Date`: la fecha ya viene en la zona del panel. */
export function shortDate(iso: string): string {
  const [, month, day] = iso.split('-');
  return `${day}/${month}`;
}
