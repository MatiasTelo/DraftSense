/**
 * El idioma de la interfaz (ADR-028).
 *
 * Lo elige la persona con el selector `EN | ES`, no el navegador. Se recuerda en `localStorage`,
 * que puede no estar disponible —navegación privada, almacenamiento bloqueado—: en ese caso la
 * sesión arranca en inglés y el selector sigue funcionando hasta recargar.
 *
 * El idioma viaja al servidor como `lang` en `GET /questions/next`, que es el único endpoint que
 * devuelve textos para mostrar. Cambiarlo descarta la cola: lo hace `LanguageToggle`.
 */

import { create } from 'zustand';

import { en } from '../i18n/en';
import type { Messages } from '../i18n/en';
import { es } from '../i18n/es';

export type Lang = 'en' | 'es';

export const LANGS: readonly Lang[] = ['en', 'es'];

const STORAGE_KEY = 'draftsense.lang';

const MESSAGES: Record<Lang, Messages> = { en, es };

function stored(): Lang {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === 'es' ? 'es' : 'en';
  } catch {
    return 'en';
  }
}

interface LangState {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

export const useLang = create<LangState>((set) => ({
  lang: stored(),
  setLang(lang) {
    try {
      window.localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      // Sin almacenamiento el idioma vale para esta pestaña y nada más.
    }
    set({ lang });
  },
}));

/** Los textos del idioma activo. */
export function useT(): Messages {
  return MESSAGES[useLang((state) => state.lang)];
}
