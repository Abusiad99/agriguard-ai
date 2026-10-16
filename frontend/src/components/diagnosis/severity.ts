import type { SeverityLevel } from "@/types/api";
import { useLocale } from "@/context/LocaleContext";

export const SEVERITY_COLOR: Record<SeverityLevel, string> = {
  mild: "rgb(var(--c-mild))",
  moderate: "rgb(var(--c-moderate))",
  severe: "rgb(var(--c-severe))",
};

export function useSeverityLabel() {
  const { t } = useLocale();
  return (level: SeverityLevel | string | null | undefined): string => {
    if (level === "mild") return t.result.severityMild;
    if (level === "moderate") return t.result.severityModerate;
    if (level === "severe") return t.result.severitySevere;
    return level ?? "";
  };
}
