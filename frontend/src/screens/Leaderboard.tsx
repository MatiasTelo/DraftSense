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
import { useSession } from '../store/session';

const WINDOWS: [LeaderboardWindow, string, string][] = [
  ['day', 'Today', 'today'],
  ['week', 'This week', 'this week'],
  ['all', 'All time', 'all time'],
];

export function Leaderboard() {
  const navigate = useNavigate();
  const counters = useSession((state) => state.counters);
  const [range, setRange] = useState<LeaderboardWindow>('week');
  const [table, setTable] = useState<LeaderboardResponse | null>(null);

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
  const phrase = WINDOWS.find(([value]) => value === range)?.[2] ?? '';

  return (
    <AppFrame>
      <TopBar streak={counters.current_streak} answers={counters.answers_count} />

      <main className="flex flex-1 flex-col">
        <div className="flex gap-2 px-[22px] pt-6 pb-4">
          {WINDOWS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setRange(value)}
              aria-pressed={range === value}
              className={`flex min-h-10 items-center px-3.5 font-mono text-xs tracking-[0.1em] uppercase ${
                range === value
                  ? 'bg-gold font-semibold text-surface'
                  : 'border border-edge font-medium text-label'
              }`}
            >
              {label}
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
              You&apos;re #{you.rank} {phrase}
            </p>
          )}
          <div className="mb-[22px]">
            <SecondaryButton onClick={() => navigate('/play')}>Keep playing</SecondaryButton>
          </div>
        </div>
      </main>

      <BottomNav />
    </AppFrame>
  );
}
