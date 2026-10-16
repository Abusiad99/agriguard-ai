import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

type Tone = "info" | "error" | "warning" | "success";

const TONE_CLASSES: Record<Tone, string> = {
  info: "bg-primary-light/70 border-primary/25 text-primary-dark",
  success: "bg-primary-light/70 border-primary/25 text-primary-dark",
  error: "bg-severity-severe-bg/80 border-severity-severe/30 text-severity-severe",
  warning: "bg-severity-mild-bg/80 border-severity-mild/35 text-severity-mild",
};

const TONE_ICON: Record<Tone, IconName> = {
  info: "info",
  success: "check",
  error: "error",
  warning: "warning",
};

export function Alert({ tone = "info", title, children }: { tone?: Tone; title?: string; children: ReactNode }) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-sm backdrop-blur-sm animate-scale-in ${TONE_CLASSES[tone]}`}
    >
      <Icon name={TONE_ICON[tone]} className="mt-px h-5 w-5 shrink-0" />
      <div className="min-w-0 text-start">
        {title && <p className="mb-0.5 font-semibold">{title}</p>}
        <p className="leading-relaxed">{children}</p>
      </div>
    </div>
  );
}
