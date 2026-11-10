import { Badge } from "@/components/ui/Badge";
import { useLocale } from "@/context/LocaleContext";
import { readinessTone } from "@/lib/aiFeatureUi";
import type { Readiness } from "@/types/aiFeatures";

/** Model readiness as a badge ("Ready", "Not trained yet", ...). */
export function ReadinessBadge({ readiness }: { readiness: Readiness | "ok" | "failed" }) {
  const { t } = useLocale();
  const key = readiness === "ok" ? "ready" : readiness;
  return <Badge tone={readinessTone(readiness)}>{t.models.readiness[key] ?? key}</Badge>;
}
