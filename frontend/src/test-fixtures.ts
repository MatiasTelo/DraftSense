/** Datos de prueba compartidos, con la forma exacta que devuelve la API. */

import type {
  ChampionRef,
  LaneMatchupQuestion,
  PairwiseDimensionQuestion,
  PeakTimingQuestion,
} from './api';

export function champion(id: number, name: string): ChampionRef {
  return {
    id,
    key: name,
    name,
    image_url: `https://ddragon.leagueoflegends.com/cdn/16.20.1/img/champion/${name}.png`,
  };
}

export function pairwise(question_id: number, a = 'Alistar', b = 'Yasuo'): PairwiseDimensionQuestion {
  return {
    question_id,
    type: 'pairwise_dimension',
    prompt: 'Who has more engage?',
    help: { label: 'Engage', text: 'Starting fights on your terms.' },
    options: [
      { key: 'a', champions: [champion(12, a)] },
      { key: 'b', champions: [champion(157, b)] },
      { key: 'unknown', label: 'Not sure', champions: [] },
    ],
  };
}

export function peakTiming(question_id: number, name = 'Kayle'): PeakTimingQuestion {
  return {
    question_id,
    type: 'peak_timing',
    prompt: `When does ${name} peak?`,
    help: {
      label: 'Power spike',
      text: 'The point in the game where this champion is at their strongest compared to everyone else.',
    },
    subject: { champions: [champion(10, name)] },
    slider: {
      min: 0,
      max: 40,
      step: 1,
      default: 20,
      unit: 'min',
      marks: [
        { at: 0, label: 'laning' },
        { at: 15, label: 'mid game' },
        { at: 30, label: 'late game' },
      ],
    },
  };
}

export function laneMatchup(
  question_id: number,
  a = 'Syndra',
  b = 'Zed',
  role = 'mid',
): LaneMatchupQuestion {
  return {
    question_id,
    type: 'lane_matchup',
    prompt: 'Who wins this lane at 10 minutes?',
    help: { label: 'Lane matchup', text: 'Assume equal skill and no jungle interference.' },
    context: { role, label: role.toUpperCase() },
    sides: [
      { key: 'a', champions: [champion(134, a)] },
      { key: 'b', champions: [champion(238, b)] },
    ],
    options: [
      { key: 'a_strong', label: `${a} wins hard` },
      { key: 'a_slight', label: `${a} wins slightly` },
      { key: 'even', label: 'Even' },
      { key: 'b_slight', label: `${b} wins slightly` },
      { key: 'b_strong', label: `${b} wins hard` },
    ],
  };
}
