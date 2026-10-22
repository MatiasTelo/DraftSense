import { useState } from 'react';

import { api } from '../api';
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

/** 24 §3.5. Mover de tier es un `UPDATE`, no un despliegue (ADR-006). */
export default function Pool() {
  const { data, error, loading, reload } = useResource(() => api.champions());
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [target, setTarget] = useState(1);
  const [filter, setFilter] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<Error | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const rows =
    data?.champions.filter((c) => c.name.toLowerCase().includes(filter.trim().toLowerCase())) ?? [];

  function toggle(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function apply() {
    setBusy(true);
    setActionError(null);
    try {
      const { updated } = await api.setPoolTier([...selected], target);
      setDone(`${updated} campeón(es) movidos al tier ${target}.`);
      setSelected(new Set());
      setConfirming(false);
      reload();
    } catch (e) {
      setActionError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page
      title="Pool"
      intro={
        data
          ? `El sampler usa los tiers 1 a ${data.enabled_pool_tiers}. Mover un campeón de tier cambia las preguntas nuevas, no las ya respondidas.`
          : undefined
      }
    >
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {done && <Notice>{done}</Notice>}
      {data && (
        <Panel
          actions={
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Buscar">
                <input
                  className={inputClass}
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Nombre"
                />
              </Field>
              <Field label="Mover a">
                <select
                  className={inputClass}
                  value={target}
                  onChange={(e) => setTarget(Number(e.target.value))}
                >
                  {[1, 2, 3].map((t) => (
                    <option key={t} value={t}>
                      Tier {t}
                    </option>
                  ))}
                </select>
              </Field>
              <Button
                variant="primary"
                disabled={selected.size === 0}
                onClick={() => setConfirming(true)}
              >
                Mover {selected.size || ''} al tier {target}
              </Button>
            </div>
          }
        >
          <TableWrap>
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className={th}>
                    <span className="sr-only">Elegir</span>
                  </th>
                  <th className={th}>Campeón</th>
                  <th className={th}>Roles</th>
                  <th className={`${th} text-right`}>Tier</th>
                  <th className={`${th} text-right`}>Mejor puesto en el snapshot</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.champion_id}>
                    <td className={td}>
                      <input
                        type="checkbox"
                        className="h-5 w-5"
                        aria-label={`Elegir ${c.name}`}
                        checked={selected.has(c.champion_id)}
                        onChange={() => toggle(c.champion_id)}
                      />
                    </td>
                    <td className={td}>{c.name}</td>
                    <td className={`${td} text-xs`}>{c.roles.join(', ')}</td>
                    <td className={`${td} text-right font-mono`}>{c.pool_tier}</td>
                    <td className={`${td} text-right font-mono`}>{c.best_rank ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </Panel>
      )}
      <Confirm
        open={confirming}
        title="Mover de tier"
        confirmLabel={`Mover al tier ${target}`}
        busy={busy}
        onCancel={() => setConfirming(false)}
        onConfirm={() => void apply()}
      >
        <p>
          {selected.size} campeón(es) pasan al tier {target}. El sampler lo ve en la próxima
          pregunta que genere.
        </p>
        <div className="mt-3">
          <ErrorBox error={actionError} />
        </div>
      </Confirm>
    </Page>
  );
}
