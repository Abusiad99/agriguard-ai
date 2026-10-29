import { Link } from "react-router-dom";
import type { DiagnosisSummarySchema } from "@/types/api";
import { Icon } from "@/components/ui/Icon";
import { useLocale } from "@/context/LocaleContext";
import { formatDate } from "@/utils/format";
import { labelDisplay, plantName } from "@/utils/labels";
import { StatusBadge } from "./ReliabilityPanels";

const STATUS_RING: Record<string, string> = {
  confident: "rgb(var(--c-primary))",
  uncertain: "rgb(var(--c-mild))",
  inconclusive: "rgb(var(--c-moderate))",
  legacy: "rgb(var(--c-ink) / 0.25)",
};

export function DiagnosisCard({ diagnosis, selectable, selected, onSelect }: {
  diagnosis: DiagnosisSummarySchema;
  selectable?: boolean;
  selected?: boolean;
  onSelect?: (id: string) => void;
}) {
  const { t, locale } = useLocale();
  const status = diagnosis.decision_status ?? "legacy";
  const ringColor = STATUS_RING[status] ?? STATUS_RING.legacy;
  const title =
    status === "inconclusive"
      ? t.status.noConditionNamed
      : diagnosis.predicted_label
        ? labelDisplay(diagnosis.predicted_label, t)
        : diagnosis.disease ?? (diagnosis.plant ? plantName(diagnosis.plant, t) : "—");

  return (
    <div className={`glass group relative flex items-center gap-4 rounded-[1.25rem] p-3 pe-4 transition-all duration-300 ease-out-expo hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-elevate sm:gap-5 ${selected ? "ring-2 ring-primary" : ""}`}>
      {selectable && (
        <input
          type="checkbox"
          checked={Boolean(selected)}
          onChange={() => onSelect?.(diagnosis.id)}
          aria-label={title}
          className="h-5 w-5 shrink-0 accent-[rgb(var(--c-primary))]"
        />
      )}
      <Link to={`/diagnoses/${diagnosis.id}`} className="flex min-w-0 flex-1 items-center gap-4 sm:gap-5">
      <div className="relative h-[4.5rem] w-[4.5rem] shrink-0 overflow-hidden rounded-2xl bg-primary/10 ring-2 ring-offset-2 ring-offset-surface" style={{ ["--tw-ring-color" as string]: ringColor }}>
        {diagnosis.thumbnail_url ? (
          <img src={diagnosis.thumbnail_url} alt="" className="h-full w-full object-cover transition-transform duration-500 ease-out-expo group-hover:scale-110" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-primary/60">
            <Icon name="photo" className="h-7 w-7" />
          </div>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span dir="auto" className="truncate font-display text-[1.05rem] font-semibold text-ink">
            {title}
          </span>
          <StatusBadge status={status} />
        </div>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          {diagnosis.plant_profile_name && (
            <span className="inline-flex items-center gap-1.5">
              <Icon name="leaf" className="h-4 w-4 text-primary/80" />
              {diagnosis.plant_profile_name}
            </span>
          )}
          {diagnosis.affected_area_pct != null && (
            <span className="inline-flex items-center gap-1.5">
              <Icon name="chart" className="h-4 w-4" />
              {diagnosis.affected_area_pct.toFixed(1)}%
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

      {status !== "inconclusive" && (
        <div className="hidden shrink-0 items-center gap-3 sm:flex">
          <ConfidenceDial value={diagnosis.confidence_score} label={t.result.confidence} />
        </div>
      )}
      <span className="flip-rtl inline-flex shrink-0 text-muted transition-all duration-300 ease-spring group-hover:translate-x-1 group-hover:text-primary">
        <Icon name="chevronRight" className="h-5 w-5" strokeWidth={2} />
      </span>
      </Link>
    </div>
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
