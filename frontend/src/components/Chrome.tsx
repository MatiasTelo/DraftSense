/**
 * Las dos barras que enmarcan `/play`, `/me` y `/leaderboard`.
 *
 * La superior lleva la racha y el contador, **y nada más**: ni tiempo, ni porcentaje, ni nivel.
 * Todo lo que se agregue ahí compite con la tarjeta (`docs/30-ux-flujos.md` §5).
 *
 * La inferior lleva tres destinos siempre visibles, sin menú desplegable: dos toques de distancia
 * a cualquier parte de la aplicación.
 */

import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';

import { useT } from '../store/lang';

/**
 * `middle` es la excepción a «nada más»: el selector de idioma de `/play` (ADR-028), que va entre
 * la racha y el contador (`docs/30-ux-flujos.md` §5, nota del 29/10).
 */
export function TopBar({
  streak,
  answers,
  middle,
}: {
  streak: number;
  answers: number;
  middle?: ReactNode;
}) {
  const t = useT();
  return (
    <header className="flex items-center justify-between border-b border-white/7 px-5 py-4 font-mono text-[13px] font-medium text-mute">
      <span className="text-gold">🔥 {streak}</span>
      {middle}
      <span>{t.chrome.answered(answers)}</span>
    </header>
  );
}

export function BottomNav() {
  const t = useT();
  const tabs = [
    { to: '/play', label: t.chrome.play },
    { to: '/me', label: t.chrome.profile },
    { to: '/leaderboard', label: t.chrome.ranks },
  ];
  return (
    <nav className="grid grid-cols-3 border-t border-white/7 bg-nav">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) =>
            `py-[17px] text-center font-mono text-[11px] font-semibold tracking-[0.16em] uppercase ${
              isActive ? 'bg-gold text-surface' : 'text-label'
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
