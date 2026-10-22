import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { NavLink } from 'react-router-dom';

import { api } from '../api';
import { formatTime } from '../lib/format';
import { RefreshContext } from '../lib/resource';

/** Las vistas, en el orden de 24 §2: lo diario arriba, lo de una vez por parche abajo. */
export const VIEWS = [
  { path: '/', label: 'Resumen' },
  { path: '/conectividad', label: 'Conectividad y tier' },
  { path: '/cobertura', label: 'Cobertura' },
  { path: '/calidad', label: 'Calidad' },
  { path: '/pool', label: 'Pool' },
  { path: '/parametros', label: 'Parámetros' },
  { path: '/jobs', label: 'Jobs' },
  { path: '/parches', label: 'Parches y seeds' },
  { path: '/exportaciones', label: 'Exportaciones' },
  { path: '/auditoria', label: 'Auditoría' },
] as const;

function CurrentPatch({ tick }: { tick: number }) {
  const [state, setState] = useState<{ version: string | null; failed: boolean } | null>(null);
  useEffect(() => {
    let alive = true;
    api.patches().then(
      ({ patches }) =>
        alive &&
        setState({ version: patches.find((p) => p.is_current)?.version ?? null, failed: false }),
      () => alive && setState({ version: null, failed: true }),
    );
    return () => {
      alive = false;
    };
  }, [tick]);

  if (state === null) return <span className="text-mute">Parche vigente: …</span>;
  if (state.failed) return <span className="text-series-2">No se pudo leer la base</span>;
  if (state.version === null)
    return <span className="font-semibold text-series-2">Sin parche vigente</span>;
  return (
    <span className="text-ink-3">
      Parche vigente: <strong className="font-mono text-gold">{state.version}</strong>
    </span>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const [tick, setTick] = useState(0);
  const [loadedAt, setLoadedAt] = useState(() => new Date());
  const [menuOpen, setMenuOpen] = useState(false);
  const refresh = useCallback(() => {
    setTick((t) => t + 1);
    setLoadedAt(new Date());
  }, []);

  return (
    <RefreshContext.Provider value={{ tick, refresh }}>
      <div className="min-h-screen md:flex">
        <aside className="border-b border-edge bg-nav md:min-h-screen md:w-60 md:shrink-0 md:border-b-0 md:border-r">
          <div className="flex items-center justify-between px-5 py-4">
            <div>
              <div className="font-display text-lg font-bold text-gold">DraftSense</div>
              <div className="text-xs uppercase tracking-[0.18em] text-label">Administración</div>
            </div>
            <button
              type="button"
              className="min-h-11 px-3 text-sm text-ink-3 md:hidden"
              aria-expanded={menuOpen}
              aria-controls="admin-nav"
              onClick={() => setMenuOpen((open) => !open)}
            >
              Menú
            </button>
          </div>
          <nav
            id="admin-nav"
            aria-label="Vistas del panel"
            className={`${menuOpen ? 'block' : 'hidden'} pb-4 md:block`}
          >
            <ul>
              {VIEWS.map((view) => (
                <li key={view.path}>
                  <NavLink
                    to={view.path}
                    end={view.path === '/'}
                    onClick={() => setMenuOpen(false)}
                    className={({ isActive }) =>
                      `flex min-h-11 items-center px-5 text-sm ${
                        isActive ? 'bg-panel font-semibold text-gold' : 'text-ink-4 hover:text-ink'
                      }`
                    }
                  >
                    {view.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </aside>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-edge bg-surface px-6 py-3 text-sm">
            <CurrentPatch tick={tick} />
            <div className="flex items-center gap-3 text-mute">
              <span>Datos de las {formatTime(loadedAt)}</span>
              <button
                type="button"
                onClick={refresh}
                className="bevel-8 min-h-11 border border-edge-strong px-4 font-semibold text-ink-2 hover:bg-rail"
              >
                Actualizar
              </button>
            </div>
          </div>
          <main className="mx-auto max-w-6xl px-4 py-6 md:px-6">{children}</main>
        </div>
      </div>
    </RefreshContext.Provider>
  );
}
