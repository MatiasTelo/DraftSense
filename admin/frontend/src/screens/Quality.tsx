import { useState } from 'react';

import { api } from '../api';
import { TrustHistogram } from '../components/charts';
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
import { formatDateTime } from '../lib/format';
import { useResource } from '../lib/resource';

interface Pending {
  respondentId: string;
  label: string;
  flagged: boolean;
}

/** 24 §3.4. */
export default function Quality() {
  const { data, error, loading, reload } = useResource(() => api.quality());
  const [pending, setPending] = useState<Pending | null>(null);
  const [reason, setReason] = useState('');
  const [manualId, setManualId] = useState('');
  const [manualFlag, setManualFlag] = useState(true);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<Error | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function apply() {
    if (!pending) return;
    setBusy(true);
    setActionError(null);
    try {
      const result = await api.flag(pending.respondentId, pending.flagged, reason.trim());
      setDone(
        result.changed
          ? `${pending.label} quedó ${result.is_flagged ? 'marcado' : 'desmarcado'}.`
          : `${pending.label} ya estaba así; no se cambió nada.`,
      );
      setPending(null);
      setReason('');
      reload();
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page
      title="Calidad"
      intro="La distribución del trust score —nunca el de una persona— y los respondedores marcados."
    >
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {done && <Notice>{done}</Notice>}
      {data && (
        <>
          <Panel title="Distribución del trust score">
            <TrustHistogram bins={data.histogram} minTrust={data.min_trust} />
            <p className="mt-2 text-xs text-mute">
              Respondedores con al menos una respuesta en el parche vigente.
            </p>
          </Panel>
          <Panel title="Respondedores marcados">
            {data.flagged.length === 0 ? (
              <p className="text-sm text-mute">No hay respondedores marcados.</p>
            ) : (
              <TableWrap>
                <table className="w-full text-sm">
                  <thead>
                    <tr>
                      <th className={th}>Id</th>
                      <th className={`${th} text-right`}>Respuestas</th>
                      <th className={th}>Primera vez</th>
                      <th className={th}>Última vez</th>
                      <th className={th} />
                    </tr>
                  </thead>
                  <tbody>
                    {data.flagged.map((r) => (
                      <tr key={r.respondent_id}>
                        <td className={`${td} font-mono`}>{r.short_id}</td>
                        <td className={`${td} text-right font-mono`}>{r.answers_count}</td>
                        <td className={td}>{formatDateTime(r.first_seen)}</td>
                        <td className={td}>{formatDateTime(r.last_seen)}</td>
                        <td className={`${td} text-right`}>
                          <Button
                            onClick={() =>
                              setPending({
                                respondentId: r.respondent_id,
                                label: r.short_id,
                                flagged: false,
                              })
                            }
                          >
                            Desmarcar
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
          </Panel>
          <Panel title="Marcar o desmarcar a mano">
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                setPending({
                  respondentId: manualId.trim(),
                  label: manualId.trim().slice(0, 8),
                  flagged: manualFlag,
                });
              }}
            >
              <Field label="Id del respondedor (completo)">
                <input
                  className={`${inputClass} w-80 font-mono`}
                  value={manualId}
                  onChange={(e) => setManualId(e.target.value)}
                  required
                />
              </Field>
              <Field label="Acción">
                <select
                  className={inputClass}
                  value={manualFlag ? 'flag' : 'unflag'}
                  onChange={(e) => setManualFlag(e.target.value === 'flag')}
                >
                  <option value="flag">Marcar</option>
                  <option value="unflag">Desmarcar</option>
                </select>
              </Field>
              <Button type="submit" variant="primary">
                Continuar
              </Button>
            </form>
          </Panel>
        </>
      )}
      <Confirm
        open={pending !== null}
        title={pending?.flagged ? 'Marcar respondedor' : 'Desmarcar respondedor'}
        confirmLabel={pending?.flagged ? 'Marcar' : 'Desmarcar'}
        busy={busy}
        onCancel={() => {
          setPending(null);
          setActionError(null);
        }}
        onConfirm={() => {
          if (reason.trim()) void apply();
          else setActionError(new Error('El motivo es obligatorio.'));
        }}
      >
        <p>
          Respondedor <span className="font-mono">{pending?.label}</span>. Sus respuestas no se
          borran: {pending?.flagged ? 'dejan de entrar' : 'vuelven a entrar'} a la agregación.
        </p>
        <div className="mt-3">
          <Field label="Motivo (queda en la auditoría)">
            <input className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </div>
        <div className="mt-3">
          <ErrorBox error={actionError} />
        </div>
      </Confirm>
    </Page>
  );
}
