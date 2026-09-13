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
import { CardSkeleton, Countdown, RetryButton, StateCard } from '../components/States';
import { ApiError, NetworkError, postResponse } from '../lib/client';
import { useQueue } from '../store/queue';
import { useSession } from '../store/session';

/** Cuánto dura la superposición de feedback. Ver `docs/30-ux-flujos.md` §10. */
const FEEDBACK_MS = 1200;

interface Shown {
  feedback: Feedback | null;
  labels: { key: string; label: string }[];
  yourKey: string;
  streak: number;
}

/**
 * Las etiquetas de las barras del feedback.
 *
 * El servidor manda el consenso por clave (`a`, `b`, `unknown`); los nombres están en la pregunta
 * que el cliente ya tiene. No se compone ningún enunciado acá: se lee el que vino.
 */
function optionLabels(question: Question): { key: string; label: string }[] {
  if (question.type !== 'pairwise_dimension') return [];
  return question.options.map((option) => ({
    key: option.key,
    label: option.champions[0]?.name ?? option.label ?? option.key,
  }));
}

function chosenKey(answer: Answer): string {
  return 'choice' in answer ? answer.choice : '';
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

  const [helpOpen, setHelpOpen] = useState(false);
  const [shown, setShown] = useState<Shown | null>(null);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<ApiError | NetworkError | null>(null);
  const [cooldown, setCooldown] = useState<{ left: number; total: number } | null>(null);

  const question = questions[0];
  /** Cuándo se pintó la tarjeta. Es el origen de `response_time_ms` (RF-109). */
  const shownAt = useRef(0);

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
      if (question === undefined || sending || shown !== null || cooldown !== null) return;
      setSending(true);
      setSendError(null);
      try {
        const recorded = await postResponse({
          question_id: question.question_id,
          answer,
          response_time_ms: Math.round(performance.now() - shownAt.current),
        });
        applyProgress(recorded.progress);
        setShown({
          feedback: recorded.feedback,
          labels: optionLabels(question),
          yourKey: chosenKey(answer),
          streak: recorded.progress.current_streak,
        });
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
        setSending(false);
      }
    },
    [question, sending, shown, cooldown, applyProgress, advance],
  );

  // La superposición dura 1,2 s y después entra la tarjeta siguiente.
  useEffect(() => {
    if (shown === null) return;
    const timer = setTimeout(() => {
      setShown(null);
      advance();
    }, FEEDBACK_MS);
    return () => clearTimeout(timer);
  }, [shown, advance]);

  // Teclado en escritorio: 1–5 eligen opción, `?` abre la definición (§9).
  useEffect(() => {
    if (question === undefined) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === '?') {
        setHelpOpen((open) => !open);
        return;
      }
      if (question?.type !== 'pairwise_dimension') return;
      const index = Number.parseInt(event.key, 10) - 1;
      const option = question.options[index];
      if (option !== undefined) void submit({ choice: option.key as 'a' | 'b' | 'unknown' });
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [question, submit]);

  return (
    <AppFrame>
      <TopBar streak={counters.current_streak} answers={counters.answers_count} />

      <main className="relative flex flex-1 flex-col">
        {question !== undefined ? (
          <QuestionCard
            question={question}
            helpOpen={helpOpen}
            onToggleHelp={() => setHelpOpen((open) => !open)}
            onAnswer={(answer) => void submit(answer)}
            disabled={sending || shown !== null || cooldown !== null}
          />
        ) : status === 'empty' ? (
          <div className="p-[22px]">
            <StateCard
              kind="Nothing to ask"
              title="Nothing left to ask right now. Come back after the next patch."
            >
              <Link to="/me" className="font-mono text-[13px] font-medium text-gold">
                See your profile →
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
            <StateCard
              kind="Rate limit"
              title={`Slow down a little — try again in ${cooldown.left} seconds.`}
            >
              <Countdown seconds={cooldown.left} total={cooldown.total} />
            </StateCard>
          </div>
        )}

        {shown !== null && (
          <FeedbackOverlay
            feedback={shown.feedback}
            labels={shown.labels}
            yourKey={shown.yourKey}
            streak={shown.streak}
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
  const offline = error instanceof NetworkError || !navigator.onLine;
  return offline ? (
    <StateCard kind="Offline" title="You're offline. Your last answer wasn't saved.">
      <RetryButton onClick={onRetry} />
    </StateCard>
  ) : (
    <StateCard kind="Server" title="Something broke on our end. Try again in a minute.">
      <RetryButton onClick={onRetry} />
    </StateCard>
  );
}
