import { Link } from "react-router-dom";
import type { DiagnosisSummarySchema } from "@/types/api";
import { Badge, severityTone } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { useLocale } from "@/context/LocaleContext";
import { formatDate } from "@/utils/format";
import { SEVERITY_COLOR, useSeverityLabel } from "./severity";

export function DiagnosisCard({ diagnosis }: { diagnosis: DiagnosisSummarySchema }) {
  const { t, locale } = useLocale();
  const severityLabel = useSeverityLabel();
  const isHealthy = !diagnosis.disease;
  const ringColor = diagnosis.severity_level ? SEVERITY_COLOR[diagnosis.severity_level] : "rgb(var(--c-primary))";

  return (
    <Link
      to={`/diagnoses/${diagnosis.id}`}
      className="glass group relative flex items-center gap-4 rounded-[1.25rem] p-3 pe-4 transition-all duration-300 ease-out-expo hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-elevate sm:gap-5"
    >
      <div className="relative h-[4.5rem] w-[4.5rem] shrink-0 overflow-hidden rounded-2xl bg-primary/10 ring-2 ring-offset-2 ring-offset-surface" style={{ ["--tw-ring-color" as string]: ringColor }}>
        {diagnosis.thumbnail_url ? (
          <img src={diagnosis.thumbnail_url} alt="" className="h-full w-full object-cover transition-transform duration-500 ease-out-expo group-hover:scale-110" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-primary/60">
            <Icon name={isHealthy ? "leaf" : "photo"} className="h-7 w-7" />
          </div>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-display text-[1.05rem] font-semibold text-ink">
            {diagnosis.disease ?? diagnosis.plant ?? "—"}
          </span>
          {diagnosis.severity_level ? (
            <Badge tone={severityTone(diagnosis.severity_level)}>{severityLabel(diagnosis.severity_level)}</Badge>
          ) : (
            isHealthy && <Badge tone="primary">{t.dashboard.healthy}</Badge>
          )}
        </div>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          {diagnosis.plant && !isHealthy && (
            <span className="inline-flex items-center gap-1.5">
              <Icon name="leaf" className="h-4 w-4 text-primary/80" />
              {diagnosis.plant}
            </span>
          )}
          {diagnosis.diagnosed_at && (
            <span className="inline-flex items-center gap-1.5">
              <Icon name="calendar" className="h-4 w-4" />
              {formatDate(diagnosis.diagnosed_at, locale)}
            </span>
          )}
        </p>
      </div>

      <div className="hidden shrink-0 items-center gap-3 sm:flex">
        <ConfidenceDial value={diagnosis.confidence_score} label={t.result.confidence} />
      </div>
      <span className="flip-rtl inline-flex shrink-0 text-muted transition-all duration-300 ease-spring group-hover:translate-x-1 group-hover:text-primary">
        <Icon name="chevronRight" className="h-5 w-5" strokeWidth={2} />
      </span>
    </Link>
  );
}

function ConfidenceDial({ value, label }: { value: number; label: string }) {
  const r = 20;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-2.5" aria-label={`${label}: ${Math.round(v)}%`}>
      <div className="relative h-12 w-12">
        <svg viewBox="0 0 48 48" className="h-12 w-12 -rotate-90" aria-hidden="true">
          <circle cx="24" cy="24" r={r} fill="none" style={{ stroke: "rgb(var(--c-ink) / 0.08)" }} strokeWidth="4" />
          <circle
            cx="24"
            cy="24"
            r={r}
            fill="none"
            style={{ stroke: "rgb(var(--c-primary))" }}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={c - (v / 100) * c}
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center font-data text-[11px] font-semibold tabular-nums text-ink">
          {Math.round(v)}
        </span>
      </div>
      <span className="hidden text-xs text-muted md:block">{label}</span>
    </div>
  );
}
