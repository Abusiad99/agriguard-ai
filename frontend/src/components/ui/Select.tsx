import { forwardRef, type SelectHTMLAttributes } from "react";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(({ label, id, className = "", children, ...rest }, ref) => {
  const selectId = id ?? rest.name;
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={selectId} className="text-sm font-medium text-ink">
          {label}
        </label>
      )}
      <select
        ref={ref}
        id={selectId}
        className={`rounded-card border border-line bg-surface px-3.5 py-2.5 text-sm text-ink focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary ${className}`}
        {...rest}
      >
        {children}
      </select>
    </div>
  );
});
Select.displayName = "Select";
