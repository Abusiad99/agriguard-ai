import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { plantsApi } from "@/lib/endpoints/plants";
import { Card, CardHeader, CardTitle, PageHeader } from "@/components/ui/Card";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Icon } from "@/components/ui/Icon";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { Pagination } from "@/components/ui/Pagination";
import { DiagnosisCard } from "@/components/diagnosis/DiagnosisCard";
import { PlantFormModal } from "@/components/plants/PlantFormModal";
import { MeasurementChart } from "@/components/plants/MeasurementChart";
import { formatDate } from "@/utils/format";
import { plantName } from "@/utils/labels";
import type { DecisionStatus } from "@/types/api";

const PAGE_SIZE = 30;

export default function PlantDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useLocale();
  const navigate = useNavigate();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [status, setStatus] = useState<DecisionStatus | "">("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const timeline = useAsync(
    () => plantsApi.timeline(id!, { date_from: dateFrom || undefined, date_to: dateTo || undefined, decision_status: status || undefined, page, page_size: PAGE_SIZE }),
    [id, dateFrom, dateTo, status, page]
  );

  if (timeline.status === "loading") return <PageLoader label={t.common.loading} />;
  if (timeline.status === "error") return <ErrorState message={errorMessage(timeline.error)} onRetry={timeline.refetch} />;

  const { plant, entries, measurement_series: series } = timeline.data;

  const toggle = (diagnosisId: string) =>
    setSelected((prev) => (prev.includes(diagnosisId) ? prev.filter((x) => x !== diagnosisId) : [...prev.slice(-1), diagnosisId]));

  const archive = async () => {
    if (!window.confirm(t.plants.archiveConfirm)) return;
    try {
      await plantsApi.archive(plant.id);
      navigate("/plants");
    } catch (e) {
      setArchiveError(e instanceof Error ? e.message : t.common.unknownError);
    }
  };

  const details: [string, string | null | undefined][] = [
    [t.plants.cropType, plant.crop_type ? plantName(plant.crop_type, t) : null],
    [t.plants.variety, plant.variety],
    [t.plants.plantingDate, plant.planting_date],
    [t.plants.location, plant.location_label],
    [t.plants.environment, plant.growing_environment ? t.plants.environments[plant.growing_environment] : null],
  ];

  return (
    <div className="flex flex-col gap-6 stagger">
      <Link to="/plants" className="group inline-flex w-fit items-center gap-2 py-1 text-sm font-medium text-muted hover:text-primary">
        <span className="flip-rtl inline-flex"><Icon name="arrowLeft" className="h-4 w-4" /></span>
        {t.plants.title}
      </Link>

      <PageHeader
        title={<span dir="auto">{plant.name}</span>}
        subtitle={plant.archived ? t.plants.archived : `${plant.observation_count} ${t.plants.observations}`}
        actions={
          <>
            <Button variant="glass" icon="pencil" onClick={() => setEditing(true)}>{t.plants.edit}</Button>
            {!plant.archived && (
              <ButtonLink to={`/scan?plant=${plant.id}`} icon="camera">{t.plants.scanThisPlant}</ButtonLink>
            )}
          </>
        }
      />

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader>
              <CardTitle icon="chart">{t.plants.measurementChart}</CardTitle>
            </CardHeader>
            {series.length > 0 ? (
              <>
                <MeasurementChart points={series} />
                {timeline.data.measurement_series_note === "mixed_measurement_methods" && (
                  <div className="mt-3"><Alert tone="warning">{t.plants.mixedMethods}</Alert></div>
                )}
              </>
            ) : (
              <p className="text-sm leading-relaxed text-muted">{t.plants.noMeasurements}</p>
            )}
            {series.length > 0 && timeline.data.observations_without_measurement > 0 && (
              <p className="mt-3 text-xs text-muted">
                {t.plants.withoutMeasurement.replace("{count}", String(timeline.data.observations_without_measurement))}
              </p>
            )}
          </Card>

          <Card>
            <CardHeader>
              <CardTitle icon="history">{t.plants.timeline}</CardTitle>
              {selected.length === 2 ? (
                <ButtonLink size="sm" icon="compare" to={`/plants/${plant.id}/compare?a=${selected[0]}&b=${selected[1]}`}>
                  {t.plants.compare}
                </ButtonLink>
              ) : (
                <span className="hidden text-xs text-muted sm:inline">{t.plants.compareSelect}</span>
              )}
            </CardHeader>

            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Input type="date" aria-label={t.plants.filterFrom} value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} />
              <Input type="date" aria-label={t.plants.filterTo} value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }} />
              <Select aria-label={t.history.statusFilter} value={status} onChange={(e) => { setStatus(e.target.value as DecisionStatus | ""); setPage(1); }}>
                <option value="">{t.history.allStatuses}</option>
                <option value="confident">{t.status.confident}</option>
                <option value="uncertain">{t.status.uncertain}</option>
                <option value="inconclusive">{t.status.inconclusive}</option>
                <option value="legacy">{t.status.legacy}</option>
              </Select>
            </div>

            {entries.length === 0 ? (
              <p className="text-sm text-muted">{t.plants.neverObserved}</p>
            ) : (
              <ol className="relative flex flex-col gap-4 border-s-2 border-primary/15 ps-5">
                {entries.map(({ observation, notes, treatment_summary }) => (
                  <li key={observation.id} className="relative">
                    <span className="absolute -start-[1.72rem] top-6 h-3 w-3 rounded-full bg-primary ring-4 ring-canvas" aria-hidden="true" />
                    <DiagnosisCard diagnosis={observation} selectable selected={selected.includes(observation.id)} onSelect={toggle} />
                    {(treatment_summary || notes.some((n) => n.body)) && (
                      <div className="mt-2 flex flex-col gap-1 rounded-xl bg-ink/[0.03] px-3 py-2 text-xs text-muted">
                        {treatment_summary && (
                          <p><span className="font-semibold text-ink">{t.plants.treatment}: </span><span dir="auto">{treatment_summary}</span></p>
                        )}
                        {notes.filter((n) => n.body && n.note_type !== "treatment_applied").slice(-2).map((n) => (
                          <p key={n.id}>
                            <span className="font-semibold text-ink">{t.reliability.noteTypes[n.note_type]}: </span>
                            <span dir="auto">{n.body}</span>
                            {n.created_at && <span> · {formatDate(n.created_at, locale)}</span>}
                          </p>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            )}
            <div className="mt-5">
              <Pagination page={timeline.data.page} totalPages={timeline.data.total_pages} onChange={setPage} />
            </div>
          </Card>
        </div>

        <aside className="flex flex-col gap-5">
          <Card>
            <CardHeader>
              <CardTitle icon="leaf">{plant.name}</CardTitle>
            </CardHeader>
            <dl className="flex flex-col gap-2.5 text-sm">
              {details.filter(([, v]) => v).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="text-muted">{k}</dt>
                  <dd dir="auto" className="text-end font-medium text-ink">{v}</dd>
                </div>
              ))}
            </dl>
            {plant.notes && <p dir="auto" className="mt-4 whitespace-pre-wrap text-start text-sm text-ink">{plant.notes}</p>}
            {!plant.archived && (
              <Button variant="ghost" size="sm" icon="archive" className="mt-4" onClick={() => void archive()}>
                {t.plants.archive}
              </Button>
            )}
            {archiveError && <div className="mt-3"><Alert tone="error">{archiveError}</Alert></div>}
          </Card>
          <ButtonLink to={`/assistant?plant=${plant.id}`} variant="glass" icon="chat" fullWidth>
            {t.reliability.askAssistant}
          </ButtonLink>
        </aside>
      </div>

      {editing && (
        <PlantFormModal plant={plant} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); timeline.refetch(); }} />
      )}
    </div>
  );
}
