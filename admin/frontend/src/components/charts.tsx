import { useState } from 'react';

import type { QuestionType } from '../api';
import { formatNumber, shortDate, TYPE_COLORS, TYPE_LABELS } from '../lib/format';

/**
 * Gráficos del panel, en HTML plano: dos formas no justifican una biblioteca de gráficos.
 *
 * Cada uno lleva leyenda (o título, si es una sola serie), tooltip por marca al pasar el mouse o
 * enfocar con el teclado, y una vista de tabla: la identidad nunca depende sólo del color.
 */

const PLOT_HEIGHT = 160;

export function VolumeChart({
  types,
  volume,
}: {
  types: QuestionType[];
  volume: { date: string; counts: Record<QuestionType, number> }[];
}) {
  const [active, setActive] = useState<number | null>(null);
  const totals = volume.map((d) => types.reduce((sum, t) => sum + (d.counts[t] ?? 0), 0));
  const max = Math.max(1, ...totals);
  const hovered = active === null ? null : volume[active];

  return (
    <figure className="m-0">
      <ul className="mb-3 flex flex-wrap gap-4 text-xs text-ink-4" aria-label="Leyenda">
        {types.map((t) => (
          <li key={t} className="flex items-center gap-2">
            <span aria-hidden className={`inline-block h-2.5 w-2.5 ${TYPE_COLORS[t]}`} />
            {TYPE_LABELS[t]}
          </li>
        ))}
      </ul>
      <div className="relative">
        <div
          className="flex items-end gap-[2px] border-b border-edge-strong"
          style={{ height: PLOT_HEIGHT }}
          onMouseLeave={() => setActive(null)}
        >
          {volume.map((day, index) => (
            <button
              key={day.date}
              type="button"
              aria-label={`${shortDate(day.date)}: ${totals[index]} envíos`}
              className="flex h-full min-w-[3px] flex-1 flex-col-reverse gap-[2px] bg-transparent p-0"
              onMouseEnter={() => setActive(index)}
              onFocus={() => setActive(index)}
              onBlur={() => setActive(null)}
            >
              {types.map((t) => {
                const value = day.counts[t] ?? 0;
                if (!value) return null;
                return (
                  <span
                    key={t}
                    className={`block w-full ${TYPE_COLORS[t]} ${active === index ? 'opacity-100' : 'opacity-85'}`}
                    style={{ height: `${(value / max) * 100}%` }}
                  />
                );
              })}
            </button>
          ))}
        </div>
        <div className="mt-1 flex justify-between text-xs text-label">
          <span>{volume[0] && shortDate(volume[0].date)}</span>
          <span>máx. {formatNumber(max)} por día</span>
          <span>{volume.at(-1) && shortDate(volume.at(-1)!.date)}</span>
        </div>
        {hovered && (
          <div
            role="tooltip"
            className="bevel-8 pointer-events-none absolute right-0 top-0 border border-edge-strong bg-control p-3 text-xs text-ink-3"
          >
            <div className="mb-1 font-semibold text-ink">{shortDate(hovered.date)}</div>
            {types.map((t) => (
              <div key={t} className="flex justify-between gap-4">
                <span>{TYPE_LABELS[t]}</span>
                <span className="font-mono text-ink">{formatNumber(hovered.counts[t] ?? 0)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-ink-4">Ver como tabla</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="px-2 py-1 text-left text-label">Día</th>
                {types.map((t) => (
                  <th key={t} className="px-2 py-1 text-right text-label">
                    {TYPE_LABELS[t]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {volume.map((day) => (
                <tr key={day.date}>
                  <td className="px-2 py-1 text-ink-4">{shortDate(day.date)}</td>
                  {types.map((t) => (
                    <td key={t} className="px-2 py-1 text-right font-mono text-ink-3">
                      {day.counts[t] ?? 0}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

export function TrustHistogram({
  bins,
  minTrust,
}: {
  bins: { from: number; to: number; count: number }[];
  minTrust: number;
}) {
  const [active, setActive] = useState<number | null>(null);
  const max = Math.max(1, ...bins.map((b) => b.count));
  const hovered = active === null ? null : bins[active];
  const range = (b: { from: number; to: number }) => `${b.from.toFixed(2)}–${b.to.toFixed(2)}`;

  return (
    <figure className="m-0">
      <div className="relative">
        <div
          className="relative flex items-end gap-[2px] border-b border-edge-strong"
          style={{ height: PLOT_HEIGHT }}
          onMouseLeave={() => setActive(null)}
        >
          {bins.map((bin, index) => (
            <button
              key={bin.from}
              type="button"
              aria-label={`${range(bin)}: ${bin.count} respondedores`}
              className="flex h-full flex-1 flex-col justify-end bg-transparent p-0"
              onMouseEnter={() => setActive(index)}
              onFocus={() => setActive(index)}
              onBlur={() => setActive(null)}
            >
              <span
                className={`block w-full bg-series-1 ${active === index ? 'opacity-100' : 'opacity-85'}`}
                style={{ height: `${(bin.count / max) * 100}%` }}
              />
            </button>
          ))}
          <div
            aria-hidden
            className="pointer-events-none absolute bottom-0 top-0 w-[2px] bg-gold"
            style={{ left: `${minTrust * 100}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between text-xs text-label">
          <span>0</span>
          <span className="text-gold">umbral de exportación {minTrust.toFixed(2)}</span>
          <span>1</span>
        </div>
        {hovered && (
          <div
            role="tooltip"
            className="bevel-8 pointer-events-none absolute right-0 top-0 border border-edge-strong bg-control p-3 text-xs text-ink-3"
          >
            Trust {range(hovered)}:{' '}
            <span className="font-mono text-ink">{formatNumber(hovered.count)}</span>
          </div>
        )}
      </div>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-ink-4">Ver como tabla</summary>
        <table className="mt-2 text-xs">
          <tbody>
            {bins.map((bin) => (
              <tr key={bin.from}>
                <td className="px-2 py-1 text-ink-4">{range(bin)}</td>
                <td className="px-2 py-1 text-right font-mono text-ink-3">{bin.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
