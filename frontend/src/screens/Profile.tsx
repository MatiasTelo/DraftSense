/**
 * `/me` — el perfil (`docs/30-ux-flujos.md` §6).
 *
 * **Las dos rachas se muestran por separado y significan cosas distintas.** La de arriba son
 * respuestas seguidas dentro de una sesión; la de días es constancia entre sesiones. Ninguna
 * depende del contenido de las respuestas: premiar coincidir con el consenso rompería la
 * independencia entre anotadores, que es un supuesto de Bradley-Terry y del alfa de Krippendorff
 * (`docs/23-gamificacion.md` §2.3).
 *
 * **No se muestra el trust score**, ni ninguna señal derivada de él, ni el resultado de los
 * honeypots — y tampoco llegan por la API (RF-207). Exponerlo convertiría la calidad en un juego a
 * optimizar en vez de una consecuencia de responder honestamente.
 *
 * La tasa de acuerdo se muestra sin juicio, sin meta y sin barra de progreso: es un dato sobre la
 * comunidad, no una nota.
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { MeResponse, QuestionType } from '../api';
import { AppFrame } from '../components/AppFrame';
import { SecondaryButton } from '../components/Button';
import { BottomNav, TopBar } from '../components/Chrome';
import { fetchMe } from '../lib/client';
import { useSession } from '../store/session';

/** Cómo se nombra cada tipo en el perfil, en el orden de `docs/30-ux-flujos.md` §6. */
const COVERAGE: [QuestionType, string][] = [
  ['pairwise_dimension', 'Champion pairs'],
  ['peak_timing', 'Power spikes'],
  ['lane_matchup', 'Lane matchups'],
  ['duo_synergy', 'Duos'],
  ['trait_multiselect', 'Traits'],
];

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="text-center">
      <div className="font-display text-[30px] leading-none font-bold text-ink">{value}</div>
      <div className="mt-[7px] font-mono text-[10px] font-medium tracking-[0.16em] text-label uppercase">
        {label}
      </div>
    </div>
  );
}

export function Profile() {
  const navigate = useNavigate();
  const counters = useSession((state) => state.counters);
  const [me, setMe] = useState<MeResponse | null>(null);

  useEffect(() => {
    void fetchMe()
      .then(setMe)
      .catch(() => {
        /* el perfil es una rama lateral: si falla, quedan los contadores de la sesión */
      });
  }, []);

  return (
    <AppFrame>
      <TopBar streak={counters.current_streak} answers={counters.answers_count} />

      <main className="flex flex-1 flex-col gap-[22px] px-[22px] pt-[30px] pb-[22px]">
        {me?.alias !== null && me?.alias !== undefined && (
          <p className="text-center font-mono text-[15px] font-medium tracking-[0.06em] text-gold">
            {me.alias}
          </p>
        )}

        <div className="grid grid-cols-3 gap-2 border-y border-white/7 py-[18px]">
          <Stat value={me?.answers_count ?? counters.answers_count} label="answers" />
          <Stat value={me?.current_streak ?? counters.current_streak} label="streak" />
          <Stat value={me?.best_streak ?? counters.best_streak} label="best" />
        </div>

        <div className="flex items-center justify-between border border-gold/22 bg-control px-4 py-3.5">
          <span className="font-display text-base font-semibold text-gold">
            🔥 {me?.current_day_streak ?? counters.current_day_streak} days in a row
          </span>
          <span className="font-mono text-[11px] text-label">
            best: {me?.best_day_streak ?? counters.best_day_streak} days
          </span>
        </div>

        {me !== null && (
          <div className="flex flex-col gap-2.5">
            <p className="text-[15px] leading-relaxed text-ink-4">
              You agree with the community{' '}
              <span className="font-semibold text-ink">{Math.round(me.agreement_rate * 100)}%</span>{' '}
              of the time
            </p>
            <p className="text-[15px] leading-relaxed text-ink-4">
              Top{' '}
              <span className="font-semibold text-ink">
                {Math.max(1, Math.round((1 - me.rank_percentile) * 100))}%
              </span>{' '}
              of contributors
            </p>
          </div>
        )}

        <div className="flex flex-col">
          <p className="pb-2.5 font-mono text-[11px] font-medium tracking-[0.18em] text-label uppercase">
            What you&apos;ve answered
          </p>
          {COVERAGE.map(([type, label]) => (
            <div
              key={type}
              className="flex items-center justify-between border-b border-white/5 py-3 text-sm text-ink-3"
            >
              <span>{label}</span>
              <span className="font-mono text-ink">{me?.coverage[type] ?? 0}</span>
            </div>
          ))}
        </div>

        <div className="flex-1" />
        <SecondaryButton onClick={() => navigate('/play')}>Keep playing</SecondaryButton>
      </main>

      <BottomNav />
    </AppFrame>
  );
}
