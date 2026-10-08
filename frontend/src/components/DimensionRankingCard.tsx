/**
 * Tipo 1 — ranking de cinco campeones por dimensión (`docs/20-tipos-de-pregunta.md` §2, ADR-022).
 *
 * Es el 50 % de la sesión y la fuente de `champion_dimensions.csv`. La persona ordena los cinco de
 * más a menos arrastrándolos, y el servidor guarda las diez comparaciones que ese orden implica.
 *
 * **Necesita confirmación explícita**, como los tipos 2 y 5: un ranking no tiene un «primer toque»
 * que valga como respuesta (`docs/30-ux-flujos.md` §10). Registra *Confirm*, o `Enter` en
 * escritorio cuando el foco no está sobre una fila.
 *
 * Los campeones llegan en orden aleatorio y la lista arranca en ese orden. Confirmar sin mover nada
 * es una respuesta válida; la delata el `response_time_ms` bajo, no la interfaz.
 *
 * `Not sure` vale para el ranking entero: su tasa por campeón se exporta como `unknown_rate` y dice
 * que la dimensión no aplica bien a esos campeones. Por eso ocupa lugar en la tarjeta en vez de
 * resolverse salteando.
 *
 * El arrastre es de `@dnd-kit`: funciona con el dedo, con el mouse y con el teclado (espacio para
 * tomar una fila, flechas para moverla, espacio para soltarla), que es lo que pide §9.
 */

import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useEffect, useState } from 'react';

import type { ChampionRef, PairwiseDimensionQuestion } from '../api';
import { PrimaryButton } from './Button';
import { ChampionPortrait } from './ChampionPortrait';
import { QuestionPrompt } from './QuestionPrompt';

export type RankingAnswer = { order: number[] } | { choice: 'unknown' };

interface Props {
  question: PairwiseDimensionQuestion;
  helpOpen: boolean;
  onToggleHelp: () => void;
  onAnswer: (answer: RankingAnswer) => void;
  disabled: boolean;
}

export function DimensionRankingCard({
  question,
  helpOpen,
  onToggleHelp,
  onAnswer,
  disabled,
}: Props) {
  const [order, setOrder] = useState<ChampionRef[]>(question.champions);

  const sensors = useSensors(
    // Unos píxeles de margen para que un toque no se lea como arrastre.
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 80, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function onDragEnd({ active, over }: DragEndEvent) {
    if (over === null || active.id === over.id) return;
    setOrder((current) => {
      const from = current.findIndex((c) => c.id === active.id);
      const to = current.findIndex((c) => c.id === over.id);
      return arrayMove(current, from, to);
    });
  }

  // `Enter` confirma (§9), salvo sobre una fila o un botón: ahí `Enter` es de `@dnd-kit` o ya es
  // un clic, y confirmar también acá mandaría la respuesta dos veces.
  useEffect(() => {
    if (disabled) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Enter' || event.repeat) return;
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (
        event.target instanceof Element &&
        event.target.closest('button, a, [role="button"]') !== null
      )
        return;
      event.preventDefault();
      onAnswer({ order: order.map((c) => c.id) });
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [disabled, order, onAnswer]);

  return (
    <div className="flex flex-1 flex-col px-[22px] py-[26px]">
      <QuestionPrompt
        prompt={question.prompt}
        subtitle={question.instruction}
        help={question.help}
        open={helpOpen}
        onToggle={onToggleHelp}
      />

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={order.map((c) => c.id)} strategy={verticalListSortingStrategy}>
          <ol aria-label={question.prompt} className="flex flex-1 flex-col justify-center gap-2 py-5">
            {order.map((champion, index) => (
              <RankRow key={champion.id} champion={champion} rank={index + 1} disabled={disabled} />
            ))}
          </ol>
        </SortableContext>
      </DndContext>

      <div className="flex gap-3">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onAnswer({ choice: 'unknown' })}
          className="flex h-[54px] w-2/5 shrink-0 items-center justify-center border border-white/12 text-[13px] font-medium tracking-[0.04em] text-mute hover:text-ink-3 disabled:opacity-60"
        >
          {question.unknown_label}
        </button>
        <PrimaryButton
          onClick={() => onAnswer({ order: order.map((c) => c.id) })}
          disabled={disabled}
        >
          Confirm
        </PrimaryButton>
      </div>
    </div>
  );
}

/**
 * Una fila de la lista: posición, retrato, nombre y la marca de arrastre.
 *
 * Toda la fila es el asa y no sólo el `≡`: a 360 px el asa sola quedaría por debajo de los 44 px de
 * área táctil. `touch-none` evita que el navegador interprete el arrastre como scroll.
 */
function RankRow({
  champion,
  rank,
  disabled,
}: {
  champion: ChampionRef;
  rank: number;
  disabled: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: champion.id,
    disabled,
  });

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      {...attributes}
      {...listeners}
      aria-label={`${rank}. ${champion.name}`}
      className={`flex h-[52px] touch-none items-center gap-3 border bg-panel px-3 select-none ${
        isDragging ? 'z-10 border-gold' : 'border-white/7'
      } ${disabled ? 'opacity-60' : 'cursor-grab active:cursor-grabbing'}`}
    >
      <span className="w-5 shrink-0 text-center font-mono text-sm font-semibold text-gold">
        {rank}
      </span>
      <ChampionPortrait champion={champion} size={40} bevel="bevel-12" />
      <span className="min-w-0 flex-1 truncate font-display text-base font-semibold tracking-[0.04em] text-ink">
        {champion.name}
      </span>
      <span aria-hidden="true" className="shrink-0 text-lg text-mute">
        ≡
      </span>
    </li>
  );
}
