import { createContext, useCallback, useContext, useEffect, useState } from 'react';

/**
 * La franja de arriba tiene un solo botón *Actualizar* para todas las vistas (24 §2): las vistas
 * no se refrescan solas. El botón sube este contador y cada vista lo usa como dependencia.
 */
export const RefreshContext = createContext<{ tick: number; refresh: () => void }>({
  tick: 0,
  refresh: () => {},
});

export function useRefresh() {
  return useContext(RefreshContext);
}

export interface Resource<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

/** Carga `load` al montar, al cambiar `deps` y con cada *Actualizar* de la franja. */
export function useResource<T>(load: () => Promise<T>, deps: unknown[] = []): Resource<T> {
  const { tick } = useRefresh();
  const [local, setLocal] = useState(0);
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    load().then(
      (data) => alive && setState({ data, error: null, loading: false }),
      (error: unknown) =>
        alive &&
        setState({
          data: null,
          error: error instanceof Error ? error : new Error(String(error)),
          loading: false,
        }),
    );
    return () => {
      alive = false;
    };
    // `load` cambia en cada render; lo que decide recargar son `deps`, el tick y `local`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, local, ...deps]);

  const reload = useCallback(() => setLocal((n) => n + 1), []);
  return { ...state, reload };
}
