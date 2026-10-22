import { Link } from 'react-router-dom';

import { api, type TierIndicators } from '../api';
import { ErrorBox, Loading, Notice, Page, Panel, TableWrap, td, th } from '../components/ui';
import { useResource } from '../lib/resource';

function Check({ ok }: { ok: boolean }) {
  return (
    <span className={`font-semibold ${ok ? 'text-green' : 'text-series-2'}`}>
      {ok ? '✓ cumple' : '✗ no cumple'}
    </span>
  );
}

function TierBox({ tier }: { tier: TierIndicators }) {
  const missing = [
    !tier.meets_median && 'la mediana de D_n',
    !tier.meets_connectivity && 'la conectividad',
  ].filter(Boolean);
  return (
    <Panel title="Habilitar el tier 2 (21 §7.2)">
      <dl className="grid gap-4 sm:grid-cols-2">
        <div className="bevel-8 border border-edge bg-control p-4">
          <dt className="text-xs uppercase tracking-[0.12em] text-label">Mediana de D_n del tier 1</dt>
          <dd className="mt-1 font-display text-2xl text-ink">
            {tier.median_dn ?? '—'} <span className="text-sm text-mute">/ {tier.median_threshold}</span>
          </dd>
          <dd className="mt-1 text-sm">
            <Check ok={tier.meets_median} />
          </dd>
        </div>
        <div className="bevel-8 border border-edge bg-control p-4">
          <dt className="text-xs uppercase tracking-[0.12em] text-label">Dimensiones conectadas</dt>
          <dd className="mt-1 font-display text-2xl text-ink">
            {tier.connected} de {tier.total_dimensions}{' '}
            <span className="text-sm text-mute">/ al menos {tier.connected_threshold}</span>
          </dd>
          <dd className="mt-1 text-sm">
            <Check ok={tier.meets_connectivity} />
          </dd>
        </div>
      </dl>
      <p className="mt-4 text-sm font-semibold text-ink-2">
        {tier.ready
          ? 'Se cumple la condición para habilitar el tier 2.'
          : `No se cumple la condición para habilitar el tier 2: falta ${missing.join(' y ')}.`}
      </p>
      <p className="mt-1 text-xs text-mute">
        El panel no habilita el tier por su cuenta: se cambia{' '}
        <code className="font-mono">sampler.enabled_pool_tiers</code> en{' '}
        <Link to="/parametros" className="text-cyan underline">
          Parámetros
        </Link>
        .
      </p>
    </Panel>
  );
}

/** 24 §3.2. */
export default function Connectivity() {
  const { data, error, loading } = useResource(() => api.connectivity());

  return (
    <Page
      title="Conectividad y tier"
      intro="Componentes del grafo de comparaciones por dimensión, calculadas en lectura: esta vista no marca ni crea puentes."
    >
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && data.patch === null && <Notice>No hay parche vigente: no hay grafo que mirar.</Notice>}
      {data?.tier && <TierBox tier={data.tier} />}
      {data && data.dimensions.length > 0 && (
        <Panel title="Por dimensión">
          <TableWrap>
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className={th}>Dimensión</th>
                  <th className={`${th} text-right`}>Componentes</th>
                  <th className={`${th} text-right`}>Mayor componente</th>
                  <th className={`${th} text-right`}>Puentes pendientes</th>
                  <th className={th}>Estado</th>
                </tr>
              </thead>
              <tbody>
                {data.dimensions.map((d) => (
                  <tr key={d.code}>
                    <td className={td}>
                      {d.label} <span className="font-mono text-xs text-mute">{d.code}</span>
                    </td>
                    <td className={`${td} text-right font-mono`}>{d.components}</td>
                    <td className={`${td} text-right font-mono`}>{d.largest_component}</td>
                    <td className={`${td} text-right font-mono`}>{d.pending_bridges}</td>
                    <td className={td}>
                      <span className={d.connected ? 'text-green' : 'text-series-2'}>
                        {d.connected ? 'conectada' : 'partida'}
                      </span>
                    </td>
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
