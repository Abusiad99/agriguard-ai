import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export function EmptyState({
  icon,
  iconName = "leaf",
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  iconName?: IconName;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="glass relative flex flex-col items-center justify-center overflow-hidden rounded-panel px-6 py-16 text-center animate-rise-in">
      {/* Viewfinder framing the empty spot, waiting for a first scan. */}
      <div className="relative mb-6 flex h-24 w-24 items-center justify-center">
        <span className="absolute inset-0 rounded-full bg-primary/10 animate-pulse-ring" />
        <span className="absolute inset-2 rounded-full bg-primary/10" />
        <svg viewBox="0 0 96 96" className="absolute inset-0 h-full w-full text-primary/60" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
          <path d="M8 26V14a6 6 0 016-6h12M70 8h12a6 6 0 016 6v12M88 70v12a6 6 0 01-6 6H70M26 88H14a6 6 0 01-6-6V70" />
        </svg>
        <span className="relative text-primary">{icon ?? <Icon name={iconName} className="h-9 w-9" />}</span>
      </div>
      <p className="font-display text-xl font-semibold text-ink">{title}</p>
      {body && <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted">{body}</p>}
      {action && <div className="mt-7">{action}</div>}
    </div>
  );
}
