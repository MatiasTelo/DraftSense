/**
 * El marco de toda pantalla.
 *
 * **El escritorio es el caso principal** desde el 08/11/2026 (ADR-031, `docs/30-ux-flujos.md` §9).
 * A partir de `lg` (1024 px) la barra superior va a lo ancho de la ventana, el contenido es un panel
 * de hasta 720 px centrado en vertical y en horizontal, y la barra inferior no se muestra: la
 * navegación sube a la barra superior (`Chrome.tsx`).
 *
 * Debajo de `lg` se ve como antes: una columna de hasta 640 px, de alto completo, con las dos
 * barras. El ancho no se estira en ningún caso: una tarjeta a pantalla completa rompería la regla de
 * una pregunta por pantalla sin scroll, que es de lo que depende la regla de los cinco segundos.
 *
 * El panel entra con `animate-fade-in` (ADR-032). Cada pantalla monta su propio `AppFrame`, así que
 * eso es la transición entre rutas.
 */

import type { ReactNode } from 'react';

interface Props {
  /** La barra superior (`TopBar`). En celular va dentro de la columna; en escritorio, a lo ancho. */
  header?: ReactNode;
  /** La barra inferior (`BottomNav`). Sólo en celular. */
  footer?: ReactNode;
  children: ReactNode;
}

export function AppFrame({ header, footer, children }: Props) {
  return (
    <div className="relative flex min-h-dvh justify-center bg-void lg:flex-col lg:items-center">
      {/* El brillo del fondo de escritorio: sólo decora el vacío alrededor del panel. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 hidden bg-[radial-gradient(70%_55%_at_50%_45%,rgb(228_180_87/0.06),rgb(228_180_87/0)_70%)] lg:block"
      />

      <div className="relative flex min-h-dvh w-full max-w-[640px] flex-col bg-surface lg:min-h-0 lg:max-w-none lg:flex-1 lg:bg-transparent">
        {header !== undefined && <div className="lg:border-b lg:border-white/7 lg:bg-nav">{header}</div>}

        <div className="flex flex-1 flex-col lg:items-center lg:justify-center lg:px-6 lg:py-6">
          {/* El alto mínimo evita que el panel cambie de tamaño entre un tipo de tarjeta y otro:
              sin él, cada pregunta movería el borde y los botones de lugar. */}
          <div className="flex w-full flex-1 animate-fade-in flex-col lg:min-h-[min(620px,calc(100dvh_-_7rem))] lg:max-w-[720px] lg:flex-none lg:border lg:border-edge lg:bg-surface">
            {children}
          </div>
        </div>

        {footer !== undefined && <div className="lg:hidden">{footer}</div>}
      </div>
    </div>
  );
}
