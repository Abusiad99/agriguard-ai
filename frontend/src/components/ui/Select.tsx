import { forwardRef, type SelectHTMLAttributes } from "react";
import { Icon } from "./Icon";
import { FIELD_CLASSES } from "./Input";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  compact?: boolean;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(({ label, id, className = "", compact, children, ...rest }, ref) => {
  const selectId = id ?? rest.name;
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={selectId} className="text-sm font-medium text-ink">
          {label}
        </label>
      )}
      <div className="group/select relative">
        <select
          ref={ref}
          id={selectId}
          className={`${FIELD_CLASSES} cursor-pointer appearance-none border-line ${compact ? "h-9 ps-3 pe-8 text-[13px]" : "h-12 ps-4 pe-10"} ${className}`}
          {...rest}
        >
          {children}
        </select>
        <span className={`pointer-events-none absolute inset-y-0 end-0 flex items-center text-muted transition-transform group-focus-within/select:rotate-180 group-focus-within/select:text-primary ${compact ? "pe-2.5" : "pe-3.5"}`}>
          <Icon name="chevronDown" className="h-4 w-4" strokeWidth={2} />
        </span>
      </div>
    </div>
  );
});
Select.displayName = "Select";
