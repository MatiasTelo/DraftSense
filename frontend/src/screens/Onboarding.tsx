/**
 * `/start` — las tres preguntas de segmentación (`docs/30-ux-flujos.md` §4).
 *
 * **Nunca se pide algo antes de dar algo**, así que nada acá es obligatorio: se puede tocar
 * `Continue` con los tres vacíos, y `Skip` está arriba a la derecha desde el primer instante.
 *
 * `Skip` no es «salir sin contestar»: llama igual a `POST /sessions/onboarding` con los tres
 * campos en `null`, lo que deja `onboarding_seen = true` y evita volver a preguntar. Omitir
 * también es una respuesta.
 *
 * La segunda línea explica **por qué** se pregunta. Sin ella, tres preguntas personales antes de
 * empezar se leen como un formulario; con ella, como una contribución.
 *
 * Los valores que se envían son los de las columnas, no las etiquetas: `Plat` guarda `platinum` y
 * `I don't play ranked` guarda `unranked`, que significa «juega, pero no clasificatoria» y es
 * distinto de `null` (`docs/25-agregacion.md` §3.1).
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { AppFrame } from '../components/AppFrame';
import { PrimaryButton } from '../components/Button';
import { saveOnboarding } from '../lib/client';
import { useT } from '../store/lang';
import { useSession } from '../store/session';

/** Los once valores de `VALID_RANKS`, en orden. La etiqueta sale del diccionario del idioma. */
const RANKS = [
  'iron',
  'bronze',
  'silver',
  'gold',
  'platinum',
  'emerald',
  'diamond',
  'master',
  'grandmaster',
  'challenger',
  'unranked',
] as const;

/** Los cinco valores de `lane_role`. `adc` se muestra como `Bot`, que es como se lo nombra. */
const ROLES = ['top', 'jungle', 'mid', 'adc', 'support'] as const;

const HOURS = ['<5', '5-15', '15-30', '30+'] as const;

interface ChipProps {
  label: string;
  selected: boolean;
  onClick: () => void;
  mono?: boolean;
}

function Chip({ label, selected, onClick, mono }: ChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`flex min-h-11 cursor-pointer items-center border px-3.5 text-[13px] transition-[background-color,border-color,color,transform,scale] duration-150 ease-out-quart active:scale-[0.96] ${
        mono === true ? 'min-w-16 justify-center font-mono' : ''
      } ${
        selected
          ? 'border-gold bg-gold/12 font-semibold text-gold-bright'
          : 'border-edge bg-control font-medium text-ink-3 hover:border-edge-strong hover:bg-rail hover:text-ink'
      }`}
    >
      {label}
    </button>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-2.5 border-0 p-0">
      <legend className="font-mono text-[11px] font-medium tracking-[0.18em] text-label uppercase">
        {title}
      </legend>
      <div className="flex flex-wrap gap-2">{children}</div>
    </fieldset>
  );
}

export function Onboarding() {
  const navigate = useNavigate();
  const markOnboardingSeen = useSession((state) => state.markOnboardingSeen);
  const t = useT();

  const [rank, setRank] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [hours, setHours] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function submit(skip: boolean) {
    setSending(true);
    try {
      await saveOnboarding({
        declared_rank: skip ? null : rank,
        declared_main_role: skip ? null : role,
        declared_hours_bucket: skip ? null : hours,
      });
    } catch {
      // Que falle no puede dejar a nadie parado en la puerta: el onboarding es opcional y lo que
      // importa es llegar a la primera tarjeta. Se pierde la segmentación de esta persona, nada más.
    } finally {
      markOnboardingSeen();
      navigate('/play');
    }
  }

  /** Volver a tocar el chip elegido lo deselecciona: no hay forma de quedar atrapado en un valor. */
  const toggle =
    (set: (value: string | null) => void, current: string | null) => (value: string) =>
      set(current === value ? null : value);

  return (
    <AppFrame>
      <header className="flex flex-col gap-2 border-b border-edge-soft px-[22px] pt-6 pb-[18px]">
        <div className="flex items-baseline justify-between gap-3">
          <h1 className="font-display text-[23px] leading-tight font-semibold text-ink">
            {t.onboarding.title}
          </h1>
          {/* 44 px de área táctil (30-ux-flujos §9). El margen negativo conserva la altura del
              encabezado del maquetado, que se armó con el botón de 32 px. */}
          <button
            type="button"
            onClick={() => void submit(true)}
            disabled={sending}
            className="-my-1.5 flex min-h-11 min-w-11 cursor-pointer items-center justify-center px-1 font-mono text-xs font-semibold tracking-[0.14em] text-gold uppercase transition-colors duration-150 enabled:hover:text-gold-bright disabled:cursor-default"
          >
            {t.onboarding.skip}
          </button>
        </div>
        <p className="text-[13px] leading-relaxed text-mute-2">
          {t.onboarding.why}
        </p>
      </header>

      <div className="flex flex-1 flex-col gap-4 px-[22px] py-5">
        <Group title={t.onboarding.rank}>
          {RANKS.map((value) => (
            <Chip
              key={value}
              label={t.onboarding.ranks[value]}
              selected={rank === value}
              onClick={() => toggle(setRank, rank)(value)}
            />
          ))}
        </Group>

        <Group title={t.onboarding.role}>
          {ROLES.map((value) => (
            <Chip
              key={value}
              label={t.onboarding.roles[value]}
              selected={role === value}
              onClick={() => toggle(setRole, role)(value)}
            />
          ))}
        </Group>

        <Group title={t.onboarding.hours}>
          {HOURS.map((value) => (
            <Chip
              key={value}
              label={value}
              mono
              selected={hours === value}
              onClick={() => toggle(setHours, hours)(value)}
            />
          ))}
        </Group>
      </div>

      <div className="flex flex-col gap-3.5 px-[22px] pb-[26px]">
        <p className="font-mono text-[11px] leading-relaxed text-faint">
          {t.onboarding.browser}
        </p>
        <PrimaryButton onClick={() => void submit(false)} disabled={sending}>
          {t.onboarding.continue}
        </PrimaryButton>
      </div>
    </AppFrame>
  );
}
