import type { ReactNode } from "react";

type Tone = "primary" | "mild" | "moderate" | "severe" | "neutral";

const TONE_CLASSES: Record<Tone, string> = {
  primary: "bg-primary-light text-primary-dark ring-primary/20",
  mild: "bg-severity-mild-bg text-severity-mild ring-severity-mild/25",
  moderate: "bg-severity-moderate-bg text-severity-moderate ring-severity-moderate/25",
  severe: "bg-severity-severe-bg text-severity-severe ring-severity-severe/25",
  neutral: "bg-ink/[0.05] text-muted ring-ink/10",
};

const DOT_CLASSES: Record<Tone, string> = {
  primary: "bg-primary",
  mild: "bg-severity-mild",
  moderate: "bg-severity-moderate",
  severe: "bg-severity-severe",
  neutral: "bg-muted",
};

export function Badge({
  tone = "neutral",
  children,
  dot = true,
  pulse = false,
  className = "",
}: {
  tone?: Tone;
  children: ReactNode;
  dot?: boolean;
  /** Draws attention to a live/urgent state — only use for severe findings. */
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${TONE_CLASSES[tone]} ${className}`}
    >
      {dot && (
        <span className="relative flex h-1.5 w-1.5">
          {pulse && <span className={`absolute inset-0 animate-ping rounded-full opacity-70 ${DOT_CLASSES[tone]}`} />}
          <span className={`relative h-1.5 w-1.5 rounded-full ${DOT_CLASSES[tone]}`} />
        </span>
      )}
      {children}
    </span>
  );
}

export function severityTone(level: string | null | undefined): Tone {
  if (level === "mild") return "mild";
  if (level === "moderate") return "moderate";
  if (level === "severe") return "severe";
  return "neutral";
}
