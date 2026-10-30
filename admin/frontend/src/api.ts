/**
 * Cliente del contrato interno del panel (`docs/24-panel-admin.md` §5).
 *
 * Es espejo de ese documento, como `frontend/src/api.ts` lo es de `12-api.md`: si cambia el
 * contrato, cambia este archivo. Sin autenticación ni cookies: el panel sólo atiende desde la
 * máquina del servidor (ADR-025).
 */

export const QUESTION_TYPES = [
  'pairwise_dimension',
  'peak_timing',
  'lane_matchup',
  'duo_synergy',
  'trait_multiselect',
] as const;
export type QuestionType = (typeof QUESTION_TYPES)[number];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: string[] = [],
    readonly field?: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  const data: unknown = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const error = (data as { error?: Partial<ApiErrorBody> } | null)?.error ?? {};
    throw new ApiError(
      response.status,
      error.code ?? 'unknown',
      error.message ?? `error ${response.status}`,
      error.details ?? [],
      error.field,
    );
  }
  return data as T;
}

interface ApiErrorBody {
  code: string;
  message: string;
  details: string[];
  field: string;
}

// ------------------------------------------------------------------------------- monitoreo

export interface Overview {
  patch: string | null;
  timezone: string;
  today: string;
  today_submissions: number;
  totals: {
    submissions: number;
    rows: number;
    aggregable_rows: number;
    respondents: number;
    flagged_respondents: number;
  };
  connected_dimensions: number;
  total_dimensions: number;
  days: number;
  types: QuestionType[];
  volume: { date: string; counts: Record<QuestionType, number> }[];
}

export interface DimensionGraph {
  code: string;
  label: string;
  components: number;
  largest_component: number;
  pending_bridges: number;
  connected: boolean;
}

export interface TierIndicators {
  median_dn: number | null;
  median_threshold: number;
  connected: number;
  connected_threshold: number;
  total_dimensions: number;
  meets_median: boolean;
  meets_connectivity: boolean;
  ready: boolean;
}

export interface Connectivity {
  patch: string | null;
  dimensions: DimensionGraph[];
  tier: TierIndicators | null;
}

export interface Coverage {
  patch: string | null;
  dimensions: { code: string; label: string }[];
  bands: { solid: number; limited: number };
  champions: {
    champion_id: number;
    name: string;
    pool_tier: number;
    roles: string[];
    counts: Record<string, number>;
    min: number;
  }[];
}

export interface FlaggedRespondent {
  respondent_id: string;
  short_id: string;
  answers_count: number;
  first_seen: string;
  last_seen: string;
}

export interface Quality {
  patch: string | null;
  min_trust: number;
  histogram: { from: number; to: number; count: number }[];
  flagged: FlaggedRespondent[];
}

export interface AuditPage {
  items: { audit_id: number; action: string; payload: unknown; created_at: string }[];
  page: number;
  page_size: number;
  total: number;
  actions: string[];
}

// ------------------------------------------------------------------------------- operación

export interface ChampionRow {
  champion_id: number;
  name: string;
  roles: string[];
  pool_tier: number;
  best_rank: number | null;
}

export interface Champions {
  patch: string | null;
  enabled_pool_tiers: number;
  champions: ChampionRow[];
}

export interface SettingRow {
  key: string;
  block: string;
  value: unknown;
  updated_at: string;
  updated_by: string | null;
  description: string;
}

export interface PatchRow {
  patch_id: number;
  version: string;
  released_at: string;
  is_current: boolean;
  has_snapshot: boolean;
  active_honeypots: number;
  missing: string[];
}

export interface SeedFiles {
  pick_rate: string[];
  honeypots: string[];
  ddragon_snapshot: string[];
}

export interface SeedResult {
  result: Record<string, unknown>;
  warnings: string[];
}

export interface Activation {
  patch_id: number;
  version: string;
  previous: string | null;
  changed: boolean;
}

export interface Exports {
  enabled: boolean;
  defaults: {
    patch_window: string | null;
    min_trust: number;
    decay_halflife_days: number | null;
    bootstrap_samples: number | null;
  };
  exports: {
    export_id: number;
    file_name: string;
    file_kind: string;
    sha256: string;
    row_count: number;
    patch_window: string;
    min_trust_applied: number;
    created_at: string;
    /** La carpeta de la corrida: la vista agrupa por esto. */
    run: string | null;
  }[];
  last_run: ExportRun | null;
}

/** Una corrida de *Generar CSV* (24 §3.9, nota del 29/10). */
export interface ExportRun {
  run_id: string;
  params: Record<string, unknown>;
  status: JobStatus;
  started_at: string;
  finished_at: string | null;
  result: {
    files: { export_id: number; file_name: string; sha256: string; row_count: number }[];
    responses: number;
    respondents: number;
    warnings: string[];
  } | null;
  error: string | null;
}

export type JobStatus = 'running' | 'succeeded' | 'failed';

export interface JobRun {
  run_id: string;
  job: string;
  params: Record<string, unknown>;
  status: JobStatus;
  started_at: string;
  finished_at: string | null;
  result: unknown;
  error: string | null;
}

export interface JobRow {
  job: string;
  label: string;
  last_run: JobRun | null;
  last_audited_at: string | null;
}

export const api = {
  overview: (days: number) => request<Overview>('GET', `/overview?days=${days}`),
  connectivity: () => request<Connectivity>('GET', '/connectivity'),
  coverage: () => request<Coverage>('GET', '/coverage'),
  quality: () => request<Quality>('GET', '/quality'),
  audit: (page: number, action: string) =>
    request<AuditPage>(
      'GET',
      `/audit?page=${page}${action ? `&action=${encodeURIComponent(action)}` : ''}`,
    ),

  flag: (respondentId: string, flagged: boolean, reason: string) =>
    request<{ respondent_id: string; is_flagged: boolean; changed: boolean }>(
      'POST',
      `/respondents/${encodeURIComponent(respondentId)}/flag`,
      { flagged, reason },
    ),
  champions: () => request<Champions>('GET', '/champions'),
  setPoolTier: (championIds: number[], poolTier: number) =>
    request<{ updated: number }>('PATCH', '/champions/pool-tier', {
      champion_ids: championIds,
      pool_tier: poolTier,
    }),
  settings: () => request<{ settings: SettingRow[] }>('GET', '/settings'),
  setSetting: (key: string, value: unknown) =>
    request<{ key: string; value: unknown; previous: unknown; changed: boolean }>(
      'PATCH',
      `/settings/${encodeURIComponent(key)}`,
      { value },
    ),

  patches: () => request<{ patches: PatchRow[] }>('GET', '/patches'),
  activate: (version: string, force: boolean) =>
    request<Activation>('POST', `/patches/${encodeURIComponent(version)}/activate`, { force }),
  seedFiles: () => request<SeedFiles>('GET', '/seeds/files'),
  seedChampions: (body: {
    version: string;
    ddragon_version: string | null;
    released_at: string | null;
    use_snapshot: boolean;
  }) => request<SeedResult>('POST', '/seeds/champions', body),
  seedPickRate: (body: {
    version: string;
    file: string;
    source: string;
    source_url: string;
    captured_at: string;
    released_at: string | null;
    notes: string | null;
  }) => request<SeedResult>('POST', '/seeds/pick-rate', body),
  seedHoneypots: (body: { version: string; file: string; force: boolean }) =>
    request<SeedResult>('POST', '/seeds/honeypots', body),

  jobs: () => request<{ jobs: JobRow[] }>('GET', '/jobs'),
  startJob: (job: string, params: Record<string, unknown>) =>
    request<{ run_id: string; job: string; status: JobStatus }>('POST', `/jobs/${job}`, {
      params,
    }),
  jobRun: (job: string, runId: string) => request<JobRun>('GET', `/jobs/${job}/runs/${runId}`),

  exports: () => request<Exports>('GET', '/exports'),
  startExport: (body: {
    patch_window: string | null;
    min_trust: number | null;
    halflife: number | null;
    bootstrap: number | null;
  }) => request<{ run_id: string; status: JobStatus }>('POST', '/exports', body),
  exportRun: (runId: string) => request<ExportRun>('GET', `/exports/runs/${runId}`),
  /** La descarga la hace el navegador con un enlace: el archivo no pasa por `request`. */
  exportFileUrl: (exportId: number) => `/api/exports/${exportId}/file`,
};
