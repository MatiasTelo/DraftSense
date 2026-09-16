/**
 * La cola de preguntas y su precarga.
 *
 * **Nada bloquea la siguiente tarjeta** (`docs/30-ux-flujos.md` §1). La cola vive en memoria y se
 * rellena cuando quedan `PREFETCH_AT` preguntas, no cuando se vacía: pedir al servidor recién
 * cuando no queda ninguna es exactamente el estado de carga visible que CA-501 prohíbe.
 *
 * La cola no se persiste. Al recargar se pide un lote nuevo, que es lo correcto: las preguntas
 * pueden haber cambiado de parche y una respuesta dada sobre una tarjeta vieja sería un dato
 * fechado mal.
 */

import { create } from 'zustand';

import type { Question } from '../api';
import { ApiError, NetworkError, fetchQuestions } from '../lib/client';

/** Con cuántas preguntas restantes se pide el próximo lote. */
export const PREFETCH_AT = 2;

/** Cuántas se piden por vez. El contrato admite de 1 a 10 (`docs/12-api.md` §2.3). */
export const BATCH_SIZE = 5;

export type QueueStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

interface QueueState {
  questions: Question[];
  status: QueueStatus;
  error: ApiError | NetworkError | null;
  fetchMore: () => Promise<void>;
  /** Descarta la pregunta de adelante y precarga si hace falta. */
  advance: () => void;
  reset: () => void;
}

/**
 * Impide dos lotes en vuelo a la vez.
 *
 * Sin esto, responder rápido dispara una precarga por respuesta y la cola se llena de duplicados
 * que el servidor tuvo que materializar para nada.
 */
let inFlight: Promise<void> | null = null;

export const useQueue = create<QueueState>((set, get) => ({
  questions: [],
  status: 'idle',
  error: null,

  fetchMore() {
    inFlight ??= (async () => {
      set((state) => ({ status: state.questions.length === 0 ? 'loading' : state.status }));
      try {
        const batch = await fetchQuestions(BATCH_SIZE);
        set((state) => {
          // El servidor no repite dentro de un lote, pero sí puede devolver algo que ya está en
          // la cola local si dos precargas se cruzaron. Deduplicar acá es barato y evita que el
          // usuario vea la misma tarjeta dos veces.
          const known = new Set(state.questions.map((q) => q.question_id));
          const fresh = batch.questions.filter((q) => !known.has(q.question_id));
          const questions = [...state.questions, ...fresh];
          return {
            questions,
            error: null,
            status: questions.length === 0 ? 'empty' : 'ready',
          };
        });
      } catch (error) {
        set((state) => ({
          // Un fallo de precarga con la cola todavía llena no es un error para el usuario: sigue
          // respondiendo y el próximo intento lo resuelve. Sólo se muestra si no queda nada.
          status: state.questions.length === 0 ? 'error' : state.status,
          error: error instanceof ApiError || error instanceof NetworkError ? error : null,
        }));
      } finally {
        inFlight = null;
      }
    })();
    return inFlight;
  },

  advance() {
    const remaining = get().questions.slice(1);
    set({ questions: remaining, status: remaining.length === 0 ? 'loading' : 'ready' });
    if (remaining.length <= PREFETCH_AT) void get().fetchMore();
  },

  reset() {
    inFlight = null;
    set({ questions: [], status: 'idle', error: null });
  },
}));
