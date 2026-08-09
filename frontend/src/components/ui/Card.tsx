import type { HTMLAttributes } from "react";

export function Card({ className = "", children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-card border border-line bg-surface p-5 sm:p-6 ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className = "", children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`mb-4 flex items-center justify-between gap-3 ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function CardTitle({ className = "", children, ...rest }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={`font-display text-lg font-semibold text-ink ${className}`} {...rest}>
      {children}
    </h3>
  );
}
