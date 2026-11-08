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
import { useT } from '../store/lang';
import { useSession } from '../store/session';

/** Los tipos en el orden de `docs/30-ux-flujos.md` §6. El nombre sale del diccionario. */
const COVERAGE: QuestionType[] = [
  'pairwise_dimension',
  'peak_timing',
  'lane_matchup',
  'duo_synergy',
  'trait_multiselect',
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
  const t = useT();

  useEffect(() => {
    void fetchMe()
      .then(setMe)
      .catch(() => {
        /* el perfil es una rama lateral: si falla, quedan los contadores de la sesión */
      });
  }, []);

  return (
    <AppFrame
      header={<TopBar streak={counters.current_streak} answers={counters.answers_count} />}
      footer={<BottomNav />}
    >

      <main className="flex flex-1 flex-col gap-[22px] px-[22px] pt-[30px] pb-[22px]">
        {me?.alias !== null && me?.alias !== undefined && (
          <p className="text-center font-mono text-[15px] font-medium tracking-[0.06em] text-gold">
            {me.alias}
          </p>
        )}

        <div className="grid grid-cols-3 gap-2 border-y border-white/7 py-[18px]">
          <Stat value={me?.answers_count ?? counters.answers_count} label={t.profile.answers} />
          <Stat value={me?.current_streak ?? counters.current_streak} label={t.profile.streak} />
          <Stat value={me?.best_streak ?? counters.best_streak} label={t.profile.best} />
        </div>

        <div className="flex items-center justify-between border border-gold/22 bg-control px-4 py-3.5">
          <span className="font-display text-base font-semibold text-gold">
            {t.profile.daysInARow(me?.current_day_streak ?? counters.current_day_streak)}
          </span>
          <span className="font-mono text-[11px] text-label">
            {t.profile.bestDays(me?.best_day_streak ?? counters.best_day_streak)}
          </span>
        </div>

        {me !== null && (
          <div className="flex flex-col gap-2.5">
            <p className="text-[15px] leading-relaxed text-ink-4">
              {t.profile.agreementBefore}{' '}
              <span className="font-semibold text-ink">{Math.round(me.agreement_rate * 100)}%</span>{' '}
              {t.profile.agreementAfter}
            </p>
            <p className="text-[15px] leading-relaxed text-ink-4">
              {t.profile.topBefore}{' '}
              <span className="font-semibold text-ink">
                {Math.max(1, Math.round((1 - me.rank_percentile) * 100))}%
              </span>{' '}
              {t.profile.topAfter}
            </p>
          </div>
        )}

        <div className="flex flex-col">
          <p className="pb-2.5 font-mono text-[11px] font-medium tracking-[0.18em] text-label uppercase">
            {t.profile.answered}
          </p>
          {COVERAGE.map((type) => (
            <div
              key={type}
              className="flex items-center justify-between border-b border-white/5 py-3 text-sm text-ink-3"
            >
              <span>{t.profile.coverage[type]}</span>
              <span className="font-mono text-ink">{me?.coverage[type] ?? 0}</span>
            </div>
          ))}
        </div>

        <div className="flex-1" />
        <SecondaryButton onClick={() => navigate('/play')}>{t.profile.keepPlaying}</SecondaryButton>
      </main>

    </AppFrame>
  );
}
