/**
 * El retrato de un campeón, con su caída.
 *
 * Los íconos se cargan bajo demanda del CDN de Riot y no se empaquetan: son la única dependencia
 * externa del sistema en tiempo de ejecución. Cuando Data Dragon no responde, el retrato cae a un
 * marcador con las iniciales en vez de dejar un hueco (`docs/10-arquitectura.md` §7) — la tarjeta
 * sigue siendo respondible, porque debajo va el nombre.
 *
 * El `alt` lleva el nombre del campeón, no «retrato de»: es lo que la persona necesita oír (§9).
 */

import { useState } from 'react';

import type { ChampionRef } from '../api';

interface Props {
  champion: ChampionRef;
  /** Lado del retrato en píxeles. 130 en la tarjeta del tipo 1. */
  size: number;
  bevel: 'bevel-12' | 'bevel-14';
}

function initials(name: string): string {
  return name
    .split(/[\s'.]+/u)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join('');
}

export function ChampionPortrait({ champion, size, bevel }: Props) {
  const [failed, setFailed] = useState(false);
  const box = { width: size, height: size };

  if (failed) {
    return (
      <div
        role="img"
        aria-label={champion.name}
        style={box}
        className={`portrait-hatch ${bevel} flex items-center justify-center border border-edge font-display text-2xl text-mute`}
      >
        {initials(champion.name)}
      </div>
    );
  }

  return (
    <img
      src={champion.image_url}
      alt={champion.name}
      style={box}
      onError={() => setFailed(true)}
      className={`${bevel} border border-edge object-cover`}
    />
  );
}
