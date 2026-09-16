/**
 * El marco de toda pantalla.
 *
 * El diseño base es de 360 px de ancho y el escritorio es el caso derivado: la aplicación se
 * centra y no pasa de 640 px (`docs/30-ux-flujos.md` §9). Estirarla a pantalla completa rompería
 * la regla de una pregunta por pantalla sin scroll, que es de lo que depende la regla de los
 * cinco segundos.
 */

import type { ReactNode } from 'react';

export function AppFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh justify-center bg-void">
      <div className="flex min-h-dvh w-full max-w-[640px] flex-col bg-surface">{children}</div>
    </div>
  );
}
