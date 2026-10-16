import type { HTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export function Card({
  className = "",
  children,
  highlight,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { highlight?: boolean }) {
  return (
    <div className={`glass rounded-panel p-5 sm:p-6 ${highlight ? "ring-gradient" : ""} ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({ className = "", children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`mb-5 flex items-center justify-between gap-3 ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function CardTitle({
  className = "",
  children,
  icon,
  ...rest
}: HTMLAttributes<HTMLHeadingElement> & { icon?: IconName }) {
  return (
    <h3 className={`flex items-center gap-3 font-display text-lg font-semibold text-ink ${className}`} {...rest}>
      {icon && <IconTile name={icon} />}
      {children}
    </h3>
  );
}

const TILE_TONES = {
  primary: "bg-primary/10 text-primary ring-primary/15",
  mild: "bg-severity-mild-bg text-severity-mild ring-severity-mild/20",
  moderate: "bg-severity-moderate-bg text-severity-moderate ring-severity-moderate/20",
  severe: "bg-severity-severe-bg text-severity-severe ring-severity-severe/20",
  accent: "bg-accent/15 text-accent-dark ring-accent/25 dark:text-accent",
  neutral: "bg-ink/[0.05] text-muted ring-ink/10",
} as const;

export type TileTone = keyof typeof TILE_TONES;

/** Small rounded icon tile used to label a section or a stat. */
export function IconTile({
  name,
  tone = "primary",
  size = "md",
}: {
  name: IconName;
  tone?: TileTone;
  size?: "sm" | "md" | "lg";
}) {
  const dims = size === "lg" ? "h-12 w-12 rounded-2xl" : size === "sm" ? "h-8 w-8 rounded-lg" : "h-10 w-10 rounded-xl";
  const iconDims = size === "lg" ? "h-6 w-6" : size === "sm" ? "h-4 w-4" : "h-5 w-5";
  return (
    <span className={`inline-flex shrink-0 items-center justify-center ring-1 ring-inset ${dims} ${TILE_TONES[tone]}`}>
      <Icon name={name} className={iconDims} />
    </span>
  );
}

/** Page heading block shared by every screen, so titles sit at one rhythm. */
export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-2">{eyebrow}</div>}
        <h1 className="text-balance font-display text-[1.75rem] font-semibold leading-tight text-ink sm:text-[2rem]">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-prose text-[0.95rem] text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2.5">{actions}</div>}
    </div>
  );
}
