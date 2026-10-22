import { useState } from 'react';

import { api, type SettingRow } from '../api';
import { Button, Confirm, ErrorBox, Loading, Notice, Page, Panel } from '../components/ui';
import { formatDateTime } from '../lib/format';
import { useResource } from '../lib/resource';

const BLOCKS = ['sampler', 'quality', 'gamification', 'export', 'aggregation'];

function pretty(value: unknown) {
  return JSON.stringify(value, null, 2);
}

/** 24 §3.6. Cualquier JSON válido se acepta: la responsabilidad del valor es de quien edita. */
export default function Settings() {
  const { data, error, loading, reload } = useResource(() => api.settings());
  const [editing, setEditing] = useState<SettingRow | null>(null);
  const [draft, setDraft] = useState('');
  const [parsed, setParsed] = useState<{ value: unknown } | null>(null);
  const [parseError, setParseError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<Error | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const groups = data
    ? [...BLOCKS, ...new Set(data.settings.map((s) => s.block).filter((b) => !BLOCKS.includes(b)))]
        .map((block) => ({ block, rows: data.settings.filter((s) => s.block === block) }))
        .filter((g) => g.rows.length > 0)
    : [];

  function review() {
    try {
      setParsed({ value: JSON.parse(draft) });
      setParseError(null);
    } catch {
      setParseError(new Error('No es JSON válido.'));
    }
  }

  async function apply() {
    if (!editing || !parsed) return;
    setBusy(true);
    setActionError(null);
    try {
      const result = await api.setSetting(editing.key, parsed.value);
      setDone(
        result.changed
          ? `${result.key} cambió. La API pública lo ve en a lo sumo 60 segundos.`
          : `${result.key} ya tenía ese valor; no se cambió nada.`,
      );
      setEditing(null);
      setParsed(null);
      reload();
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page
      title="Parámetros"
      intro="Las claves de app_settings. No se crean claves desde acá: una clave nueva llega con el código que la usa, en un seed."
    >
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {done && <Notice>{done}</Notice>}
      {groups.map(({ block, rows }) => (
        <Panel key={block} title={`${block}.`}>
          <ul className="flex flex-col divide-y divide-edge-soft">
            {rows.map((s) => (
              <li key={s.key} className="flex flex-wrap items-start justify-between gap-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-sm text-ink">{s.key}</div>
                  {s.description && <div className="mt-1 text-xs text-ink-4">{s.description}</div>}
                  <pre className="mt-2 overflow-x-auto font-mono text-xs text-gold">{pretty(s.value)}</pre>
                  <div className="mt-1 text-xs text-mute">
                    {formatDateTime(s.updated_at)} · {s.updated_by ?? '—'}
                  </div>
                </div>
                <Button
                  onClick={() => {
                    setEditing(s);
                    setDraft(pretty(s.value));
                    setParsed(null);
                    setParseError(null);
                    setActionError(null);
                  }}
                >
                  Editar
                </Button>
              </li>
            ))}
          </ul>
        </Panel>
      ))}

      {editing && !parsed && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-void/80 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-label={`Editar ${editing.key}`}
            className="bevel-12 w-full max-w-lg border border-edge-strong bg-panel p-6"
          >
            <h2 className="font-display text-lg font-semibold text-ink">{editing.key}</h2>
            <label className="mt-3 block text-sm text-ink-4">
              Valor nuevo (JSON)
              <textarea
                className="bevel-8 mt-1 block h-48 w-full border border-edge bg-control p-3 font-mono text-xs text-ink"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
            </label>
            <div className="mt-3">
              <ErrorBox error={parseError} />
            </div>
            <div className="mt-4 flex justify-end gap-3">
              <Button onClick={() => setEditing(null)}>Cancelar</Button>
              <Button variant="primary" onClick={review}>
                Revisar cambio
              </Button>
            </div>
          </div>
        </div>
      )}

      <Confirm
        open={editing !== null && parsed !== null}
        title={`Cambiar ${editing?.key ?? ''}`}
        confirmLabel="Guardar"
        busy={busy}
        onCancel={() => setParsed(null)}
        onConfirm={() => void apply()}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <div className="text-xs uppercase tracking-[0.12em] text-label">Actual</div>
            <pre className="mt-1 overflow-x-auto font-mono text-xs text-ink-3">
              {editing && pretty(editing.value)}
            </pre>
          </div>
          <div>
            <div className="text-xs uppercase tracking-[0.12em] text-label">Nuevo</div>
            <pre className="mt-1 overflow-x-auto font-mono text-xs text-gold">
              {parsed && pretty(parsed.value)}
            </pre>
          </div>
        </div>
        <div className="mt-3">
          <ErrorBox error={actionError} />
        </div>
      </Confirm>
    </Page>
  );
}
