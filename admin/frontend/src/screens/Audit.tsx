import { useState } from 'react';

import { api } from '../api';
import { Button, ErrorBox, Field, inputClass, Loading, Page, Panel } from '../components/ui';
import { formatDateTime } from '../lib/format';
import { useResource } from '../lib/resource';

/** 24 §3.10. Sólo lectura: `admin_audit` es append-only. */
export default function Audit() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState('');
  const { data, error, loading } = useResource(() => api.audit(page, action), [page, action]);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <Page title="Auditoría" intro="Toda acción de administración, de la más nueva a la más vieja.">
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && (
        <Panel
          actions={
            <Field label="Acción">
              <select
                className={inputClass}
                value={action}
                onChange={(e) => {
                  setAction(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">Todas</option>
                {data.actions.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </Field>
          }
        >
          {data.items.length === 0 ? (
            <p className="text-sm text-mute">No hay filas.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-edge-soft">
              {data.items.map((row) => (
                <li key={row.audit_id} className="py-2">
                  <details>
                    <summary className="flex min-h-11 cursor-pointer flex-wrap items-center gap-3 text-sm">
                      <span className="text-ink-4">{formatDateTime(row.created_at)}</span>
                      <span className="font-mono text-gold">{row.action}</span>
                    </summary>
                    <pre className="mt-2 overflow-x-auto font-mono text-xs text-ink-3">
                      {JSON.stringify(row.payload, null, 2)}
                    </pre>
                  </details>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 flex items-center justify-between text-sm text-mute">
            <span>
              {data.total} filas · página {data.page} de {pages}
            </span>
            <div className="flex gap-2">
              <Button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Anterior
              </Button>
              <Button disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                Siguiente
              </Button>
            </div>
          </div>
        </Panel>
      )}
    </Page>
  );
}
