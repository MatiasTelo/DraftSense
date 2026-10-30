/**
 * Tipo 5 — multi-selección de atributos (`docs/20-tipos-de-pregunta.md` §6).
 *
 * El retrato, el nombre y los siete atributos en una grilla de dos columnas; el último, si queda
 * solo, va a lo ancho. Cada atributo es un botón de alternar (`aria-pressed`) con su propia
 * definición a un toque, que viene de la tabla `traits` (CA-506).
 *
 * **Hay que marcar al menos uno** ([ADR-027]): *Confirm* está deshabilitado con la lista vacía y
 * `Enter` no envía nada (CA-509). Las teclas `1`–`7` marcan y desmarcan en el orden de la grilla
 * (`docs/30-ux-flujos.md` §9, nota del 29/10). Los dos atajos los maneja la tarjeta, que es la que
 * conoce la selección.
 */

import { useEffect, useState } from 'react';

import type { TraitMultiselectQuestion } from '../api';
import { useT } from '../store/lang';
import { PrimaryButton } from './Button';
import { ChampionPortrait } from './ChampionPortrait';
import { QuestionPrompt } from './QuestionPrompt';

/** La selección con `code` agregado o quitado. */
function toggled(current: string[], code: string): string[] {
  return current.includes(code) ? current.filter((c) => c !== code) : [...current, code];
}

interface Props {
  question: TraitMultiselectQuestion;
  onConfirm: (traits: string[]) => void;
  disabled: boolean;
}

export function TraitMultiselectCard({ question, onConfirm, disabled }: Props) {
  const t = useT();
  const champion = question.subject.champions[0];
  const [selected, setSelected] = useState<string[]>([]);
  /** El atributo cuya definición está abierta. Una a la vez, debajo de la grilla. */
  const [helpFor, setHelpFor] = useState<string | null>(null);

  // Se envían en el orden de la grilla, no en el orden en que se tocaron.
  const chosen = question.traits.map((trait) => trait.code).filter((c) => selected.includes(c));

  useEffect(() => {
    if (disabled) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey || event.repeat) return;
      const index = Number.parseInt(event.key, 10) - 1;
      const trait = Number.isNaN(index) ? undefined : question.traits[index];
      if (trait !== undefined) {
        setSelected((current) => toggled(current, trait.code));
        return;
      }
      if (event.key !== 'Enter' || event.shiftKey) return;
      // El botón con foco ya convierte `Enter` en un clic: confirmar también acá enviaría dos
      // veces, o alternaría un atributo y enviaría a la vez.
      if (event.target instanceof Element && event.target.closest('button, a') !== null) return;
      event.preventDefault();
      if (chosen.length > 0) onConfirm(chosen);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [disabled, chosen, question.traits, onConfirm]);

  const open = question.traits.find((trait) => trait.code === helpFor);
  const odd = question.traits.length % 2 === 1;

  return (
    <div className="flex flex-1 flex-col px-[22px] py-[22px]">
      <QuestionPrompt
        prompt={question.prompt}
        subtitle={question.subtitle}
        help={question.help}
        open={false}
        onToggle={() => undefined}
        size="text-[25px]"
      />

      <div className="flex flex-col items-center gap-1.5 py-4">
        {champion !== undefined && (
          <>
            <ChampionPortrait champion={champion} size={72} bevel="bevel-12" />
            <span className="font-display text-base font-semibold tracking-[0.04em] text-ink">
              {champion.name}
            </span>
          </>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        {question.traits.map((trait, index) => {
          const pressed = selected.includes(trait.code);
          const wide = odd && index === question.traits.length - 1;
          return (
            <div
              key={trait.code}
              className={`flex border ${wide ? 'col-span-2' : ''} ${
                pressed ? 'border-gold bg-gold/12' : 'border-edge bg-control'
              }`}
            >
              <button
                type="button"
                aria-pressed={pressed}
                disabled={disabled}
                onClick={() => setSelected((current) => toggled(current, trait.code))}
                className={`flex min-h-[52px] flex-1 items-center gap-2 px-3 text-left text-[14px] leading-tight disabled:opacity-60 ${
                  pressed ? 'font-semibold text-gold-bright' : 'font-medium text-ink-3'
                }`}
              >
                <span aria-hidden="true" className="w-3 shrink-0 text-gold">
                  {pressed ? '✓' : ''}
                </span>
                {trait.label}
              </button>
              <button
                type="button"
                onClick={() => setHelpFor((current) => (current === trait.code ? null : trait.code))}
                aria-expanded={helpFor === trait.code}
                aria-label={t.play.whatItMeans(trait.label)}
                className={`flex w-11 shrink-0 items-center justify-center font-mono text-[13px] font-semibold ${
                  helpFor === trait.code ? 'text-cyan' : 'text-mute'
                }`}
              >
                ?
              </button>
            </div>
          );
        })}
      </div>

      {open !== undefined && (
        <p className="mt-3 border-l-2 border-cyan bg-control px-4 py-3 text-[13px] leading-relaxed text-ink-4">
          <span className="font-semibold text-ink-3">{open.label}.</span> {open.help}
        </p>
      )}

      <div className="flex-1" />
      <div className="pt-4">
        <PrimaryButton onClick={() => onConfirm(chosen)} disabled={disabled || chosen.length === 0}>
          {t.play.confirm}
        </PrimaryButton>
      </div>
    </div>
  );
}
