import { api } from '../api';
import { Button, ErrorBox, Field, inputClass, Loading, Page, Panel, TableWrap, td, th } from '../components/ui';
import { formatDateTime } from '../lib/format';
import { useResource } from '../lib/resource';

/**
 * 24 §3.9. El formulario de CU-08 existe desde la semana 7; el botón se habilita cuando esté el
 * pipeline de agregación (semana 9). No hay endpoint detrás todavía.
 */
export default function Exports() {
  const { data, error, loading } = useResource(() => api.exports());
  const defaults = data?.defaults;

  return (
    <Page title="Exportaciones" intro="Generar los seis CSV y el Informe de Calidad de Datos (CU-08).">
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && defaults && (
        <>
          <Panel title="Nueva corrida">
            <fieldset disabled className="grid gap-3 md:grid-cols-2">
              <Field label="Ventana de parches">
                <input className={`${inputClass} font-mono`} defaultValue={defaults.patch_window ?? ''} />
              </Field>
              <Field label="Umbral de confianza">
                <input className={`${inputClass} font-mono`} defaultValue={defaults.min_trust} />
              </Field>
              <Field label="Vida media del decaimiento (días)">
                <input className={`${inputClass} font-mono`} defaultValue={defaults.decay_halflife_days ?? ''} />
              </Field>
              <Field label="Remuestreos del bootstrap">
                <input className={`${inputClass} font-mono`} defaultValue={defaults.bootstrap_samples ?? ''} />
              </Field>
            </fieldset>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button variant="primary" disabled={!data.enabled}>
                Generar CSV
              </Button>
              <span className="text-sm text-mute">
                Disponible cuando esté el pipeline de agregación (semana 9).
              </span>
            </div>
          </Panel>
          <Panel title="Corridas anteriores">
            {data.exports.length === 0 ? (
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
                    </tr>
                  </thead>
                  <tbody>
                    {data.exports.map((e) => (
                      <tr key={e.export_id}>
                        <td className={td}>{formatDateTime(e.created_at)}</td>
                        <td className={`${td} font-mono`}>{e.file_name}</td>
                        <td className={`${td} font-mono`}>{e.patch_window}</td>
                        <td className={`${td} text-right font-mono`}>{e.row_count}</td>
                        <td className={`${td} font-mono text-xs`}>{e.sha256.slice(0, 12)}…</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
          </Panel>
        </>
      )}
    </Page>
  );
}
