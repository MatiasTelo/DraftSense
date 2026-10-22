import { useState } from 'react';

import { api, type Coverage as CoverageData } from '../api';
import { ErrorBox, Field, inputClass, Loading, Page, Panel, TableWrap, td, th } from '../components/ui';
import { useResource } from '../lib/resource';

function band(n: number, bands: CoverageData['bands']) {
  if (n >= bands.solid) return { className: 'bg-band-high text-void', label: 'sólido' };
  if (n >= bands.limited) return { className: 'bg-band-mid text-void', label: 'limitado' };
  return { className: 'bg-band-low text-ink', label: 'insuficiente' };
}

/** 24 §3.3. */
export default function Coverage() {
  const { data, error, loading } = useResource(() => api.coverage());
  const [tier, setTier] = useState('');
  const [role, setRole] = useState('');

  const roles = data ? [...new Set(data.champions.flatMap((c) => c.roles))].sort() : [];
  const rows =
    data?.champions.filter(
      (c) => (!tier || String(c.pool_tier) === tier) && (!role || c.roles.includes(role)),
    ) ?? [];

  return (
    <Page
      title="Cobertura"
      intro="D_n por campeón y dimensión del pool habilitado: comparaciones agregables del tipo 1 en las que participa el campeón."
    >
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && (
        <Panel
          actions={
            <div className="flex flex-wrap gap-3">
              <Field label="Tier">
                <select className={inputClass} value={tier} onChange={(e) => setTier(e.target.value)}>
                  <option value="">Todos</option>
                  {[1, 2, 3].map((t) => (
                    <option key={t} value={t}>
                      Tier {t}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Rol">
                <select className={inputClass} value={role} onChange={(e) => setRole(e.target.value)}>
                  <option value="">Todos</option>
                  {roles.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          }
        >
          <ul className="mb-3 flex flex-wrap gap-4 text-xs text-ink-4" aria-label="Leyenda">
            <li className="flex items-center gap-2">
              <span aria-hidden className="inline-block h-2.5 w-2.5 bg-band-high" />≥ {data.bands.solid}
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden className="inline-block h-2.5 w-2.5 bg-band-mid" />≥ {data.bands.limited}
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden className="inline-block h-2.5 w-2.5 bg-band-low" />
              menos de {data.bands.limited}
            </li>
          </ul>
          <p className="mb-3 text-xs text-mute">
            Aproxima el soporte que va a tener el export sólo por n: el ancho del intervalo no se puede
            saber sin ajustar Bradley-Terry (26 §2.4).
          </p>
          <TableWrap>
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className={th}>Campeón</th>
                  <th className={th}>Tier</th>
                  {data.dimensions.map((d) => (
                    <th key={d.code} className={`${th} text-right`} title={d.code}>
                      {d.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.champion_id}>
                    <td className={`${td} whitespace-nowrap`}>{c.name}</td>
                    <td className={`${td} font-mono`}>{c.pool_tier}</td>
                    {data.dimensions.map((d) => {
                      const n = c.counts[d.code] ?? 0;
                      const b = band(n, data.bands);
                      return (
                        <td key={d.code} className="border-b border-edge-soft p-[2px] text-right">
                          <span
                            className={`block px-2 py-1 font-mono text-xs ${b.className}`}
                            title={`${c.name} · ${d.label}: ${n} (${b.label})`}
                          >
                            {n}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </Panel>
      )}
    </Page>
  );
}
