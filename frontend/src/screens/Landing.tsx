/**
 * `/` — el landing (`docs/30-ux-flujos.md` §3).
 *
 * Cada paso entre abrir el enlace y responder la primera pregunta cuesta respuestas, y la
 * participación insuficiente es el riesgo número uno del proyecto. De ahí que acá no haya registro,
 * ni muro, ni email: una promesa, una fricción declarada y un botón.
 *
 * La tercera línea —la investigación en la UTN— no es un crédito: **el motivo del proyecto es parte
 * del gancho**. La gente responde encuestas de internet cuando entiende para qué sirven, y nombrar
 * la universidad convierte «otro quiz de LoL» en algo con destino.
 *
 * `About` y `Privacy` se maquetan pero todavía no llevan a ningún lado: esas dos rutas llegan con
 * `docs/33-privacidad-y-legal.md`, que está pendiente y desbloquea la semana 7.
 */

import { useNavigate } from 'react-router-dom';

import { AppFrame } from '../components/AppFrame';
import { PrimaryButton } from '../components/Button';
import { LanguageToggle } from '../components/LanguageToggle';
import { useT } from '../store/lang';
import { useSession } from '../store/session';

export function Landing() {
  const navigate = useNavigate();
  const onboardingSeen = useSession((state) => state.onboardingSeen);
  const ready = useSession((state) => state.ready);
  const t = useT();

  // La cookie es HttpOnly y no se puede consultar: `onboarding_seen` es la única señal de que ya
  // hubo una sesión antes, porque tanto `Continue` como `Skip` lo dejan en `true` y no se vuelve
  // a preguntar. Hasta que `POST /sessions` conteste se muestra `Start`, que es el caso de quien
  // llega por primera vez.
  const returning = ready && onboardingSeen;

  return (
    <AppFrame>
      <div className="relative flex flex-1 flex-col">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(120%_60%_at_50%_0%,rgb(228_180_87/0.10),rgb(228_180_87/0)_60%)]" />

        <div className="relative flex flex-1 flex-col justify-center px-7">
          <p className="font-display text-[40px] leading-none font-bold tracking-[0.14em] text-ink uppercase">
            Draftsense
          </p>
          <div className="my-[18px] mb-[26px] h-0.5 w-16 bg-gold" />
          <h1 className="font-display text-[25px] leading-tight font-semibold text-pretty text-ink">
            {t.landing.headline}
          </h1>
          <p className="mt-3.5 text-[15px] leading-relaxed text-mute-2">
            {t.landing.promise}
          </p>
          <div className="mt-[34px]">
            <PrimaryButton onClick={() => navigate(returning ? '/play' : '/start')}>
              {returning ? t.landing.continue : t.landing.start}
            </PrimaryButton>
          </div>
          <p className="mt-[26px] font-mono text-xs leading-relaxed text-faint">
            {t.landing.research}
          </p>
        </div>

        <footer className="relative flex items-center gap-4 border-t border-edge-soft px-7 py-[22px] font-mono text-xs font-medium tracking-[0.1em] text-label">
          {/* Sin corte de línea: en español «Acerca de» se partía en dos a 360 px. */}
          <span className="whitespace-nowrap">{t.landing.about}</span>
          <span className="text-[#39414d]">·</span>
          <span className="whitespace-nowrap">{t.landing.privacy}</span>
          <span className="flex-1" />
          <LanguageToggle />
        </footer>
      </div>
    </AppFrame>
  );
}
