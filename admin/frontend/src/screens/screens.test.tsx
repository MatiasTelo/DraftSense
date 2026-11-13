import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';

import { mockApi, NO_PATCHES, renderInLayout, type Call } from '../test-utils';
import Connectivity from './Connectivity';
import Exports from './Exports';
import Jobs, { POLL_MS } from './Jobs';
import Overview from './Overview';
import Patches from './Patches';
import Settings from './Settings';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const CURRENT = {
  patches: [
    {
      patch_id: 1,
      version: '16.17',
      released_at: '2026-08-25',
      is_current: true,
      has_snapshot: true,
      active_honeypots: 34,
      missing: [],
    },
  ],
};

const EXPORT_DEFAULTS = {
  patch_window: '16.17',
  min_trust: 0.3,
  decay_halflife_days: 21,
  bootstrap_samples: 2000,
};

const EMPTY_EXPORTS = { enabled: true, defaults: EXPORT_DEFAULTS, exports: [], last_run: null };

const volumeDay = (date: string, n: number) => ({
  date,
  counts: {
    pairwise_dimension: n,
    peak_timing: 0,
    lane_matchup: 0,
    duo_synergy: 0,
    trait_multiselect: 0,
  },
});

const overview = (days: number) => ({
  patch: '16.17',
  timezone: 'America/Argentina/Buenos_Aires',
  today: '2026-10-21',
  today_submissions: 4,
  totals: { submissions: 12, rows: 30, aggregable_rows: 25, respondents: 3, flagged_respondents: 1 },
  connected_dimensions: 5,
  total_dimensions: 8,
  days,
  types: ['pairwise_dimension', 'peak_timing', 'lane_matchup', 'duo_synergy', 'trait_multiselect'],
  volume: [volumeDay('2026-10-20', 8), volumeDay('2026-10-21', 4)],
});

describe('Layout', () => {
  it('avisa en la franja cuando no hay parche vigente', async () => {
    mockApi({ 'GET /patches': NO_PATCHES, 'GET /exports': EMPTY_EXPORTS });
    renderInLayout(<Exports />);
    expect(await screen.findByText('Sin parche vigente')).toBeInTheDocument();
  });

  it('muestra el parche vigente', async () => {
    mockApi({ 'GET /patches': CURRENT, 'GET /exports': EMPTY_EXPORTS });
    renderInLayout(<Exports />);
    expect(await screen.findByText('16.17')).toBeInTheDocument();
  });
});

describe('Overview', () => {
  it('pide la ventana elegida y muestra los totales', async () => {
    const calls = mockApi({
      'GET /patches': CURRENT,
      'GET /overview': (call: Call) => ({ body: overview(Number(call.path.split('=')[1])) }),
    });
    renderInLayout(<Overview />);
    expect(await screen.findByText('5 de 8')).toBeInTheDocument();
    expect(screen.getByText(/30 filas · 25 agregables/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '7 días' }));
    await waitFor(() => expect(calls.some((c) => c.path === '/overview?days=7')).toBe(true));
    expect(screen.getByRole('button', { name: '7 días' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('el gráfico tiene leyenda y vista de tabla', async () => {
    mockApi({ 'GET /patches': CURRENT, 'GET /overview': overview(30) });
    renderInLayout(<Overview />);
    const legend = await screen.findByRole('list', { name: 'Leyenda' });
    expect(within(legend).getByText('Ranking por dimensión')).toBeInTheDocument();
    expect(screen.getByText('Ver como tabla')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '20/10: 8 envíos' })).toBeInTheDocument();
  });
});

describe('Connectivity', () => {
  it('dice qué falta para habilitar el tier 2', async () => {
    mockApi({
      'GET /patches': CURRENT,
      'GET /connectivity': {
        patch: '16.17',
        dimensions: [
          { code: 'engage', label: 'Engage', components: 1, largest_component: 58, pending_bridges: 0, connected: true },
          { code: 'poke', label: 'Poke', components: 3, largest_component: 50, pending_bridges: 2, connected: false },
        ],
        tier: {
          median_dn: 30,
          median_threshold: 25,
          connected: 1,
          connected_threshold: 6,
          total_dimensions: 2,
          meets_median: true,
          meets_connectivity: false,
          ready: false,
        },
      },
    });
    renderInLayout(<Connectivity />);
    expect(
      await screen.findByText(/No se cumple la condición para habilitar el tier 2: falta la conectividad/),
    ).toBeInTheDocument();
    expect(screen.getByText('partida')).toBeInTheDocument();
  });
});

describe('Exports', () => {
  it('CA-612 — genera con los valores del formulario y consulta la corrida hasta que termina', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const calls = mockApi({
      'GET /patches': CURRENT,
      'GET /exports': EMPTY_EXPORTS,
      'POST /exports': { run_id: 'r1', status: 'running' },
      'GET /exports/runs/r1': {
        run_id: 'r1',
        params: {},
        status: 'succeeded',
        started_at: '2026-10-29T12:00:00Z',
        finished_at: '2026-10-29T12:02:30Z',
        result: { files: [], responses: 120, respondents: 4, warnings: [] },
        error: null,
      },
    });
    renderInLayout(<Exports />);
    const button = await screen.findByRole('button', { name: 'Generar CSV' });
    expect(button).toBeEnabled();
    fireEvent.change(screen.getByDisplayValue('2000'), { target: { value: '500' } });
    fireEvent.click(button);

    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
    const post = calls.find((c) => c.method === 'POST');
    expect(post?.body).toEqual({ patch_window: '16.17', min_trust: 0.3, halflife: 21, bootstrap: 500 });
    expect(await screen.findByText('corriendo')).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });
    expect(await screen.findByText(/terminó bien/)).toBeInTheDocument();
  });

  it('un campo que no es un número se avisa y no lanza la corrida con el valor por defecto', async () => {
    const calls = mockApi({ 'GET /patches': CURRENT, 'GET /exports': EMPTY_EXPORTS });
    renderInLayout(<Exports />);
    const button = await screen.findByRole('button', { name: 'Generar CSV' });
    fireEvent.change(screen.getByDisplayValue('0.3'), { target: { value: '0,25' } });
    fireEvent.click(button);

    expect(await screen.findByText(/«0,25» no es un número/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('cada archivo de una corrida se descarga por su export_id', async () => {
    mockApi({
      'GET /patches': CURRENT,
      'GET /exports': {
        ...EMPTY_EXPORTS,
        exports: [
          {
            export_id: 41,
            file_name: 'peak_timing_v16.17.csv',
            file_kind: 'peak_timing',
            sha256: 'a'.repeat(64),
            row_count: 58,
            patch_window: '16.17..16.17',
            min_trust_applied: 0.3,
            created_at: '2026-10-29T12:00:00Z',
            run: '16.17..16.17_2026-10-29_1',
          },
        ],
      },
    });
    renderInLayout(<Exports />);
    const link = await screen.findByRole('link', { name: 'CSV' });
    expect(link).toHaveAttribute('href', '/api/exports/41/file');
  });
});

describe('Patches', () => {
  it('activar sin forzar muestra cada faltante del 409', async () => {
    mockApi({
      'GET /patches': CURRENT,
      'GET /seeds/files': { pick_rate: ['pick_rate_16.17.csv'], honeypots: [], ddragon_snapshot: [] },
      'POST /patches/16.20/activate': () => ({
        status: 409,
        body: {
          error: {
            code: 'patch_not_ready',
            message: 'al parche le falta algo para servirse; se puede forzar',
            details: ['el parche 16.20 no tiene snapshot de pick rate', 'el parche 16.20 no tiene honeypots activas'],
          },
        },
      }),
    });
    renderInLayout(<Patches />);
    fireEvent.change(await screen.findByLabelText(/^Versiónp. ej./), {
      target: { value: '16.20' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Activar 16.20' }));
    const dialog = screen.getByRole('dialog', { name: 'Activar 16.20' });
    expect(within(dialog).getByText(/en lugar de 16.17/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Activar' }));

    expect(await screen.findByText('el parche 16.20 no tiene honeypots activas')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('el foco del diálogo arranca en Cancelar', async () => {
    mockApi({
      'GET /patches': CURRENT,
      'GET /seeds/files': { pick_rate: [], honeypots: [], ddragon_snapshot: [] },
    });
    renderInLayout(<Patches />);
    fireEvent.change(await screen.findByLabelText(/^Versiónp. ej./), {
      target: { value: '16.20' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Activar 16.20' }));
    expect(screen.getByRole('button', { name: 'Cancelar' })).toHaveFocus();
  });

  it('los archivos del snapshot salen de infra/seeds/', async () => {
    mockApi({
      'GET /patches': CURRENT,
      'GET /seeds/files': { pick_rate: ['pick_rate_16.17.csv'], honeypots: ['honeypots_16.17.yaml'], ddragon_snapshot: [] },
    });
    renderInLayout(<Patches />);
    expect(await screen.findByRole('option', { name: 'pick_rate_16.17.csv' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'honeypots_16.17.yaml' })).toBeInTheDocument();
  });
});

describe('Settings', () => {
  const settings = {
    settings: [
      {
        key: 'sampler.epsilon',
        block: 'sampler',
        value: 1,
        updated_at: '2026-10-01T10:00:00Z',
        updated_by: 'seed',
        description: 'Probabilidad de explorar.',
      },
    ],
  };

  it('rechaza un JSON inválido antes de mandar nada', async () => {
    const calls = mockApi({ 'GET /patches': CURRENT, 'GET /settings': settings });
    renderInLayout(<Settings />);
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    fireEvent.change(screen.getByLabelText('Valor nuevo (JSON)'), { target: { value: '{nope' } });
    fireEvent.click(screen.getByRole('button', { name: 'Revisar cambio' }));
    expect(screen.getByText('No es JSON válido.')).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'PATCH')).toBe(false);
  });

  it('confirma mostrando el valor actual y el nuevo, y manda el JSON', async () => {
    const calls = mockApi({
      'GET /patches': CURRENT,
      'GET /settings': settings,
      'PATCH /settings/sampler.epsilon': { key: 'sampler.epsilon', value: 0.2, previous: 1, changed: true },
    });
    renderInLayout(<Settings />);
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    fireEvent.change(screen.getByLabelText('Valor nuevo (JSON)'), { target: { value: '0.2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Revisar cambio' }));
    const dialog = screen.getByRole('dialog', { name: 'Cambiar sampler.epsilon' });
    expect(within(dialog).getByText('Actual')).toBeInTheDocument();
    expect(within(dialog).getByText('0.2')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/a lo sumo 60 segundos/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ value: 0.2 });
  });
});

describe('Jobs', () => {
  it('deshabilita Ejecutar mientras corre y consulta el estado hasta que termina', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let status: 'running' | 'succeeded' = 'running';
    mockApi({
      'GET /patches': CURRENT,
      'GET /jobs': {
        jobs: [{ job: 'refresh_question_stats', label: 'Recalcular estadísticas de preguntas', last_run: null, last_audited_at: null }],
      },
      'POST /jobs/refresh_question_stats': { run_id: 'r1', job: 'refresh_question_stats', status: 'running' },
      'GET /jobs/refresh_question_stats/runs/r1': () => ({
        body: {
          run_id: 'r1',
          job: 'refresh_question_stats',
          params: {},
          status,
          started_at: '2026-10-21T10:00:00Z',
          finished_at: status === 'running' ? null : '2026-10-21T10:00:05Z',
          result: status === 'running' ? null : { questions: 12 },
          error: null,
        },
      }),
    });
    renderInLayout(<Jobs />);
    fireEvent.click(await screen.findByRole('button', { name: 'Ejecutar' }));
    expect(await screen.findByRole('button', { name: 'Corriendo…' })).toBeDisabled();

    status = 'succeeded';
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS + 10);
    });
    expect(await screen.findByText('terminó bien')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ejecutar' })).toBeEnabled();
  });
});
