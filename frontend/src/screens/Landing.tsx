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
 *
 * Movimiento (ADR-032, 08/11): el brillo dorado del fondo deriva despacio sobre un rayado tenue, y
 * los elementos entran escalonados en el orden en que se leen. Ninguno trae texto nuevo ni pide
 * nada a la red: el fondo es CSS. El botón entra a los 240 ms y se puede tocar desde antes.
 */

import { useNavigate } from 'react-router-dom';

import { AppFrame } from '../components/AppFrame';
import { PrimaryButton } from '../components/Button';
import { LanguageToggle } from '../components/LanguageToggle';
import { useT } from '../store/lang';
import { useSession } from '../store/session';

/** Retraso de entrada de cada elemento, en el orden de lectura. */
const stagger = (step: number) => ({ animationDelay: `${step * 80}ms` });

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
      <div className="relative flex flex-1 flex-col overflow-hidden">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[repeating-linear-gradient(135deg,rgb(255_255_255/0.018)_0_1px,transparent_1px_14px)]"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -inset-[10%] animate-drift bg-[radial-gradient(120%_60%_at_50%_0%,rgb(228_180_87/0.13),rgb(228_180_87/0)_60%)]"
        />

        <div className="relative flex flex-1 flex-col justify-center px-7">
          <p
            style={stagger(0)}
            className="animate-rise font-display text-[40px] leading-none font-bold tracking-[0.14em] text-ink uppercase lg:text-[52px]"
          >
            Draftsense
          </p>
          <div
            style={stagger(1)}
            className="my-[18px] mb-[26px] h-0.5 w-16 origin-left animate-line-grow bg-gold"
          />
          <h1
            style={stagger(1)}
            className="animate-rise font-display text-[25px] leading-tight font-semibold text-pretty text-ink lg:text-[30px]"
          >
            {t.landing.headline}
          </h1>
          <p
            style={stagger(2)}
            className="mt-3.5 animate-rise text-[15px] leading-relaxed text-mute-2 lg:text-base"
          >
            {t.landing.promise}
          </p>
          <div style={stagger(3)} className="mt-[34px] animate-rise">
            <PrimaryButton onClick={() => navigate(returning ? '/play' : '/start')}>
              {returning ? t.landing.continue : t.landing.start}
            </PrimaryButton>
          </div>
          <p
            style={stagger(4)}
            className="mt-[26px] animate-rise font-mono text-xs leading-relaxed text-faint"
          >
            {t.landing.research}
          </p>
        </div>

        <footer style={stagger(5)} className="relative flex animate-fade-in items-center gap-4 border-t border-edge-soft px-7 py-[22px] font-mono text-xs font-medium tracking-[0.1em] text-label">
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
