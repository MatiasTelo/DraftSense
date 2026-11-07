/**
 * El microcopy de las pantallas en inglés, que es el idioma por defecto (ADR-010, ADR-028).
 *
 * Los textos de las preguntas no están acá: los arma el servidor en el idioma pedido
 * (`docs/12-api.md` §1.1). Lo de acá es lo que rodea a la tarjeta. Los literales son los de
 * `docs/30-ux-flujos.md`; cambiar uno es cambiar ese documento.
 */

export const en = {
  language: 'Language',

  landing: {
    headline: 'Help rank every champion in League of Legends.',
    promise: 'Quick questions. No account. 2 minutes.',
    start: 'Start',
    continue: 'Continue',
    research: 'Your answers feed public research at UTN Mendoza.',
    about: 'About',
    privacy: 'Privacy',
  },

  onboarding: {
    title: 'A bit about you',
    skip: 'Skip',
    why: 'Optional. It helps us compare answers across skill levels.',
    rank: 'Your rank',
    ranks: {
      iron: 'Iron',
      bronze: 'Bronze',
      silver: 'Silver',
      gold: 'Gold',
      platinum: 'Plat',
      emerald: 'Emerald',
      diamond: 'Diamond',
      master: 'Master',
      grandmaster: 'Grandmaster',
      challenger: 'Challenger',
      unranked: "I don't play ranked",
    },
    role: 'Main role',
    roles: { top: 'Top', jungle: 'Jungle', mid: 'Mid', adc: 'Bot', support: 'Support' },
    hours: 'Hours per week',
    browser: 'Your progress lives in this browser.',
    continue: 'Continue',
  },

  play: {
    confirm: 'Confirm',
    whatItMeans: (label: string) => `What ${label.toLowerCase()} means`,
    versus: 'vs',
    emptyKind: 'Nothing to ask',
    emptyTitle: 'Nothing left to ask right now. Come back after the next patch.',
    seeProfile: 'See your profile →',
    rateKind: 'Rate limit',
    rateTitle: (seconds: number) => `Slow down a little — try again in ${seconds} seconds.`,
    offlineKind: 'Offline',
    offlineTitle: "You're offline. Your last answer wasn't saved.",
    serverKind: 'Server',
    serverTitle: 'Something broke on our end. Try again in a minute.',
    retry: 'Retry',
  },

  feedback: {
    inARow: (streak: number) => `${streak} in a row 🔥`,
    firstTitle: "You're one of the first to answer this",
    firstBody: "There aren't enough answers yet to show how the community compares.",
    pairs: (agreed: number, compared: number) =>
      `You agree with the community on ${agreed} of ${compared} ${compared === 1 ? 'pair' : 'pairs'}`,
    traits: (agreed: number, compared: number) =>
      `You agree with the community on ${agreed} of ${compared} ${compared === 1 ? 'trait' : 'traits'}`,
    median: (median: number, unit: string, yours: number | undefined) =>
      `Most players said ${median} ${unit}. You said ${yours ?? ''}.`,
    agree: (percent: number) => `${percent}% agree with you`,
    minority: (percent: number) => `You're in the ${percent}%`,
    answers: (count: number | undefined) => `${count ?? ''} answers`,
  },

  chrome: {
    answered: (count: number) => `${count} answered`,
    play: 'Play',
    profile: 'Profile',
    ranks: 'Ranks',
  },

  profile: {
    answers: 'answers',
    streak: 'streak',
    best: 'best',
    daysInARow: (days: number) => `🔥 ${days} days in a row`,
    bestDays: (days: number) => `best: ${days} days`,
    agreementBefore: 'You agree with the community',
    agreementAfter: 'of the time',
    topBefore: 'Top',
    topAfter: 'of contributors',
    answered: "What you've answered",
    coverage: {
      pairwise_dimension: 'Champion rankings',
      peak_timing: 'Power spikes',
      lane_matchup: 'Lane matchups',
      duo_synergy: 'Duos',
      trait_multiselect: 'Traits',
    },
    keepPlaying: 'Keep playing',
  },

  leaderboard: {
    windows: { day: 'Today', week: 'This week', all: 'All time' },
    phrases: { day: 'today', week: 'this week', all: 'all time' },
    you: (rank: number, phrase: string) => `You're #${rank} ${phrase}`,
    keepPlaying: 'Keep playing',
  },
};

/** La forma que tiene que cumplir cada idioma: la del inglés, con los mismos parámetros. */
export type Messages = typeof en;
