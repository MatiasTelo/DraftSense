/**
 * El feedback post-respuesta — `docs/30-ux-flujos.md` §5.1.
 *
 * **Este es el gancho de retención principal.** La comparación con el consenso es lo que convierte
 * responder preguntas en algo con recompensa inmediata, y es la razón por la que alguien contesta
 * 40 en vez de 5. Dura 1,2 segundos: suficiente para leer el porcentaje, corto para no romper el
 * ritmo.
 *
 * Dos textos que no se tocan:
 *
 * - Con menos de 20 respuestas no se muestra consenso sino *«You're one of the first to answer
 *   this»*. No es un estado vacío disfrazado: mostrar una distribución sobre cinco respuestas
 *   anclaría a los primeros usuarios sobre ruido, y durante los primeros días **todas** las
 *   preguntas caen ahí (ADR-012, RF-114).
 * - La discrepancia se dice *«You're in the 19%»*, **sin ninguna connotación de error**. No hay
 *   respuesta correcta: la discrepancia es el dato, no una falla del usuario. Decir «wrong»
 *   arruinaría la motivación y la calidad de las respuestas siguientes.
 *
 * El tipo 2 no tiene opciones sino un minuto, y su consenso es la mediana: se informa con una
 * frase —*«Most players said 26 min. You said 27.»*— y sin barras.
 */

import type { Feedback } from '../api';

interface Props {
  /** `null` mientras la pregunta tiene menos respuestas que el umbral de consenso. */
  feedback: Feedback | null;
  /** Etiqueta visible de cada opción, en el orden de la tarjeta. Vacío en el tipo 2. */
  labels: { key: string; label: string }[];
  /** La opción que eligió esta persona. */
  yourKey: string;
  /** Racha de respuestas seguidas, ya actualizada con esta respuesta. */
  streak: number;
  /** La unidad de la escala del tipo 2, tal como la manda el servidor. */
  unit?: string;
  /**
   * `inline` pone etiqueta, barra y porcentaje en una fila, como en el maquetado del tipo 1.
   * `stacked` pone la barra debajo de la etiqueta: las del tipo 3 —«Nunu & Willump wins
   * slightly»— no entran en una columna de ancho fijo a 360 px.
   */
  layout?: 'inline' | 'stacked';
}

const percent = (share: number) => Math.round(share * 100);

export function FeedbackOverlay({
  feedback,
  labels,
  yourKey,
  streak,
  unit = '',
  layout = 'inline',
}: Props) {
  // `?? undefined` también absorbe un `null`: el contrato omite las claves que no aplican, pero
  // una clave nula no puede romper la tarjeta que sigue.
  const consensus = feedback?.consensus ?? undefined;
  const median = feedback?.consensus_median ?? undefined;
  const yourShare = consensus?.[yourKey] ?? 0;
  const milestone = streak > 0 && streak % 10 === 0;

  return (
    <div
      role="status"
      className="absolute inset-0 flex items-center justify-center bg-[rgb(6_8_11/0.94)] p-[22px]"
    >
      <div className="flex w-full flex-col gap-[22px]">
        <div className="flex flex-col items-center gap-2.5">
          {milestone && (
            <p className="font-mono text-xs font-semibold tracking-[0.2em] text-gold uppercase">
              {streak} in a row 🔥
            </p>
          )}

          {feedback === null ? (
            <p className="flex items-center gap-3 text-center font-display text-[22px] leading-snug font-semibold text-ink">
              <span className="text-[19px] text-cyan">⚡</span>
              You&apos;re one of the first to answer this
            </p>
          ) : median !== undefined ? (
            <p className="text-center font-display text-[22px] leading-snug font-semibold text-ink">
              Most players said {median} {unit}. You said {feedback.your_answer}.
            </p>
          ) : feedback.agreed_with_majority === true ? (
            <p className="flex items-center gap-2.5 font-display text-[22px] font-semibold text-ink">
              <span className="text-green">✓</span>
              {percent(yourShare)}% agree with you
            </p>
          ) : (
            <p className="font-display text-[22px] font-semibold text-ink">
              You&apos;re in the {percent(yourShare)}%
            </p>
          )}

          {median !== undefined && (
            <p className="font-mono text-[11px] tracking-[0.14em] text-faint uppercase">
              {feedback?.sample_size} answers
            </p>
          )}
        </div>

        {consensus !== undefined && median === undefined && (
          <div className="flex flex-col gap-3 border border-white/7 bg-panel px-[18px] py-5">
            {labels.map(({ key, label }) => {
              const share = consensus[key] ?? 0;
              // La barra dorada es la del usuario, no la de la mayoría: es de la que habla el
              // mensaje, y en el caso de discrepancia es la que hay que poder encontrar.
              const mine = key === yourKey;
              const bar = (
                <span className={`h-2 bg-rail ${layout === 'inline' ? 'flex-1' : 'block'}`}>
                  <span
                    style={{ width: `${percent(share)}%` }}
                    className={`block h-2 ${mine ? 'bg-gold' : 'bg-inert'}`}
                  />
                </span>
              );
              // El porcentaje va escrito además de dibujado: el color nunca es el único
              // portador de información (§9).
              const value = (
                <span
                  className={`w-[38px] shrink-0 text-right font-mono text-xs font-medium ${mine ? 'text-gold' : 'text-mute'}`}
                >
                  {percent(share)}%
                </span>
              );
              const text = `text-[13px] font-medium ${mine ? 'text-ink' : 'text-ink-4'}`;

              return layout === 'inline' ? (
                <div key={key} className="flex items-center gap-2.5">
                  <span className={`w-[78px] ${text}`}>{label}</span>
                  {bar}
                  {value}
                </div>
              ) : (
                <div key={key} className="flex flex-col gap-1.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className={`min-w-0 leading-snug ${text}`}>{label}</span>
                    {value}
                  </div>
                  {bar}
                </div>
              );
            })}
            <p className="mt-1.5 text-center font-mono text-[11px] tracking-[0.14em] text-faint uppercase">
              {feedback?.sample_size} answers
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
