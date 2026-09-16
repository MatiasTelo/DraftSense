/**
 * La identidad del respondedor y sus contadores visibles.
 *
 * Lo único que se guarda acá es lo que más de una pantalla necesita: el landing decide entre
 * `Start` y `Continue` con `onboardingSeen`, y la barra superior de `/play` muestra la racha y el
 * total. Todo lo demás es estado local del componente.
 *
 * **La cookie `ds_session` no aparece por ningún lado y está bien así**: es `HttpOnly`, el cliente
 * no puede leerla, y la identidad la resuelve el servidor en cada petición (ADR-001).
 */

import { create } from 'zustand';

import type { Progress, SessionResponse } from '../api';
import { createSession } from '../lib/client';

/** Lo que se muestra. Es el subconjunto común entre `SessionResponse` y `Progress`. */
export interface Counters {
  answers_count: number;
  current_streak: number;
  best_streak: number;
  current_day_streak: number;
  best_day_streak: number;
}

const ZERO: Counters = {
  answers_count: 0,
  current_streak: 0,
  best_streak: 0,
  current_day_streak: 0,
  best_day_streak: 0,
};

interface SessionState {
  respondentId: string | null;
  onboardingSeen: boolean;
  counters: Counters;
  /** `false` hasta que `bootstrap()` contestó. El landing no decide el botón antes de eso. */
  ready: boolean;
  bootstrap: () => Promise<void>;
  markOnboardingSeen: () => void;
  applyProgress: (progress: Progress) => void;
}

function counters(source: SessionResponse | Progress): Counters {
  return {
    answers_count: source.answers_count,
    current_streak: source.current_streak,
    best_streak: source.best_streak,
    current_day_streak: source.current_day_streak,
    best_day_streak: source.best_day_streak,
  };
}

export const useSession = create<SessionState>((set) => ({
  respondentId: null,
  onboardingSeen: false,
  counters: ZERO,
  ready: false,

  async bootstrap() {
    try {
      const session = await createSession();
      set({
        respondentId: session.respondent_id,
        onboardingSeen: session.onboarding_seen,
        counters: counters(session),
        ready: true,
      });
    } catch {
      // Que falle no bloquea nada: los endpoints crean la sesión al vuelo, así que el usuario
      // puede jugar igual. Se marca listo para no dejar el landing colgado en el esqueleto.
      set({ ready: true });
    }
  },

  markOnboardingSeen() {
    set({ onboardingSeen: true });
  },

  applyProgress(progress) {
    set({ counters: counters(progress) });
  },
}));
