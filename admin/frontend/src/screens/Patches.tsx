import { useState, type FormEvent, type ReactNode } from 'react';

import { api, ApiError, type SeedResult } from '../api';
import {
  Button,
  Confirm,
  ErrorBox,
  Field,
  inputClass,
  Loading,
  Notice,
  Page,
  Panel,
  TableWrap,
  td,
  th,
} from '../components/ui';
import { useResource } from '../lib/resource';

function Outcome({ result }: { result: SeedResult | null }) {
  if (!result) return null;
  return (
    <div className="mt-3 flex flex-col gap-2">
      <Notice>
        <pre className="overflow-x-auto font-mono text-xs">{JSON.stringify(result.result, null, 2)}</pre>
      </Notice>
      {result.warnings.map((w) => (
        <p key={w} className="text-xs text-series-4">
          Aviso: {w}
        </p>
      ))}
    </div>
  );
}

function Step({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: ReactNode;
}) {
  return (
    <Panel title={`${number}. ${title}`}>
      <div className="flex flex-col gap-3">{children}</div>
    </Panel>
  );
}

/** Lo común de los tres seeds: el envío, el error y el resultado. */
function useSeed(onDone: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<SeedResult | null>(null);
  async function run(call: () => Promise<SeedResult>) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await call());
      onDone();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, result, run };
}

const optional = (value: string) => (value.trim() ? value.trim() : null);

/** 24 §3.8: los cuatro pasos de CU-06, en orden. */
export default function Patches() {
  const patches = useResource(() => api.patches());
  const files = useResource(() => api.seedFiles());
  const reload = patches.reload;

  const [version, setVersion] = useState('');
  const [releasedAt, setReleasedAt] = useState('');

  // Paso 1
  const champions = useSeed(reload);
  const [ddragon, setDdragon] = useState('');
  const [useSnapshot, setUseSnapshot] = useState(false);
  // Paso 2
  const pickRate = useSeed(reload);
  const [pickFile, setPickFile] = useState('');
  const [source, setSource] = useState('lolalytics');
  const [sourceUrl, setSourceUrl] = useState('');
  const [capturedAt, setCapturedAt] = useState('');
  const [notes, setNotes] = useState('');
  // Paso 3
  const honeypots = useSeed(reload);
  const [honeyFile, setHoneyFile] = useState('');
  const [reactivate, setReactivate] = useState(false);
  // Paso 4
  const [force, setForce] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [activating, setActivating] = useState(false);
  const [activationError, setActivationError] = useState<Error | null>(null);
  const [activated, setActivated] = useState<string | null>(null);

  const current = patches.data?.patches.find((p) => p.is_current)?.version ?? null;
  const needsVersion = !version.trim();

  function submit(e: FormEvent, action: () => void) {
    e.preventDefault();
    action();
  }

  async function activate() {
    setActivating(true);
    setActivationError(null);
    try {
      const result = await api.activate(version.trim(), force);
      setActivated(
        result.changed
          ? `Parche vigente: ${result.version} (antes: ${result.previous ?? 'ninguno'}).`
          : `El parche ${result.version} ya era el vigente; no se cambió nada.`,
      );
      setConfirming(false);
      reload();
    } catch (e) {
      setActivationError(e as Error);
      // Un 409 lista los faltantes: se muestran fuera del diálogo, en el paso 4.
      if (e instanceof ApiError && e.code === 'patch_not_ready') setConfirming(false);
    } finally {
      setActivating(false);
    }
  }

  return (
    <Page
      title="Parches y seeds"
      intro="Los archivos se eligen de los que ya están en infra/seeds/ del servidor; el panel no sube archivos."
    >
      <ErrorBox error={patches.error ?? files.error} />
      {patches.loading && !patches.data && <Loading />}
      {patches.data && (
        <Panel title="Parches registrados">
          <TableWrap>
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className={th}>Versión</th>
                  <th className={th}>Salida</th>
                  <th className={th}>Vigente</th>
                  <th className={th}>Snapshot</th>
                  <th className={`${th} text-right`}>Honeypots activas</th>
                  <th className={th}>Le falta</th>
                </tr>
              </thead>
              <tbody>
                {patches.data.patches.map((p) => (
                  <tr key={p.patch_id}>
                    <td className={`${td} font-mono`}>{p.version}</td>
                    <td className={td}>{p.released_at}</td>
                    <td className={td}>{p.is_current ? <strong className="text-gold">sí</strong> : 'no'}</td>
                    <td className={td}>{p.has_snapshot ? 'sí' : 'no'}</td>
                    <td className={`${td} text-right font-mono`}>{p.active_honeypots}</td>
                    <td className={`${td} text-xs`}>{p.missing.join('; ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </Panel>
      )}

      <Panel title="Parche sobre el que se trabaja">
        <div className="flex flex-wrap gap-3">
          <Field label="Versión" hint="p. ej. 16.20">
            <input
              className={`${inputClass} font-mono`}
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            />
          </Field>
          <Field label="Fecha de salida (opcional)">
            <input
              type="date"
              className={inputClass}
              value={releasedAt}
              onChange={(e) => setReleasedAt(e.target.value)}
            />
          </Field>
        </div>
      </Panel>

      <Step number={1} title="Catálogo de campeones">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) =>
            submit(e, () =>
              void champions.run(() =>
                api.seedChampions({
                  version: version.trim(),
                  ddragon_version: optional(ddragon),
                  released_at: optional(releasedAt),
                  use_snapshot: useSnapshot,
                }),
              ),
            )
          }
        >
          <Field label="Versión de Data Dragon (opcional)" hint="Por defecto, la última publicada">
            <input className={`${inputClass} font-mono`} value={ddragon} onChange={(e) => setDdragon(e.target.value)} />
          </Field>
          <label className="flex min-h-11 items-center gap-2 text-sm text-ink-4">
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={useSnapshot}
              onChange={(e) => setUseSnapshot(e.target.checked)}
            />
            Usar el respaldo local
            {files.data?.ddragon_snapshot[0] && (
              <span className="font-mono text-xs">({files.data.ddragon_snapshot[0]})</span>
            )}
          </label>
          <Button type="submit" variant="primary" disabled={needsVersion || champions.busy}>
            {champions.busy ? 'Cargando…' : 'Cargar catálogo'}
          </Button>
        </form>
        <ErrorBox error={champions.error} />
        <Outcome result={champions.result} />
      </Step>

      <Step number={2} title="Snapshot de pick rate">
        <form
          className="grid gap-3 md:grid-cols-2"
          onSubmit={(e) =>
            submit(e, () =>
              void pickRate.run(() =>
                api.seedPickRate({
                  version: version.trim(),
                  file: pickFile,
                  source: source.trim(),
                  source_url: sourceUrl.trim(),
                  captured_at: capturedAt,
                  released_at: optional(releasedAt),
                  notes: optional(notes),
                }),
              ),
            )
          }
        >
          <Field label="Archivo">
            <select className={inputClass} value={pickFile} onChange={(e) => setPickFile(e.target.value)} required>
              <option value="">Elegir…</option>
              {files.data?.pick_rate.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Fuente">
            <input className={inputClass} value={source} onChange={(e) => setSource(e.target.value)} required />
          </Field>
          <Field label="URL de la captura" hint="La exacta, con sus filtros">
            <input className={inputClass} value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} required />
          </Field>
          <Field label="Fecha de captura">
            <input
              type="date"
              className={inputClass}
              value={capturedAt}
              onChange={(e) => setCapturedAt(e.target.value)}
              required
            />
          </Field>
          <Field label="Notas (opcional)">
            <input className={inputClass} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
          <div className="flex items-end">
            <Button type="submit" variant="primary" disabled={needsVersion || pickRate.busy}>
              {pickRate.busy ? 'Cargando…' : 'Cargar snapshot'}
            </Button>
          </div>
        </form>
        <ErrorBox error={pickRate.error} />
        <Outcome result={pickRate.result} />
      </Step>

      <Step number={3} title="Honeypots">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) =>
            submit(e, () =>
              void honeypots.run(() =>
                api.seedHoneypots({ version: version.trim(), file: honeyFile, force: reactivate }),
              ),
            )
          }
        >
          <Field label="Archivo">
            <select className={inputClass} value={honeyFile} onChange={(e) => setHoneyFile(e.target.value)} required>
              <option value="">Elegir…</option>
              {files.data?.honeypots.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </Field>
          <label className="flex min-h-11 items-center gap-2 text-sm text-ink-4">
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={reactivate}
              onChange={(e) => setReactivate(e.target.checked)}
            />
            Reactivar las retiradas
          </label>
          <Button type="submit" variant="primary" disabled={needsVersion || honeypots.busy}>
            {honeypots.busy ? 'Cargando…' : 'Cargar honeypots'}
          </Button>
        </form>
        <ErrorBox error={honeypots.error} />
        <Outcome result={honeypots.result} />
      </Step>

      <Step number={4} title="Activar">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-h-11 items-center gap-2 text-sm text-ink-4">
            <input
              type="checkbox"
              className="h-5 w-5"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
            />
            Forzar aunque falten el snapshot o las honeypots
          </label>
          <Button variant="primary" disabled={needsVersion} onClick={() => setConfirming(true)}>
            Activar {version.trim() || 'parche'}
          </Button>
        </div>
        <ErrorBox error={confirming ? null : activationError} />
        {activated && <Notice>{activated}</Notice>}
      </Step>

      <Confirm
        open={confirming}
        title={`Activar ${version.trim()}`}
        confirmLabel={force ? 'Activar forzando' : 'Activar'}
        busy={activating}
        onCancel={() => setConfirming(false)}
        onConfirm={() => void activate()}
      >
        <p>
          Las preguntas nuevas van a tomar el parche <strong className="font-mono">{version.trim()}</strong>
          {current ? ` en lugar de ${current}` : ''}; las respuestas anteriores conservan el suyo.
        </p>
        {force && (
          <p className="mt-2 text-series-4">
            Forzar es para un entorno de prueba o una emergencia: sin honeypots el trust de los
            nuevos queda congelado todo el parche (ADR-024).
          </p>
        )}
        <div className="mt-3">
          <ErrorBox error={activationError} />
        </div>
      </Confirm>
    </Page>
  );
}
