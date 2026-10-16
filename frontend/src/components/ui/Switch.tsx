import type { ReactNode } from "react";

/** Accessible on/off switch built on a native checkbox (keyboard + screen readers
 * work as usual); the thumb springs across when toggled. */
export function Switch({
  checked,
  onChange,
  label,
  description,
  icon,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label
      className={`group flex cursor-pointer items-center gap-3.5 rounded-2xl border border-line bg-surface/60 px-4 py-3 transition-colors hover:border-primary/40 dark:bg-surface/40
        ${checked ? "border-primary/40 bg-primary/[0.06]" : ""} ${disabled ? "pointer-events-none opacity-60" : ""}`}
    >
      {icon && (
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-colors ${checked ? "bg-primary/15 text-primary" : "bg-ink/[0.05] text-muted"}`}>
          {icon}
        </span>
      )}
      <span className="min-w-0 flex-1 text-start">
        <span className="block text-sm font-medium text-ink">{label}</span>
        {description && <span className="mt-0.5 block text-xs text-muted">{description}</span>}
      </span>
      <input
        type="checkbox"
        role="switch"
        className="peer sr-only"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span
        aria-hidden="true"
        className="relative h-7 w-12 shrink-0 rounded-full bg-ink/15 transition-colors duration-300 peer-checked:bg-primary peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-canvas
          after:absolute after:start-1 after:top-1 after:h-5 after:w-5 after:rounded-full after:bg-white after:shadow-md after:transition-transform after:duration-300 after:ease-spring
          peer-checked:after:translate-x-5 rtl:peer-checked:after:-translate-x-5"
      />
    </label>
  );
}
