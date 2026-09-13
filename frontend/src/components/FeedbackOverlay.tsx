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
 */

import type { Feedback } from '../api';

interface Props {
  /** `null` mientras la pregunta tiene menos respuestas que el umbral de consenso. */
  feedback: Feedback | null;
  /** Etiqueta visible de cada opción: para el tipo 1, los dos nombres y `Not sure`. */
  labels: { key: string; label: string }[];
  /** La opción que eligió esta persona. */
  yourKey: string;
  /** Racha de respuestas seguidas, ya actualizada con esta respuesta. */
  streak: number;
}

const percent = (share: number) => Math.round(share * 100);

export function FeedbackOverlay({ feedback, labels, yourKey, streak }: Props) {
  const consensus = feedback?.consensus;
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
        </div>

        {consensus !== undefined && (
          <div className="flex flex-col gap-3 border border-white/7 bg-panel px-[18px] py-5">
            {labels.map(({ key, label }) => {
              const share = consensus[key] ?? 0;
              // La barra dorada es la del usuario, no la de la mayoría: es de la que habla el
              // mensaje, y en el caso de discrepancia es la que hay que poder encontrar.
              const mine = key === yourKey;
              return (
                <div key={key} className="flex items-center gap-2.5">
                  <span className={`w-[78px] text-[13px] font-medium ${mine ? 'text-ink' : 'text-ink-4'}`}>
                    {label}
                  </span>
                  <span className="h-2 flex-1 bg-rail">
                    <span
                      style={{ width: `${percent(share)}%` }}
                      className={`block h-2 ${mine ? 'bg-gold' : 'bg-inert'}`}
                    />
                  </span>
                  {/* El porcentaje va escrito además de dibujado: el color nunca es el único
                      portador de información (§9). */}
                  <span
                    className={`w-[38px] text-right font-mono text-xs font-medium ${mine ? 'text-gold' : 'text-mute'}`}
                  >
                    {percent(share)}%
                  </span>
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
