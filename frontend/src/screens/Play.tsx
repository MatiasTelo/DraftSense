/**
 * `/play` — el motor de tarjetas (`docs/30-ux-flujos.md` §5 y §8).
 *
 * Es la pantalla donde se pasa el 95 % del tiempo y el único camino por el que entran datos al
 * sistema. Tres cosas la gobiernan:
 *
 * 1. **Nada bloquea la siguiente tarjeta.** La cola se precarga sola; entre tarjeta y tarjeta no
 *    hay estado de carga visible (CA-501).
 * 2. **El doble toque no es un error.** El segundo envío devuelve `409 duplicate_response` y la
 *    interfaz avanza en silencio: el usuario no tiene que ver un error por tocar dos veces
 *    (CA-502).
 * 3. **Las respuestas no se encolan para envío diferido.** Si una no se registra, se pierde y se
 *    dice. Reintentar solo al recuperar la conexión arriesga duplicados y respuestas dadas en un
 *    contexto que ya pasó; con crudo append-only, un duplicado es peor que una pérdida (ADR-002).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import type { Answer, Feedback, Question } from '../api';
import { AppFrame } from '../components/AppFrame';
import { BottomNav, TopBar } from '../components/Chrome';
import { FeedbackOverlay } from '../components/FeedbackOverlay';
import { QuestionCard } from '../components/QuestionCard';
import { LanguageToggle } from '../components/LanguageToggle';
import { CardSkeleton, Countdown, RetryButton, StateCard } from '../components/States';
import { ApiError, NetworkError, postResponse } from '../lib/client';
import { useT } from '../store/lang';
import { useQueue } from '../store/queue';
import { useSession } from '../store/session';

/**
 * Cuánto dura la superposición de feedback si no se toca nada: 4 s desde el 07/11/2026 (ADR-030,
 * `docs/30-ux-flujos.md` §10). Un toque, `Enter` o `Espacio` la cierran antes.
 */
export const FEEDBACK_MS = 4000;

interface Shown {
  feedback: Feedback | null;
  labels: { key: string; label: string }[];
  yourKey: string;
  /** Tipo 5: los atributos que marcó. */
  yourKeys: string[];
  streak: number;
  unit?: string;
  layout: 'inline' | 'stacked';
}

/**
 * Las etiquetas de las barras del feedback.
 *
 * El servidor manda el consenso por clave (los niveles del tipo 3, las opciones del 4, los códigos
 * del 5); los textos están en la pregunta que el cliente ya tiene. No se compone ningún enunciado
 * acá: se lee el que vino. Los tipos 1 y 2 no tienen barras: el 1 informa en cuántos pares
 * coincide (ADR-022) y el 2, una mediana.
 */
function optionLabels(question: Question): { key: string; label: string }[] {
  switch (question.type) {
    case 'lane_matchup':
    case 'duo_synergy':
      return question.options.map(({ key, label }) => ({ key, label }));
    case 'trait_multiselect':
      return question.traits.map(({ code, label }) => ({ key: code, label }));
    case 'pairwise_dimension':
    case 'peak_timing':
      return [];
  }
}

/**
 * Las teclas eligen la opción en el orden de la tarjeta (§9), en los tipos que registran al primer
 * toque: `1`–`5` en el tipo 3 y `1`–`3` en el 4. Los tipos 1, 2 y 5 confirman con `Enter`, y eso lo
 * resuelve su propia tarjeta, que es la que conoce el orden, el valor del slider o la selección.
 */
function answerForDigit(question: Question, key: string): Answer | undefined {
  const index = Number.parseInt(key, 10) - 1;
  if (Number.isNaN(index)) return undefined;
  switch (question.type) {
    case 'lane_matchup': {
      const option = question.options[index];
      return option === undefined ? undefined : { choice: option.key };
    }
    case 'duo_synergy': {
      const option = question.options[index];
      return option === undefined ? undefined : { choice: option.key };
    }
    case 'pairwise_dimension':
    case 'peak_timing':
    case 'trait_multiselect':
      return undefined;
  }
}

function chosenKey(answer: Answer): string {
  return 'choice' in answer ? answer.choice : '';
}

function chosenKeys(answer: Answer): string[] {
  return 'traits' in answer ? answer.traits : [];
}

export function Play() {
  const questions = useQueue((state) => state.questions);
  const status = useQueue((state) => state.status);
  const queueError = useQueue((state) => state.error);
  const fetchMore = useQueue((state) => state.fetchMore);
  const advance = useQueue((state) => state.advance);

  const counters = useSession((state) => state.counters);
  const applyProgress = useSession((state) => state.applyProgress);
  const bootstrap = useSession((state) => state.bootstrap);
  const ready = useSession((state) => state.ready);

  const t = useT();
  const [helpOpen, setHelpOpen] = useState(false);
  const [shown, setShown] = useState<Shown | null>(null);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<ApiError | NetworkError | null>(null);
  const [cooldown, setCooldown] = useState<{ left: number; total: number } | null>(null);

  const question = questions[0];
  /** Cuándo se pintó la tarjeta. Es el origen de `response_time_ms` (RF-109). */
  const shownAt = useRef(0);
  /**
   * Candado sincrónico contra el doble envío. El estado de React llega a los manejadores recién en
   * el render siguiente, y en ese intervalo un segundo toque —o `Enter` justo después de un clic—
   * pasaría la guarda. Se libera cuando cambia la tarjeta o cuando el envío falla y la tarjeta
   * queda para volver a intentar.
   */
  const inFlight = useRef(false);
  /**
   * Si el feedback que está en pantalla ya se cerró. El cierre llega por tres caminos —el tiempo,
   * un toque, una tecla— y dos pueden caer antes del render siguiente: sin este candado la cola
   * avanzaría dos veces y se saltearía una tarjeta sin mostrarla.
   */
  const dismissed = useRef(false);

  useEffect(() => {
    if (!ready) void bootstrap();
  }, [ready, bootstrap]);

  useEffect(() => {
    if (status === 'idle') void fetchMore();
  }, [status, fetchMore]);

  // Cada tarjeta arranca con la definición cerrada y el cronómetro en cero.
  useEffect(() => {
    setHelpOpen(false);
    setSendError(null);
    inFlight.current = false;
    shownAt.current = performance.now();
  }, [question?.question_id]);

  // La cuenta regresiva del 429, que se apaga sola.
  useEffect(() => {
    if (cooldown === null) return;
    if (cooldown.left <= 0) {
      setCooldown(null);
      return;
    }
    const timer = setTimeout(() => {
      setCooldown((current) => (current === null ? null : { ...current, left: current.left - 1 }));
    }, 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const submit = useCallback(
    async (answer: Answer) => {
      if (question === undefined || inFlight.current) return;
      if (sending || shown !== null || cooldown !== null) return;
      inFlight.current = true;
      let recorded = false;
      setSending(true);
      setSendError(null);
      try {
        const result = await postResponse({
          question_id: question.question_id,
          // El tipo 1 se contesta sobre el ranking servido, cuyo ancla es la pregunta (ADR-022).
          ...(question.type === 'pairwise_dimension' ? { ranking_id: question.ranking_id } : {}),
          answer,
          response_time_ms: Math.round(performance.now() - shownAt.current),
        });
        applyProgress(result.progress);
        dismissed.current = false;
        setShown({
          feedback: result.feedback,
          labels: optionLabels(question),
          yourKey: chosenKey(answer),
          yourKeys: chosenKeys(answer),
          streak: result.progress.current_streak,
          unit: question.type === 'peak_timing' ? question.slider.unit : undefined,
          layout: question.type === 'pairwise_dimension' ? 'inline' : 'stacked',
        });
        recorded = true;
      } catch (error) {
        if (error instanceof ApiError && error.code === 'duplicate_response') {
          // CA-502 — carrera de doble toque. Se descarta en silencio y se sigue.
          advance();
        } else if (error instanceof ApiError && error.code === 'rate_limit_exceeded') {
          const seconds = error.retryAfter ?? 60;
          setCooldown({ left: seconds, total: seconds });
        } else if (error instanceof ApiError || error instanceof NetworkError) {
          setSendError(error);
        }
      } finally {
        // Registrada, la tarjeta se va y el candado se libera con la siguiente. Si no, queda.
        if (!recorded) inFlight.current = false;
        setSending(false);
      }
    },
    [question, sending, shown, cooldown, applyProgress, advance],
  );

  /** Cierra el feedback y entra la tarjeta siguiente. Una sola vez por feedback. */
  const dismiss = useCallback(() => {
    if (dismissed.current) return;
    dismissed.current = true;
    setShown(null);
    advance();
  }, [advance]);

  // La superposición dura 4 s y después entra la tarjeta siguiente (ADR-030).
  useEffect(() => {
    if (shown === null) return;
    const timer = setTimeout(dismiss, FEEDBACK_MS);
    return () => clearTimeout(timer);
  }, [shown, dismiss]);

  // `Enter` o `Espacio` la cierran antes (ADR-030). La tecla mantenida no cuenta: si no, un `Enter`
  // sostenido cerraría el feedback y confirmaría la tarjeta siguiente. Sobre un botón habilitado o
  // un enlace con foco, el navegador ya convierte la tecla en un clic de ese control y no se toca.
  // El *Confirm* que se acaba de tocar con el mouse queda con foco pero deshabilitado mientras dura
  // el feedback: ahí nadie hace clic, y sin el `:not(:disabled)` `Enter` no saltearía nada.
  useEffect(() => {
    if (shown === null) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const control = 'button:not(:disabled), a';
      if (event.target instanceof Element && event.target.closest(control) !== null) return;
      event.preventDefault();
      dismiss();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [shown, dismiss]);

  // Teclado en escritorio: 1–5 eligen opción, `?` abre la definición (§9).
  useEffect(() => {
    if (question === undefined) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === '?') {
        setHelpOpen((open) => !open);
        return;
      }
      // `onKeyDown` es una declaración y se eleva: TypeScript no arrastra el estrechamiento de
      // arriba hasta acá.
      if (question === undefined) return;
      const answer = answerForDigit(question, event.key);
      if (answer !== undefined) void submit(answer);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [question, submit]);

  return (
    <AppFrame>
      <TopBar
        streak={counters.current_streak}
        answers={counters.answers_count}
        middle={<LanguageToggle />}
      />

      <main className="relative flex flex-1 flex-col">
        {question !== undefined ? (
          // La `key` por pregunta desmonta la tarjeta anterior: el valor del slider del tipo 2 es
          // estado local y, sin esto, pasaría de un pico al siguiente.
          <QuestionCard
            key={question.question_id}
            question={question}
            helpOpen={helpOpen}
            onToggleHelp={() => setHelpOpen((open) => !open)}
            onAnswer={(answer) => void submit(answer)}
            disabled={sending || shown !== null || cooldown !== null}
          />
        ) : status === 'empty' ? (
          <div className="p-[22px]">
            <StateCard kind={t.play.emptyKind} title={t.play.emptyTitle}>
              <Link to="/me" className="font-mono text-[13px] font-medium text-gold">
                {t.play.seeProfile}
              </Link>
            </StateCard>
          </div>
        ) : status === 'error' ? (
          <div className="p-[22px]">
            <QueueProblem error={queueError} onRetry={() => void fetchMore()} />
          </div>
        ) : (
          <CardSkeleton />
        )}

        {/* Un fallo al enviar no borra la tarjeta: la respuesta se perdió, pero la pregunta sigue
            ahí y se puede volver a tocar. */}
        {sendError !== null && (
          <div className="px-[22px] pb-[22px]">
            <QueueProblem error={sendError} onRetry={() => setSendError(null)} />
          </div>
        )}

        {cooldown !== null && (
          <div className="px-[22px] pb-[22px]">
            <StateCard kind={t.play.rateKind} title={t.play.rateTitle(cooldown.left)}>
              <Countdown seconds={cooldown.left} total={cooldown.total} />
            </StateCard>
          </div>
        )}

        {shown !== null && (
          <FeedbackOverlay
            feedback={shown.feedback}
            labels={shown.labels}
            yourKey={shown.yourKey}
            yourKeys={shown.yourKeys}
            streak={shown.streak}
            unit={shown.unit}
            layout={shown.layout}
            onDismiss={dismiss}
          />
        )}
      </main>

      <BottomNav />
    </AppFrame>
  );
}

/**
 * Sin conexión contra base caída.
 *
 * Se ramifica por el tipo de error y no por el status, porque son dos mensajes distintos: uno dice
 * que la respuesta no se guardó, el otro que el problema es nuestro (§8).
 */
function QueueProblem({
  error,
  onRetry,
}: {
  error: ApiError | NetworkError | null;
  onRetry: () => void;
}) {
  const t = useT();
  const offline = error instanceof NetworkError || !navigator.onLine;
  return offline ? (
    <StateCard kind={t.play.offlineKind} title={t.play.offlineTitle}>
      <RetryButton onClick={onRetry} />
    </StateCard>
  ) : (
    <StateCard kind={t.play.serverKind} title={t.play.serverTitle}>
      <RetryButton onClick={onRetry} />
    </StateCard>
  );
}
