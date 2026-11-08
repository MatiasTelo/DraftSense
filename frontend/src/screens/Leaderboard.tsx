/**
 * `/leaderboard` — la tabla de posiciones (`docs/30-ux-flujos.md` §7).
 *
 * **Ordena por cantidad de respuestas, no por acuerdo ni por precisión.** Premiar el acuerdo
 * empujaría a responder lo que se cree popular en vez de lo que se cree cierto, que es exactamente
 * el sesgo que arruinaría los datos (`docs/23-gamificacion.md` §5).
 *
 * El alias nunca es un identificador real y no se deriva del `respondent_id` ni de la huella
 * (CA-312). Quién queda afuera de la tabla lo decide el servidor, y el cliente no tiene forma de
 * saberlo: el filtro por confianza de ADR-014 no se observa desde acá.
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { LeaderboardResponse, LeaderboardWindow } from '../api';
import { AppFrame } from '../components/AppFrame';
import { SecondaryButton } from '../components/Button';
import { BottomNav, TopBar } from '../components/Chrome';
import { fetchLeaderboard } from '../lib/client';
import { useT } from '../store/lang';
import { useSession } from '../store/session';

const WINDOWS: LeaderboardWindow[] = ['day', 'week', 'all'];

export function Leaderboard() {
  const navigate = useNavigate();
  const counters = useSession((state) => state.counters);
  const [range, setRange] = useState<LeaderboardWindow>('week');
  const [table, setTable] = useState<LeaderboardResponse | null>(null);
  const t = useT();

  useEffect(() => {
    let current = true;
    void fetchLeaderboard(range)
      .then((data) => {
        if (current) setTable(data);
      })
      .catch(() => {
        /* rama lateral: sin tabla no se rompe nada del camino principal */
      });
    return () => {
      current = false;
    };
  }, [range]);

  const you = table?.entries.find((entry) => entry.is_you);
  const phrase = t.leaderboard.phrases[range];

  return (
    <AppFrame
      header={<TopBar streak={counters.current_streak} answers={counters.answers_count} />}
      footer={<BottomNav />}
    >

      <main className="flex flex-1 flex-col">
        <div className="flex gap-2 px-[22px] pt-6 pb-4">
          {WINDOWS.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setRange(value)}
              aria-pressed={range === value}
              className={`flex min-h-11 cursor-pointer items-center px-3.5 font-mono text-xs tracking-[0.1em] uppercase transition-[background-color,border-color,color,transform,scale] duration-150 ease-out-quart active:scale-[0.96] ${
                range === value
                  ? 'bg-gold font-semibold text-surface'
                  : 'border border-edge font-medium text-label hover:border-edge-strong hover:text-ink-3'
              }`}
            >
              {t.leaderboard.windows[value]}
            </button>
          ))}
        </div>

        <div className="flex flex-1 flex-col px-[22px]">
          {table?.entries.map((entry) =>
            entry.is_you ? (
              <div
                key={entry.rank}
                className="-mx-3 flex items-center gap-3.5 border-l-2 border-gold bg-gold/10 px-3 py-3.5"
              >
                <span className="w-6 font-mono text-sm font-semibold text-gold">{entry.rank}</span>
                <span className="flex-1 font-mono text-sm font-medium text-gold-bright">
                  {entry.alias}
                </span>
                <span className="font-mono text-sm font-semibold text-gold-bright">
                  {entry.answers_count}
                </span>
              </div>
            ) : (
              <div
                key={entry.rank}
                className="flex items-center gap-3.5 border-b border-white/5 py-3.5"
              >
                <span className="w-6 font-mono text-sm font-semibold text-label">{entry.rank}</span>
                <span className="flex-1 font-mono text-sm text-ink-3">{entry.alias}</span>
                <span className="font-mono text-sm font-semibold text-ink-4">
                  {entry.answers_count}
                </span>
              </div>
            ),
          )}

          <div className="flex-1" />

          {you !== undefined && (
            <p className="pt-[18px] pb-2 font-display text-[17px] font-semibold text-ink">
              {t.leaderboard.you(you.rank, phrase)}
            </p>
          )}
          <div className="mb-[22px]">
            <SecondaryButton onClick={() => navigate('/play')}>{t.leaderboard.keepPlaying}</SecondaryButton>
          </div>
        </div>
      </main>

    </AppFrame>
  );
}
