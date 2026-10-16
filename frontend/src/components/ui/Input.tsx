import { forwardRef, useState, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Icon, type IconName } from "./Icon";

export const FIELD_CLASSES =
  "w-full rounded-xl border bg-surface/80 text-sm text-ink placeholder:text-muted/70 shadow-[inset_0_1px_2px_rgb(var(--c-shadow)/0.05)] " +
  "transition-[border-color,box-shadow,background-color] duration-200 " +
  "hover:border-primary/40 focus:border-primary focus:bg-surface focus:outline-none focus:ring-4 focus:ring-primary/15 " +
  "disabled:cursor-not-allowed disabled:opacity-60 dark:bg-surface/50";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  icon?: IconName;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, id, icon, type, className = "", ...rest }, ref) => {
    const inputId = id ?? rest.name;
    const [revealed, setRevealed] = useState(false);
    const isPassword = type === "password";

    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={inputId} className="text-sm font-medium text-ink">
            {label}
          </label>
        )}
        <div className="group/field relative">
          {icon && (
            <span className="pointer-events-none absolute inset-y-0 start-0 flex items-center ps-3.5 text-muted transition-colors group-focus-within/field:text-primary">
              <Icon name={icon} className="h-[18px] w-[18px]" />
            </span>
          )}
          <input
            ref={ref}
            id={inputId}
            type={isPassword && revealed ? "text" : type}
            aria-invalid={!!error}
            aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
            className={`${FIELD_CLASSES} h-12 ${icon ? "ps-10" : "ps-4"} ${isPassword ? "pe-11" : "pe-4"}
              ${error ? "border-severity-severe focus:border-severity-severe focus:ring-severity-severe/15" : "border-line"} ${className}`}
            {...rest}
          />
          {isPassword && (
            <button
              type="button"
              onClick={() => setRevealed((r) => !r)}
              aria-label={revealed ? "Hide password" : "Show password"}
              aria-pressed={revealed}
              className="absolute inset-y-0 end-0 flex w-11 items-center justify-center rounded-e-xl text-muted transition-colors hover:text-primary"
            >
              <Icon name={revealed ? "eyeSlash" : "eye"} className="h-[18px] w-[18px]" />
            </button>
          )}
        </div>
        {error && (
          <p id={`${inputId}-error`} className="flex items-center gap-1.5 text-sm text-severity-severe animate-fade-in">
            <Icon name="error" className="h-4 w-4 shrink-0" />
            {error}
          </p>
        )}
        {!error && hint && (
          <p id={`${inputId}-hint`} className="text-xs text-muted">
            {hint}
          </p>
        )}
      </div>
    );
  }
);
Input.displayName = "Input";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(({ label, id, className = "", ...rest }, ref) => {
  const fieldId = id ?? rest.name;
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={fieldId} className="text-sm font-medium text-ink">
          {label}
        </label>
      )}
      <textarea ref={ref} id={fieldId} className={`${FIELD_CLASSES} border-line px-4 py-3 leading-relaxed ${className}`} {...rest} />
    </div>
  );
});
Textarea.displayName = "Textarea";
