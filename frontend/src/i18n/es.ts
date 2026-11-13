/**
 * El microcopy en español (ADR-028), aprobado por el alumno el 29/10/2026: español neutro con
 * «tú». Los términos del juego quedan en inglés (ADR-010).
 *
 * Tipado contra `Messages`: si falta un texto o cambia un parámetro, no compila.
 */

import type { Messages } from './en';

export const es: Messages = {
  language: 'Idioma',

  landing: {
    headline: 'Ayuda a clasificar a cada campeón de League of Legends.',
    promise: 'Preguntas rápidas. Sin cuenta. 2 minutos.',
    start: 'Empezar',
    continue: 'Continuar',
    research: 'Tus respuestas alimentan una investigación pública de la UTN Mendoza.',
    about: 'Acerca de',
    privacy: 'Privacidad',
  },

  onboarding: {
    title: 'Un poco sobre ti',
    skip: 'Saltar',
    why: 'Opcional. Nos ayuda a comparar respuestas entre niveles de juego.',
    rank: 'Tu rango',
    ranks: {
      iron: 'Hierro',
      bronze: 'Bronce',
      silver: 'Plata',
      gold: 'Oro',
      platinum: 'Platino',
      emerald: 'Esmeralda',
      diamond: 'Diamante',
      master: 'Maestro',
      grandmaster: 'Gran Maestro',
      challenger: 'Retador',
      unranked: 'No juego clasificatorias',
    },
    role: 'Rol principal',
    roles: { top: 'Top', jungle: 'Jungla', mid: 'Mid', adc: 'Bot', support: 'Support' },
    hours: 'Horas por semana',
    browser: 'Tu progreso se guarda en este navegador.',
    continue: 'Continuar',
  },

  play: {
    confirm: 'Confirmar',
    whatItMeans: (label: string) => `Qué significa ${label.toLowerCase()}`,
    versus: 'vs',
    emptyKind: 'Nada para preguntar',
    emptyTitle: 'No queda nada para preguntar por ahora. Vuelve después del próximo parche.',
    seeProfile: 'Ver tu perfil →',
    rateKind: 'Límite de velocidad',
    rateTitle: (seconds: number) => `Más despacio — vuelve a intentarlo en ${seconds} segundos.`,
    offlineKind: 'Sin conexión',
    offlineTitle: 'Estás sin conexión. Tu última respuesta no se guardó.',
    serverKind: 'Servidor',
    serverTitle: 'Algo falló de nuestro lado. Inténtalo de nuevo en un minuto.',
    retry: 'Reintentar',
  },

  feedback: {
    inARow: (streak: number) => `${streak} seguidas 🔥`,
    firstTitle: 'Eres de los primeros en responder esto',
    firstBody: 'Todavía no hay suficientes respuestas para mostrar cómo se compara la comunidad.',
    pairs: (agreed: number, compared: number) =>
      `Coincides con la comunidad en ${agreed} de ${compared} ${compared === 1 ? 'par' : 'pares'}`,
    traits: (agreed: number, compared: number) =>
      `Coincides con la comunidad en ${agreed} de ${compared} ${compared === 1 ? 'atributo' : 'atributos'}`,
    median: (median: number, unit: string, yours: number | undefined) =>
      `La mayoría dijo ${median} ${unit}. Tú dijiste ${yours ?? ''}.`,
    agree: (percent: number) => `El ${percent}% coincide contigo`,
    minority: (percent: number) => `Estás en el ${percent}%`,
    answers: (count: number | undefined) => `${count ?? ''} respuestas`,
  },

  chrome: {
    answered: (count: number) => `${count} respondidas`,
    play: 'Jugar',
    profile: 'Perfil',
    ranks: 'Ranking',
  },

  profile: {
    answers: 'respuestas',
    streak: 'racha',
    best: 'mejor',
    daysInARow: (days: number) =>
      days === 1 ? '🔥 1 día seguido' : `🔥 ${days} días seguidos`,
    bestDays: (days: number) => `mejor: ${days} ${days === 1 ? 'día' : 'días'}`,
    agreementBefore: 'Coincides con la comunidad el',
    agreementAfter: 'de las veces',
    topBefore: 'Top',
    topAfter: 'de quienes participan',
    answered: 'Lo que respondiste',
    coverage: {
      pairwise_dimension: 'Rankings de campeones',
      peak_timing: 'Power spikes',
      lane_matchup: 'Enfrentamientos de línea',
      duo_synergy: 'Duplas',
      trait_multiselect: 'Atributos',
    },
    keepPlaying: 'Seguir jugando',
  },

  leaderboard: {
    windows: { day: 'Hoy', week: 'Esta semana', all: 'Histórico' },
    phrases: { day: 'hoy', week: 'esta semana', all: 'en el histórico' },
    you: (rank: number, phrase: string) => `Estás #${rank} ${phrase}`,
    keepPlaying: 'Seguir jugando',
  },
};
