import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';

import { Layout } from './components/Layout';

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

type Handler = (call: Call) => { status?: number; body: unknown };

/**
 * Reemplaza `fetch` con respuestas por ruta: `'GET /patches'` → cuerpo. Una ruta sin handler es
 * un error del test, no un 404 silencioso.
 */
export function mockApi(routes: Record<string, unknown | Handler>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      const url = new URL(input, 'http://panel.test');
      const method = init?.method ?? 'GET';
      const path = url.pathname.replace(/^\/api/, '') + url.search;
      const call = { method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined };
      calls.push(call);
      const key = `${method} ${url.pathname.replace(/^\/api/, '')}`;
      const route = routes[`${method} ${path}`] ?? routes[key];
      if (route === undefined) throw new Error(`sin handler para ${method} ${path}`);
      const result =
        typeof route === 'function' ? (route as Handler)(call) : { status: 200, body: route };
      return new Response(JSON.stringify(result.body), { status: result.status ?? 200 });
    }),
  );
  return calls;
}

export const NO_PATCHES = { patches: [] };

export function renderInLayout(ui: ReactElement, route = '/') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Layout>{ui}</Layout>
    </MemoryRouter>,
  );
}
