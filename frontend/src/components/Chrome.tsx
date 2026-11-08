/**
 * Las dos barras que enmarcan `/play`, `/me` y `/leaderboard`.
 *
 * La superior lleva la racha y el contador, **y nada más**: ni tiempo, ni porcentaje, ni nivel.
 * Todo lo que se agregue ahí compite con la tarjeta (`docs/30-ux-flujos.md` §5). En escritorio
 * (ADR-031) suma la marca y los tres destinos, que en celular viven en la barra inferior: la
 * navegación no se agrega, se muda.
 *
 * La inferior lleva tres destinos siempre visibles, sin menú desplegable: dos toques de distancia
 * a cualquier parte de la aplicación. En escritorio no se muestra. Las dos navegaciones existen en
 * el DOM, pero la que no corresponde está en `display: none` y el lector de pantalla encuentra una.
 */

import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';

import { useT } from '../store/lang';

function useTabs() {
  const t = useT();
  return [
    { to: '/play', label: t.chrome.play },
    { to: '/me', label: t.chrome.profile },
    { to: '/leaderboard', label: t.chrome.ranks },
  ];
}

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
  const tabs = useTabs();
  return (
    <header className="flex items-center justify-between gap-6 border-b border-white/7 px-5 py-4 font-mono text-[13px] font-medium text-mute lg:mx-auto lg:max-w-[1120px] lg:justify-start lg:border-b-0 lg:px-8 lg:py-0">
      {/* La marca sólo en escritorio: es el mismo literal que el landing, que no se traduce. */}
      <span className="hidden font-display text-[17px] font-bold tracking-[0.14em] text-ink uppercase lg:inline">
        Draftsense
      </span>
      <span className="hidden h-5 w-px bg-edge-strong lg:block" />

      <span className="text-gold">🔥 {streak}</span>
      {middle}
      <span>{t.chrome.answered(answers)}</span>

      <nav className="ml-auto hidden self-stretch lg:flex">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              // El subrayado dorado crece desde el centro: marca el destino actual y responde al
              // puntero sin mover nada de lugar.
              `group relative flex min-h-14 items-center px-4 font-mono text-[11px] font-semibold tracking-[0.16em] uppercase transition-colors duration-150 ${
                isActive ? 'text-gold' : 'text-label hover:text-ink-3'
              }`
            }
          >
            {({ isActive }) => (
              <>
                {tab.label}
                <span
                  aria-hidden="true"
                  className={`absolute inset-x-3 bottom-0 h-0.5 bg-gold transition-transform duration-200 ease-out-quart ${
                    isActive ? 'scale-x-100' : 'scale-x-0 group-hover:scale-x-50'
                  }`}
                />
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}

export function BottomNav() {
  const tabs = useTabs();
  return (
    <nav className="grid grid-cols-3 border-t border-white/7 bg-nav">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) =>
            `py-[17px] text-center font-mono text-[11px] font-semibold tracking-[0.16em] uppercase transition-colors duration-150 ${
              isActive ? 'bg-gold text-surface' : 'text-label hover:bg-control hover:text-ink-3 active:bg-rail'
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
