/** Datos de prueba compartidos, con la forma exacta que devuelve la API. */

import type {
  ChampionRef,
  DuoSynergyQuestion,
  LaneMatchupQuestion,
  PairwiseDimensionQuestion,
  PeakTimingQuestion,
  TraitMultiselectQuestion,
} from './api';

export function champion(id: number, name: string): ChampionRef {
  return {
    id,
    key: name,
    name,
    image_url: `https://ddragon.leagueoflegends.com/cdn/16.20.1/img/champion/${name}.png`,
  };
}

/** Un ranking del tipo 1 (ADR-022): cinco campeones, `a` y `b` primero, en el orden servido. */
export function pairwise(question_id: number, a = 'Alistar', b = 'Yasuo'): PairwiseDimensionQuestion {
  return {
    question_id,
    ranking_id: 5000 + question_id,
    type: 'pairwise_dimension',
    prompt: 'Who has more engage?',
    instruction: 'Drag to order: most at the top.',
    help: { label: 'Engage', text: 'Starting fights on your terms.' },
    champions: [
      champion(12, a),
      champion(157, b),
      champion(89, 'Leona'),
      champion(24, 'Jax'),
      champion(99, 'Lux'),
    ],
    unknown_label: 'Not sure',
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

/** Tipo 3, variante 2v2 de bot — `docs/12-api.md` §2.3. Cada lado en orden adc, support. */
export function botLane(question_id: number): LaneMatchupQuestion {
  return {
    question_id,
    type: 'lane_matchup',
    prompt: 'Which bot lane wins at 10 minutes?',
    help: {
      label: 'Bot lane matchup',
      text: "Which pair beats the other in lane. Not about how well each pair works together — that's a different question.",
    },
    context: { duo_context: 'bot', label: 'BOT' },
    sides: [
      { key: 'a', champions: [champion(51, 'Caitlyn'), champion(99, 'Lux')] },
      { key: 'b', champions: [champion(360, 'Samira'), champion(111, 'Nautilus')] },
    ],
    options: [
      { key: 'a_strong', label: 'Top pair wins hard' },
      { key: 'a_slight', label: 'Top pair wins slightly' },
      { key: 'even', label: 'Even' },
      { key: 'b_slight', label: 'Bottom pair wins slightly' },
      { key: 'b_strong', label: 'Bottom pair wins hard' },
    ],
  };
}

/** Tipo 4 — `docs/12-api.md` §2.3. */
export function duoSynergy(question_id: number): DuoSynergyQuestion {
  return {
    question_id,
    type: 'duo_synergy',
    prompt: 'Which duo works better together?',
    help: {
      label: 'Synergy',
      text: "Ignore who they're up against. Which two complement each other better?",
    },
    context: { duo_context: 'mid_jungle', label: 'MID + JUNGLE' },
    sides: [
      { key: 'pair_1', champions: [champion(61, 'Orianna'), champion(59, 'Jarvan IV')] },
      { key: 'pair_2', champions: [champion(4, 'Twisted Fate'), champion(120, 'Hecarim')] },
    ],
    options: [
      { key: 'pair_1', label: 'Top pair' },
      { key: 'similar', label: 'About the same' },
      { key: 'pair_2', label: 'Bottom pair' },
    ],
  };
}

/** Tipo 5 — `docs/12-api.md` §2.3, con los siete atributos de `20-tipos-de-pregunta.md` §6. */
export function traitMultiselect(question_id: number, name = 'Sett'): TraitMultiselectQuestion {
  return {
    question_id,
    type: 'trait_multiselect',
    prompt: `What does ${name} do well?`,
    subtitle: 'Pick all that apply.',
    help: null,
    subject: { champions: [champion(875, name)] },
    traits: [
      { code: 'engage', label: 'Engage', help: 'Starts fights on their own terms.' },
      { code: 'poke', label: 'Poke', help: 'Wears enemies down from range.' },
      { code: 'pick', label: 'Pick', help: 'Catches out and kills isolated targets.' },
      { code: 'peel', label: 'Peel', help: 'Keeps divers off their carries.' },
      { code: 'front_to_back', label: 'Front to back', help: 'Wants a straight teamfight, tanks in front.' },
      { code: 'dive', label: 'Dive', help: 'Jumps past the front line onto the back line.' },
      { code: 'split_push', label: 'Split push', help: 'Pressures a side lane instead of grouping.' },
    ],
  };
}
