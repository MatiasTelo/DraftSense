/**
 * El selector de idioma `EN | ES` (ADR-028, `docs/30-ux-flujos.md` §10).
 *
 * Vive en la landing y en la barra superior de `/play`. Cambiar el idioma **descarta la cola**:
 * las preguntas ya cargadas vinieron armadas por el servidor en el idioma anterior, y el lote
 * siguiente se pide con el nuevo. La pregunta que se estaba mirando se pierde sin registrar nada,
 * que es lo mismo que pasa al recargar.
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
  const resetQueue = useQueue((state) => state.reset);
  const t = useT();

  function choose(next: Lang) {
    if (next === lang) return;
    setLang(next);
    resetQueue();
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
            className={`flex min-h-11 min-w-11 items-center justify-center font-mono text-xs font-semibold tracking-[0.14em] uppercase ${
              lang === code ? 'text-gold' : 'text-label'
            }`}
          >
            {code}
          </button>
        </Fragment>
      ))}
    </div>
  );
}
