/**
 * El selector de idioma `EN | ES` (ADR-028, `docs/30-ux-flujos.md` §10).
 *
 * Vive en la landing y en la barra superior de `/play`. Cambiar el idioma **traduce la cola**
 * (ADR-029, que reemplazó el descarte de ADR-028 §5): el servidor vuelve a armar en el idioma
 * nuevo las preguntas que ya estaban cargadas, y la tarjeta que se está mirando sigue siendo la
 * misma, con lo que ya se movió en ella. La `key` de la tarjeta es su `question_id`, que no cambia,
 * así que su estado local —el orden del ranking, el minuto, los atributos marcados— sobrevive.
 *
 * Cada opción mide 44 px (§9) y el idioma activo se marca con `aria-pressed`, no sólo con color.
 */

import { Fragment } from 'react';

import { LANGS, useLang, useT } from '../store/lang';
import type { Lang } from '../store/lang';
import { useQueue } from '../store/queue';

export function LanguageToggle() {
  const lang = useLang((state) => state.lang);
  const setLang = useLang((state) => state.setLang);
  const retranslate = useQueue((state) => state.retranslate);
  const t = useT();

  function choose(next: Lang) {
    if (next === lang) return;
    setLang(next);
    void retranslate(next);
  }

  return (
    <div role="group" aria-label={t.language} className="-my-3 flex items-center">
      {LANGS.map((code, index) => (
        <Fragment key={code}>
          {index > 0 && (
            <span aria-hidden="true" className="text-faint">
              |
            </span>
          )}
          <button
            type="button"
            onClick={() => choose(code)}
            aria-pressed={lang === code}
            className={`flex min-h-11 min-w-11 cursor-pointer items-center justify-center font-mono text-xs font-semibold tracking-[0.14em] uppercase transition-colors duration-150 ${
              lang === code ? 'text-gold' : 'text-label hover:text-ink-3'
            }`}
          >
            {code}
          </button>
        </Fragment>
      ))}
    </div>
  );
}
