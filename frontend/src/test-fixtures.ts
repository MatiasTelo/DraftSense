/** Datos de prueba compartidos, con la forma exacta que devuelve la API. */

import type { ChampionRef, PairwiseDimensionQuestion } from './api';

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
