import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { modelsApi } from "@/lib/endpoints/aiFeatures";
import { humanizeLabel } from "@/lib/aiFeatureUi";
import { Card, CardHeader, CardTitle, PageHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageLoader } from "@/components/ui/PageLoader";
import { ReadinessBadge } from "@/components/ai/ReadinessBadge";
import { formatDate } from "@/utils/format";
import type { ModelCard } from "@/types/aiFeatures";

const TASK_ICON = { classification: "leaf", segmentation: "target", outbreak: "pin" } as const;

/** Top-level numeric metrics, plus one level of nesting ("test.mean_iou"). */
function flattenMetrics(metrics: Record<string, unknown>): [string, number][] {
  const out: [string, number][] = [];
  for (const [k, v] of Object.entries(metrics)) {
    if (typeof v === "number") out.push([k, v]);
    else if (v && typeof v === "object" && !Array.isArray(v)) {
      for (const [k2, v2] of Object.entries(v as Record<string, unknown>)) {
        if (typeof v2 === "number") out.push([`${k}.${k2}`, v2]);
      }
    }
  }
  return out.slice(0, 16);
}

function ModelCardView({ card }: { card: ModelCard }) {
  const { t, locale } = useLocale();
  const m = t.models;
  const metrics = flattenMetrics(card.metrics ?? {});
  const rows: [string, string | null | undefined][] = [
    [m.version, card.version],
    [m.architecture, card.architecture],
    [m.datasetVersion, card.dataset_version],
    [m.trainedAt, card.trained_at ? formatDate(card.trained_at, locale) : null],
    [m.classes, card.classes.length ? `${card.classes.length}: ${card.classes.slice(0, 6).map(humanizeLabel).join(", ")}${card.classes.length > 6 ? "…" : ""}` : null],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle icon={TASK_ICON[card.task]}>{m.task[card.task]}</CardTitle>
        <ReadinessBadge readiness={card.readiness} />
      </CardHeader>
      <p className="text-sm leading-relaxed text-muted">{card.message}</p>
      {card.name && <p className="mt-2 font-data text-sm text-ink">{card.name}</p>}
      <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
        {rows.filter(([, v]) => v).map(([k, v]) => (
          <div key={k} className="rounded-2xl bg-ink/[0.035] p-3">
            <dt className="text-xs text-muted">{k}</dt>
            <dd className="break-words font-data text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      <h3 className="mb-2 mt-4 text-sm font-semibold text-ink">{m.metrics}</h3>
      {metrics.length === 0 ? (
        <p className="text-sm text-muted">{m.noMetrics}</p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
          {metrics.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2 border-b border-ink/[0.06] py-1">
              <dt className="truncate text-muted" title={k}>{k}</dt>
              <dd className="font-data text-ink">{Number.isInteger(v) ? v : v.toFixed(3)}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

export default function AdminModelsPage() {
  const { t } = useLocale();
  const models = useAsync(() => modelsApi.list(), []);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title={t.models.title} subtitle={t.models.subtitle} />
      {models.status === "loading" && <PageLoader label={t.common.loading} />}
      {models.status === "error" && <ErrorState message={errorMessage(models.error)} onRetry={models.refetch} />}
      {models.status === "success" && (
        <div className="grid gap-5 lg:grid-cols-2">
          {models.data.map((card) => <ModelCardView key={card.task} card={card} />)}
        </div>
      )}
    </div>
  );
}
