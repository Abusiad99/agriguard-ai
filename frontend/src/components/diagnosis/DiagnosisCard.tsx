import { Link } from "react-router-dom";
import type { DiagnosisSummarySchema } from "@/types/api";
import { Badge, severityTone } from "@/components/ui/Badge";
import { useLocale } from "@/context/LocaleContext";
import { formatDate } from "@/utils/format";

export function DiagnosisCard({ diagnosis }: { diagnosis: DiagnosisSummarySchema }) {
  const { t } = useLocale();
  return (
    <Link
      to={`/diagnoses/${diagnosis.id}`}
      className="flex items-center gap-4 rounded-card border border-line bg-surface p-4 transition-shadow hover:shadow-elevate focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
    >
      <div className="h-16 w-16 shrink-0 overflow-hidden rounded-card bg-canvas">
        {diagnosis.thumbnail_url ? (
          <img src={diagnosis.thumbnail_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-primary/40">
            <svg className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3.75H6.912a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661V18a2.25 2.25 0 002.25 2.25h15a2.25 2.25 0 002.25-2.25v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H15M9 3.75V2.25M15 3.75V2.25" />
            </svg>
          </div>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-display font-semibold text-ink">
            {diagnosis.disease ?? diagnosis.plant ?? "—"}
          </span>
          {diagnosis.severity_level && <Badge tone={severityTone(diagnosis.severity_level)}>{diagnosis.severity_level}</Badge>}
        </div>
        <p className="truncate text-sm text-muted">{diagnosis.plant}</p>
        <p className="text-xs text-muted">{diagnosis.diagnosed_at ? formatDate(diagnosis.diagnosed_at) : ""}</p>
      </div>

      <div className="shrink-0 text-end">
        <p className="font-data text-sm font-semibold text-ink">{Math.round(diagnosis.confidence_score)}%</p>
        <p className="text-xs text-muted">{t.result.confidence}</p>
      </div>
    </Link>
  );
}
