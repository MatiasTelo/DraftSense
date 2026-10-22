import { useState } from 'react';

import { api } from '../api';
import { VolumeChart } from '../components/charts';
import { ErrorBox, Loading, Page, Panel, Stat } from '../components/ui';
import { formatNumber } from '../lib/format';
import { useResource } from '../lib/resource';

const WINDOWS = [7, 30, 90] as const;

/** 24 §3.1. */
export default function Overview() {
  const [days, setDays] = useState<(typeof WINDOWS)[number]>(30);
  const { data, error, loading } = useResource(() => api.overview(days), [days]);

  return (
    <Page title="Resumen" intro="Volumen y estado general de la recolección del parche vigente.">
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Envíos del parche"
              value={formatNumber(data.totals.submissions)}
              hint={`${formatNumber(data.totals.rows)} filas · ${formatNumber(data.totals.aggregable_rows)} agregables`}
            />
            <Stat
              label="Respondedores"
              value={formatNumber(data.totals.respondents)}
              hint={`${formatNumber(data.totals.flagged_respondents)} marcados`}
            />
            <Stat label="Envíos de hoy" value={formatNumber(data.today_submissions)} hint={data.timezone} />
            <Stat
              label="Dimensiones conectadas"
              value={`${data.connected_dimensions} de ${data.total_dimensions}`}
            />
          </div>
          <Panel
            title="Volumen por día y por tipo"
            actions={
              <div role="group" aria-label="Ventana" className="flex gap-1">
                {WINDOWS.map((w) => (
                  <button
                    key={w}
                    type="button"
                    aria-pressed={days === w}
                    onClick={() => setDays(w)}
                    className={`bevel-8 min-h-11 px-3 text-sm ${
                      days === w ? 'bg-gold font-semibold text-void' : 'bg-control text-ink-4'
                    }`}
                  >
                    {w} días
                  </button>
                ))}
              </div>
            }
          >
            <VolumeChart types={data.types} volume={data.volume} />
            <p className="mt-3 text-xs text-mute">
              Cuenta envíos: un ranking del tipo 1 es uno solo aunque guarde diez filas.
            </p>
          </Panel>
        </>
      )}
    </Page>
  );
}
