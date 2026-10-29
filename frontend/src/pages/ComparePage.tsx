import { Link, useParams, useSearchParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { plantsApi } from "@/lib/endpoints/plants";
import { Card, CardHeader, CardTitle, PageHeader } from "@/components/ui/Card";
import { Alert } from "@/components/ui/Alert";
import { Icon } from "@/components/ui/Icon";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { StatusBadge } from "@/components/diagnosis/ReliabilityPanels";
import { formatDate } from "@/utils/format";
import { labelDisplay } from "@/utils/labels";
import type { DiagnosisResponse } from "@/types/api";

/** Side-by-side comparison of two observations of the same plant. Wording is
 * deliberately cautious: a different prediction is never presented as a change in
 * plant health, and measurements are compared only when comparable. */
export default function ComparePage() {
  const { id } = useParams<{ id: string }>();
  const [params] = useSearchParams();
  const a = params.get("a") ?? "";
  const b = params.get("b") ?? "";
  const { t, locale } = useLocale();
  const result = useAsync(() => plantsApi.compare(id!, a, b), [id, a, b]);

  if (result.status === "loading") return <PageLoader label={t.common.loading} />;
  if (result.status === "error") return <ErrorState message={errorMessage(result.error)} onRetry={result.refetch} />;

  const { comparison: c } = result.data;
  const earlier = c.earlier_id === result.data.a.diagnosis_id ? result.data.a : result.data.b;
  const later = earlier === result.data.a ? result.data.b : result.data.a;
  const m = c.measurement;

  return (
    <div className="flex flex-col gap-6 stagger">
      <Link to={`/plants/${id}`} className="group inline-flex w-fit items-center gap-2 py-1 text-sm font-medium text-muted hover:text-primary">
        <span className="flip-rtl inline-flex"><Icon name="arrowLeft" className="h-4 w-4" /></span>
        {t.plants.timeline}
      </Link>
      <PageHeader
        title={t.plants.compareTitle}
        subtitle={c.days_between != null ? t.compare.daysBetween.replace("{days}", String(Math.round(c.days_between))) : undefined}
      />

      <div className="grid gap-5 md:grid-cols-2">
        <ObservationColumn label={t.compare.earlier} d={earlier} locale={locale} />
        <ObservationColumn label={t.compare.later} d={later} locale={locale} />
      </div>

      <Card highlight>
        <CardHeader>
          <CardTitle icon="compare">{t.compare.measurement}</CardTitle>
        </CardHeader>
        <p className="text-[0.98rem] font-medium text-ink">{t.compare.summaries[c.summary]}</p>
        {m.delta_pct_points != null && (
          <p className="mt-2 font-data text-sm tabular-nums text-muted" dir="ltr">
            {m.earlier_pct?.toFixed(1)}% → {m.later_pct?.toFixed(1)}% ({m.delta_pct_points > 0 ? "+" : ""}{m.delta_pct_points.toFixed(1)} pp
            {m.tolerance_pct_points != null ? `, ±${m.tolerance_pct_points.toFixed(1)} pp` : ""})
          </p>
        )}
        {m.reason && <p className="mt-2 text-sm text-muted">{t.compare.reasons[m.reason] ?? m.reason}</p>}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle icon="target">{t.compare.predictions}</CardTitle>
        </CardHeader>
        <p className="text-sm leading-relaxed text-ink">
          {c.prediction_change === "same_prediction"
            ? t.compare.samePrediction
            : c.prediction_change === "different_prediction"
              ? t.compare.differentPrediction
              : t.compare.predictionUnavailable}
        </p>
      </Card>

      {c.comparability_issues.length > 0 && (
        <Alert tone="warning" title={t.compare.caution}>
          {c.comparability_issues.map((i) => t.compare.issues[i] ?? i).join(" · ")}
        </Alert>
      )}
    </div>
  );
}

function ObservationColumn({ label, d, locale }: { label: string; d: DiagnosisResponse; locale: string }) {
  const { t } = useLocale();
  const status = d.decision_status ?? "legacy";
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold uppercase tracking-wide text-muted">{label}</span>
        <StatusBadge status={status} />
      </div>
      <Link to={`/diagnoses/${d.diagnosis_id}`} className="overflow-hidden rounded-2xl">
        {d.original_image_url ? (
          <img src={d.original_image_url} alt={label} className="aspect-square w-full object-cover" />
        ) : (
          <div className="flex aspect-square items-center justify-center bg-ink/[0.04] text-muted"><Icon name="photo" className="h-8 w-8" /></div>
        )}
      </Link>
      <p dir="auto" className="text-start font-medium text-ink">
        {status === "inconclusive" ? t.status.noConditionNamed : labelDisplay(d.predicted_label, t) || d.disease?.name || "—"}
      </p>
      <p className="text-xs text-muted">
        {d.diagnosed_at && formatDate(d.diagnosed_at, locale)}
        {status !== "inconclusive" && ` · ${t.result.confidence} ${d.confidence_score.toFixed(0)}%`}
      </p>
    </Card>
  );
}
