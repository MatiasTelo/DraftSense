import { forwardRef, useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react';

import { ApiError } from '../api';

export function Page({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-6">
      <header>
        <h1 className="font-display text-2xl font-semibold text-ink">{title}</h1>
        {intro && <p className="mt-1 max-w-3xl text-sm text-ink-4">{intro}</p>}
      </header>
      {children}
    </section>
  );
}

export function Panel({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="bevel-12 border border-edge bg-panel p-5">
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {title && <h2 className="font-display text-base font-semibold text-ink-2">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="bevel-8 border border-edge bg-control p-4">
      <div className="text-xs uppercase tracking-[0.12em] text-label">{label}</div>
      <div className="mt-1 font-display text-2xl font-semibold text-ink">{value}</div>
      {hint && <div className="mt-1 text-xs text-mute">{hint}</div>}
    </div>
  );
}

type Variant = 'primary' | 'secondary' | 'danger';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-gold text-void hover:bg-gold-bright',
  secondary: 'border border-edge-strong bg-control text-ink-2 hover:bg-rail',
  danger: 'border border-series-2 bg-control text-ink hover:bg-rail',
};

// `forwardRef` porque `Confirm` pone el foco en *Cancelar* al abrir: la acción por defecto de un
// diálogo que cambia el parche vigente no puede ser la destructiva.
export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }
>(function Button({ variant = 'secondary', className = '', ...props }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      className={`bevel-8 min-h-11 px-4 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
});

export function Loading() {
  return <p className="text-sm text-mute">Cargando…</p>;
}

/** Un error del contrato, con la lista de `details` cuando viene (24 §5). */
export function ErrorBox({ error }: { error: Error | null }) {
  if (!error) return null;
  const details = error instanceof ApiError ? error.details : [];
  return (
    <div role="alert" className="bevel-8 border border-series-2 bg-control p-4 text-sm text-ink-2">
      <p className="font-semibold">{error.message}</p>
      {details.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-ink-4">
          {details.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <div role="status" className="bevel-8 border border-cyan/40 bg-control p-4 text-sm text-ink-2">
      {children}
    </div>
  );
}

/**
 * La confirmación de las acciones que cambian lo que se sirve (24 §3.5, §3.6, §3.8).
 *
 * Es un diálogo propio y no `window.confirm`: el nativo bloquea la página entera y no se puede
 * maquetar para mostrar el valor actual y el nuevo lado a lado.
 */
export function Confirm({
  open,
  title,
  children,
  confirmLabel,
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) cancelRef.current?.focus();
  }, [open]);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-20 flex items-center justify-center bg-void/80 p-4"
      onKeyDown={(e) => e.key === 'Escape' && onCancel()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="bevel-12 w-full max-w-lg border border-edge-strong bg-panel p-6"
      >
        <h2 className="font-display text-lg font-semibold text-ink">{title}</h2>
        <div className="mt-3 text-sm text-ink-3">{children}</div>
        <div className="mt-6 flex justify-end gap-3">
          <Button ref={cancelRef} onClick={onCancel} disabled={busy}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={onConfirm} disabled={busy}>
            {busy ? 'Aplicando…' : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-ink-4">{label}</span>
      {children}
      {hint && <span className="text-xs text-mute">{hint}</span>}
    </label>
  );
}

export const inputClass =
  'bevel-8 min-h-11 border border-edge bg-control px-3 text-sm text-ink placeholder:text-faint';

/** Las tablas anchas scrollean dentro de su contenedor, nunca la página (24 §2). */
export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="overflow-x-auto">{children}</div>;
}

export const th = 'border-b border-edge px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-label';
export const td = 'border-b border-edge-soft px-3 py-2 align-top text-ink-3';
