/**
 * Tipo 2 — slider de pico de poder (`docs/20-tipos-de-pregunta.md` §3).
 *
 * Es el único tipo, junto al 5, que **necesita confirmación explícita**: un slider no tiene un
 * «primer toque» que valga como respuesta (`docs/30-ux-flujos.md` §10). Moverlo no registra nada;
 * registra *Confirm*, o `Enter` en escritorio (§9).
 *
 * El slider arranca en el valor que manda el servidor —el centro de la escala— y confirmar sin
 * moverlo es una respuesta válida: la delata el `response_time_ms` bajo, no la interfaz. Por eso
 * *Confirm* está habilitado desde el principio.
 *
 * El valor del slider es estado de esta tarjeta y vive sólo hasta que se confirma. `Play` monta
 * cada tarjeta con `key` por pregunta: sin eso, dos picos seguidos compartirían el valor.
 */

import { useEffect, useState, type CSSProperties } from 'react';

import type { PeakTimingQuestion } from '../api';
import { PrimaryButton } from './Button';
import { ChampionPortrait } from './ChampionPortrait';
import { QuestionPrompt } from './QuestionPrompt';

interface Props {
  question: PeakTimingQuestion;
  helpOpen: boolean;
  onToggleHelp: () => void;
  onConfirm: (minute: number) => void;
  disabled: boolean;
}

/** Posición de un valor sobre la pista, en porcentaje. */
function position(value: number, min: number, max: number): number {
  return max > min ? ((value - min) / (max - min)) * 100 : 0;
}

/** Las marcas de los extremos se alinean a su borde para no salirse de la tarjeta. */
function alignment(at: number): string {
  if (at <= 0) return 'items-start';
  if (at >= 100) return 'items-end';
  return 'items-center';
}

export function PeakTimingCard({ question, helpOpen, onToggleHelp, onConfirm, disabled }: Props) {
  const { slider } = question;
  const champion = question.subject.champions[0];
  const [minute, setMinute] = useState(slider.default);

  // `Enter` confirma (§9). El `button` o el enlace con foco ya lo convierte en un clic: confirmar
  // también acá mandaría la respuesta dos veces, y el segundo envío saltearía una tarjeta.
  useEffect(() => {
    if (disabled) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Enter' || event.repeat) return;
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.target instanceof Element && event.target.closest('button, a') !== null) return;
      event.preventDefault();
      onConfirm(minute);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [disabled, minute, onConfirm]);

  // El extremo derecho lleva su número aunque el servidor no lo marque, como en el maquetado.
  const ticks = slider.marks.some((mark) => mark.at === slider.max)
    ? slider.marks
    : [...slider.marks, { at: slider.max, label: '' }];

  const fill = { '--fill': `${position(minute, slider.min, slider.max)}%` } as CSSProperties;

  return (
    <div className="flex flex-1 flex-col px-[22px] py-[30px]">
      <QuestionPrompt
        prompt={question.prompt}
        help={question.help}
        open={helpOpen}
        onToggle={onToggleHelp}
      />

      <div className="flex flex-1 flex-col items-center justify-center gap-3 py-5">
        {champion !== undefined && (
          <>
            <ChampionPortrait champion={champion} size={112} bevel="bevel-14" />
            <span className="font-display text-lg font-semibold tracking-[0.04em] text-ink">
              {champion.name}
            </span>
          </>
        )}
      </div>

      <div className="flex flex-col pb-6">
        {/* El input ya anuncia su valor con `aria-valuetext`: esta lectura es para la vista. */}
        <p
          aria-hidden="true"
          className="text-center font-display text-[26px] leading-none font-semibold text-gold"
        >
          {minute} <span className="text-base text-gold/80">{slider.unit}</span>
        </p>
        <input
          type="range"
          min={slider.min}
          max={slider.max}
          step={slider.step}
          value={minute}
          disabled={disabled}
          onChange={(event) => setMinute(Number(event.target.value))}
          aria-label={question.prompt}
          aria-valuetext={`${minute} ${slider.unit}`}
          style={fill}
          className="range-slider w-full"
        />
        <div className="relative h-9">
          {ticks.map((tick) => {
            const at = position(tick.at, slider.min, slider.max);
            return (
              <span
                key={tick.at}
                style={{ left: `${at}%`, transform: `translateX(-${at}%)` }}
                className={`absolute top-0 flex flex-col whitespace-nowrap ${alignment(at)}`}
              >
                <span className="font-mono text-[11px] text-mute">{tick.at}</span>
                {tick.label !== '' && (
                  <span className="text-[11px] tracking-[0.04em] text-faint">{tick.label}</span>
                )}
              </span>
            );
          })}
        </div>
      </div>

      <PrimaryButton onClick={() => onConfirm(minute)} disabled={disabled}>
        Confirm
      </PrimaryButton>
    </div>
  );
}
