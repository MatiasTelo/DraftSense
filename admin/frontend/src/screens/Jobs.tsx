import { useEffect, useRef, useState } from 'react';

import { api, type JobRow, type JobRun } from '../api';
import { Button, ErrorBox, Field, inputClass, Loading, Page, Panel } from '../components/ui';
import { formatDateTime } from '../lib/format';
import { useResource } from '../lib/resource';

/** Cada cuánto se consulta una corrida en curso (24 §3.7). */
export const POLL_MS = 2000;

const STATUS: Record<JobRun['status'], { label: string; className: string }> = {
  running: { label: 'corriendo', className: 'text-cyan' },
  succeeded: { label: 'terminó bien', className: 'text-green' },
  failed: { label: 'falló', className: 'text-series-2' },
};

function JobCard({ row, onFinished }: { row: JobRow; onFinished: () => void }) {
  const [run, setRun] = useState<JobRun | null>(row.last_run);
  const [error, setError] = useState<Error | null>(null);
  const [sinceHours, setSinceHours] = useState('24');
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => setRun(row.last_run), [row.last_run]);

  useEffect(() => {
    if (run?.status !== 'running') return;
    timer.current = window.setTimeout(async () => {
      try {
        const next = await api.jobRun(row.job, run.run_id);
        setRun(next);
        if (next.status !== 'running') onFinished();
      } catch (e) {
        // Igual que en Exportaciones: si la corrida ya no existe (el panel se reinició), dejarla
        // en `running` deshabilita el botón hasta recargar la página.
        setError(e as Error);
        setRun(null);
        onFinished();
      }
    }, POLL_MS);
    return () => window.clearTimeout(timer.current);
  }, [run, row.job, onFinished]);

  async function start() {
    setError(null);
    const params =
      row.job === 'detect_degenerate_patterns' ? { since_hours: Number(sinceHours) } : {};
    try {
      const started = await api.startJob(row.job, params);
      setRun({
        run_id: started.run_id,
        job: started.job,
        params,
        status: started.status,
        started_at: new Date().toISOString(),
        finished_at: null,
        result: null,
        error: null,
      });
    } catch (e) {
      setError(e as Error);
    }
  }

  const running = run?.status === 'running';
  return (
    <Panel title={row.label}>
      <div className="font-mono text-xs text-mute">{row.job}</div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        {row.job === 'detect_degenerate_patterns' && (
          <Field label="Ventana en horas">
            <input
              type="number"
              min={1}
              className={`${inputClass} w-28`}
              value={sinceHours}
              onChange={(e) => setSinceHours(e.target.value)}
            />
          </Field>
        )}
        <Button variant="primary" disabled={running} onClick={() => void start()}>
          {running ? 'Corriendo…' : 'Ejecutar'}
        </Button>
      </div>
      <dl className="mt-4 grid gap-1 text-sm">
        <div>
          <dt className="inline text-label">Última corrida auditada: </dt>
          <dd className="inline text-ink-3">{formatDateTime(row.last_audited_at)}</dd>
        </div>
        {run && (
          <div>
            <dt className="inline text-label">Esta sesión: </dt>
            <dd className={`inline font-semibold ${STATUS[run.status].className}`}>
              {STATUS[run.status].label}
            </dd>
          </div>
        )}
      </dl>
      {run?.error && <p className="mt-2 font-mono text-xs text-series-2">{run.error}</p>}
      {run?.status === 'succeeded' && run.result !== null && (
        <pre className="mt-2 max-h-56 overflow-auto font-mono text-xs text-ink-3">
          {JSON.stringify(run.result, null, 2)}
        </pre>
      )}
      <div className="mt-2">
        <ErrorBox error={error} />
      </div>
    </Panel>
  );
}

/** 24 §3.7. Los jobs corren en segundo plano en el proceso del panel. */
export default function Jobs() {
  const { data, error, loading, reload } = useResource(() => api.jobs());
  return (
    <Page
      title="Jobs"
      intro="Los cuatro jobs de fondo, a mano. La programación periódica llega con el despliegue."
    >
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      <div className="grid gap-4 lg:grid-cols-2">
        {data?.jobs.map((row) => <JobCard key={row.job} row={row} onFinished={reload} />)}
      </div>
    </Page>
  );
}
