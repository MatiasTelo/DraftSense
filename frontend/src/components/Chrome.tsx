/**
 * Las dos barras que enmarcan `/play`, `/me` y `/leaderboard`.
 *
 * La superior lleva la racha y el contador, **y nada más**: ni tiempo, ni porcentaje, ni nivel.
 * Todo lo que se agregue ahí compite con la tarjeta (`docs/30-ux-flujos.md` §5).
 *
 * La inferior lleva tres destinos siempre visibles, sin menú desplegable: dos toques de distancia
 * a cualquier parte de la aplicación.
 */

import { NavLink } from 'react-router-dom';

const TABS = [
  { to: '/play', label: 'Play' },
  { to: '/me', label: 'Profile' },
  { to: '/leaderboard', label: 'Ranks' },
] as const;

export function TopBar({ streak, answers }: { streak: number; answers: number }) {
  return (
    <header className="flex items-center justify-between border-b border-white/7 px-5 py-4 font-mono text-[13px] font-medium text-mute">
      <span className="text-gold">🔥 {streak}</span>
      <span>{answers} answered</span>
    </header>
  );
}

export function BottomNav() {
  return (
    <nav className="grid grid-cols-3 border-t border-white/7 bg-nav">
      {TABS.map((tab) => (
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
