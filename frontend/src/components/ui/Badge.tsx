import type { ReactNode } from "react";

type Tone = "primary" | "mild" | "moderate" | "severe" | "neutral";

const TONE_CLASSES: Record<Tone, string> = {
  primary: "bg-primary-light text-primary-dark",
  mild: "bg-severity-mild-bg text-severity-mild",
  moderate: "bg-severity-moderate-bg text-severity-moderate",
  severe: "bg-severity-severe-bg text-severity-severe",
  neutral: "bg-line/50 text-muted",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${TONE_CLASSES[tone]}`}>
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
