import type { ReactNode } from "react";

type Tone = "info" | "error" | "warning" | "success";

const TONE_CLASSES: Record<Tone, string> = {
  info: "bg-primary-light border-primary/30 text-primary-dark",
  error: "bg-severity-severe-bg border-severity-severe/30 text-severity-severe",
  warning: "bg-severity-mild-bg border-severity-mild/40 text-severity-moderate",
  success: "bg-primary-light border-primary/30 text-primary-dark",
};

export function Alert({ tone = "info", title, children }: { tone?: Tone; title?: string; children: ReactNode }) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-card border px-4 py-3 text-sm ${TONE_CLASSES[tone]}`}>
      {title && <p className="mb-0.5 font-semibold">{title}</p>}
      <p>{children}</p>
    </div>
  );
}
