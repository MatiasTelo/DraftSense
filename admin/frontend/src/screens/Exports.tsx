import { useEffect, useRef, useState } from 'react';

import { api, type ExportRun } from '../api';
import { Button, ErrorBox, Field, inputClass, Loading, Page, Panel, TableWrap, td, th } from '../components/ui';
import { formatDateTime } from '../lib/format';
import { useResource } from '../lib/resource';
import { POLL_MS } from './Jobs';

/**
 * 24 §3.9 (nota del 29/10). *Generar CSV* corre el pipeline de agregación en segundo plano, como
 * un job: se consulta el estado cada 2 s y, al terminar, la lista de corridas se recarga. Los
 * campos vacíos se mandan como `null` y los resuelve `app_settings`. Desde la semana 10 cada
 * corrida trae además el Informe de Calidad de Datos (`docs/27-validacion-confiabilidad.md`).
 */

const STATUS: Record<ExportRun['status'], { label: string; className: string }> = {
  running: { label: 'corriendo', className: 'text-cyan' },
  succeeded: { label: 'terminó bien', className: 'text-green' },
  failed: { label: 'falló', className: 'text-series-2' },
};

/**
 * Vacío es `null` («usar app_settings»). Lo que no es un número **es un error**, no un vacío:
 * `Number('0,25')` es `NaN`, `JSON.stringify` lo manda como `null`, y la corrida salía con el
 * umbral por defecto sin avisar (13/11/2026).
 */
function numberOrNull(value: string, label: string): number | null {
  const trimmed = value.trim();
  if (trimmed === '') return null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label}: «${trimmed}» no es un número. Los decimales van con punto.`);
  }
  return parsed;
}

export default function Exports() {
  const { data, error, loading, reload } = useResource(() => api.exports());
  const defaults = data?.defaults;
  const [form, setForm] = useState<{ window: string; trust: string; halflife: string; bootstrap: string } | null>(
    null,
  );
  const [run, setRun] = useState<ExportRun | null>(null);
  const [startError, setStartError] = useState<Error | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (defaults && form === null) {
      setForm({
        window: defaults.patch_window ?? '',
        trust: String(defaults.min_trust),
        halflife: defaults.decay_halflife_days === null ? '' : String(defaults.decay_halflife_days),
        bootstrap: defaults.bootstrap_samples === null ? '' : String(defaults.bootstrap_samples),
      });
    }
  }, [defaults, form]);

  useEffect(() => {
    if (data?.last_run && run === null) setRun(data.last_run);
  }, [data, run]);

  useEffect(() => {
    if (run?.status !== 'running') return;
    timer.current = window.setTimeout(async () => {
      try {
        const next = await api.exportRun(run.run_id);
        setRun(next);
        if (next.status !== 'running') reload();
      } catch (e) {
        // Sin esto el botón queda deshabilitado para siempre: el estado seguía en `running`
        // aunque el proceso del panel se hubiera reiniciado y la corrida ya no existiera.
        setStartError(e as Error);
        setRun(null);
        reload();
      }
    }, POLL_MS);
    return () => window.clearTimeout(timer.current);
  }, [run, reload]);

  async function start() {
    if (form === null) return;
    setStartError(null);
    try {
      const params = {
        patch_window: form.window.trim() === '' ? null : form.window.trim(),
        min_trust: numberOrNull(form.trust, 'Umbral de confianza'),
        halflife: numberOrNull(form.halflife, 'Vida media del decaimiento'),
        bootstrap: numberOrNull(form.bootstrap, 'Remuestreos del bootstrap'),
      };
      const started = await api.startExport(params);
      setRun({
        run_id: started.run_id,
        params,
        status: started.status,
        started_at: new Date().toISOString(),
        finished_at: null,
        result: null,
        error: null,
      });
    } catch (e) {
      setStartError(e as Error);
    }
  }

  const running = run?.status === 'running';
  const set = (key: 'window' | 'trust' | 'halflife' | 'bootstrap') => (event: { target: { value: string } }) =>
    setForm((current) => (current === null ? current : { ...current, [key]: event.target.value }));

  // Las filas de `exports` agrupadas por corrida, en el orden en que llegan (de la más nueva).
  const runs: { key: string; rows: NonNullable<typeof data>['exports'] }[] = [];
  for (const row of data?.exports ?? []) {
    const key = row.run ?? `sin-carpeta-${row.export_id}`;
    const group = runs.find((g) => g.key === key);
    if (group) group.rows.push(row);
    else runs.push({ key, rows: [row] });
  }

  return (
    <Page
      title="Exportaciones"
      intro="Generar los seis CSV de la entrega y el Informe de Calidad de Datos (CU-08)."
    >
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && form && (
        <>
          <Panel title="Nueva corrida">
            <fieldset disabled={!data.enabled || running} className="grid gap-3 md:grid-cols-2">
              <Field label="Ventana de parches" hint="16.18..16.20, o un solo parche">
                <input className={`${inputClass} font-mono`} value={form.window} onChange={set('window')} />
              </Field>
              <Field label="Umbral de confianza">
                <input className={`${inputClass} font-mono`} value={form.trust} onChange={set('trust')} />
              </Field>
              <Field label="Vida media del decaimiento (días)">
                <input className={`${inputClass} font-mono`} value={form.halflife} onChange={set('halflife')} />
              </Field>
              <Field label="Remuestreos del bootstrap">
                <input className={`${inputClass} font-mono`} value={form.bootstrap} onChange={set('bootstrap')} />
              </Field>
            </fieldset>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button variant="primary" disabled={!data.enabled || running} onClick={() => void start()}>
                Generar CSV
              </Button>
              {run && (
                <span className={`text-sm ${STATUS[run.status].className}`}>
                  {STATUS[run.status].label}
                  {run.status === 'succeeded' && run.result
                    ? ` · ${run.result.files.length} archivos, ${run.result.responses} respuestas`
                    : ''}
                </span>
              )}
            </div>
            <ErrorBox error={startError} />
            {run?.status === 'failed' && run.error && (
              <p className="mt-3 border-l-2 border-series-2 px-3 py-2 text-sm text-ink-3">{run.error}</p>
            )}
            {run?.status === 'succeeded' && run.result && run.result.warnings.length > 0 && (
              <p className="mt-3 text-sm text-mute">Avisos: {run.result.warnings.join(', ')}</p>
            )}
          </Panel>
          <Panel title="Corridas anteriores">
            {runs.length === 0 ? (
              <p className="text-sm text-mute">Todavía no hay corridas.</p>
            ) : (
              <TableWrap>
                <table className="w-full text-sm">
                  <thead>
                    <tr>
                      <th className={th}>Fecha</th>
                      <th className={th}>Archivo</th>
                      <th className={th}>Ventana</th>
                      <th className={`${th} text-right`}>Filas</th>
                      <th className={th}>SHA-256</th>
                      <th className={th}>Descargar</th>
                    </tr>
                  </thead>
                  {runs.map((group) => (
                    <tbody key={group.key} className="border-t-2 border-edge">
                      {group.rows.map((e) => (
                        <tr key={e.export_id}>
                          <td className={td}>{formatDateTime(e.created_at)}</td>
                          <td className={`${td} font-mono`}>{e.file_name}</td>
                          <td className={`${td} font-mono`}>{e.patch_window}</td>
                          <td className={`${td} text-right font-mono`}>{e.row_count}</td>
                          <td className={`${td} font-mono text-xs`}>{e.sha256.slice(0, 12)}…</td>
                          <td className={td}>
                            <a className="text-gold underline" href={api.exportFileUrl(e.export_id)} download>
                              {e.file_name.endsWith('.md') ? 'Informe' : 'CSV'}
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  ))}
                </table>
              </TableWrap>
            )}
          </Panel>
        </>
      )}
    </Page>
  );
}
