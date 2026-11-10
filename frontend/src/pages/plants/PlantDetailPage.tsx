import { useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { plantsApi, type TreatmentInput } from "@/lib/endpoints/aiFeatures";
import { scansApi } from "@/lib/endpoints/scans";
import { humanizeLabel, recoveryTone } from "@/lib/aiFeatureUi";
import { Card, CardHeader, CardTitle, PageHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Alert } from "@/components/ui/Alert";
import { Input, Textarea } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Tabs } from "@/components/ui/Tabs";
import { Modal } from "@/components/ui/Modal";
import { Icon } from "@/components/ui/Icon";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageLoader } from "@/components/ui/PageLoader";
import { LineChart } from "@/components/charts/MiniCharts";
import { CompareSlider } from "@/components/plants/CompareSlider";
import { PlantForm } from "@/components/plants/PlantForm";
import { GenerateReportButton } from "@/components/reports/GenerateReportButton";
import { formatDate } from "@/utils/format";
import { ApiError, isUnrecognizedPlant } from "@/types/api";
import type {
  Assessment,
  PlantScan,
  Reminder,
  TimelineEvent,
  TrackedPlantDetail,
  TreatmentCategoryRecorded,
  TreatmentStage,
} from "@/types/aiFeatures";

const STAGES: TreatmentStage[] = ["unknown", "before_treatment", "during_treatment", "after_treatment"];
const CATEGORIES: TreatmentCategoryRecorded[] = ["organic", "chemical", "biological", "cultural", "other"];

/** Today's date in the user's local calendar, as YYYY-MM-DD. */
const localToday = () => new Date().toLocaleDateString("en-CA");

function formatValue(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "string") return humanizeLabel(v);
  if (Array.isArray(v)) return String(v.length);
  return "—";
}

function indicatorValue(ind: Assessment["indicators"][number]): string {
  if ("value" in ind && ind.value != null) return formatValue(ind.value);
  if ("from" in ind || "to" in ind) return `${formatValue(ind.from)} → ${formatValue(ind.to)}`;
  if ("diagnosis_ids" in ind) return formatValue(ind.diagnosis_ids);
  return "—";
}

function Section({ icon, title, children, actions }: { icon: Parameters<typeof CardTitle>[0]["icon"]; title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle icon={icon}>{title}</CardTitle>
        {actions}
      </CardHeader>
      {children}
    </Card>
  );
}

export default function PlantDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useLocale();
  const p = t.plants;
  const d = p.detail;
  const detail = useAsync(() => plantsApi.get(id!), [id]);
  const timeline = useAsync(() => plantsApi.timeline(id!), [id]);
  // Keep showing the last loaded data while a refresh after an action is in flight,
  // so open forms and the comparison don't unmount behind a full-page loader.
  const shown = useRef<{ id?: string; detail?: TrackedPlantDetail; timeline?: TimelineEvent[] }>({});
  if (shown.current.id !== id) shown.current = { id };
  if (detail.status === "success") shown.current.detail = detail.data;
  if (timeline.status === "success") shown.current.timeline = timeline.data.items;
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const refresh = () => {
    detail.refetch();
    timeline.refetch();
  };

  const run = async (key: string, action: () => Promise<unknown>) => {
    setActionError(null);
    setBusy(key);
    try {
      await action();
      refresh();
      return true;
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : t.common.unknownError);
      return false;
    } finally {
      setBusy(null);
    }
  };

  const data = shown.current.detail;
  if (detail.status === "error" && !data) return <ErrorState message={errorMessage(detail.error)} onRetry={detail.refetch} />;
  if (!data) return <PageLoader label={t.common.loading} />;

  const { plant, assessment, treatments, reminders } = data;
  const events = shown.current.timeline ?? [];
  const scans = [...data.scans].sort((a, b) => (a.diagnosed_at ?? "").localeCompare(b.diagnosed_at ?? ""));
  const archived = plant.status === "archived";

  return (
    <div className="flex flex-col gap-5 stagger">
      <Link to="/plants" className="group inline-flex w-fit items-center gap-2 rounded-xl py-1 text-sm font-medium text-muted transition-colors hover:text-primary">
        <span className="flip-rtl inline-flex"><Icon name="arrowLeft" className="h-4 w-4" /></span>
        {d.back}
      </Link>

      <PageHeader
        title={plant.name}
        subtitle={[plant.crop, plant.species].filter(Boolean).join(" · ") || undefined}
        eyebrow={archived ? <Badge tone="neutral">{p.archived}</Badge> : undefined}
        actions={
          <>
            <Button variant="secondary" size="sm" icon="pencil" onClick={() => setEditing(true)}>{d.edit}</Button>
            <Button variant="ghost" size="sm" isLoading={busy === "archive"}
                    onClick={() => void run("archive", () => plantsApi.update(plant.id, { status: archived ? "active" : "archived" }))}>
              {archived ? d.unarchive : d.archive}
            </Button>
          </>
        }
      />
      {plant.notes && <p dir="auto" className="max-w-prose whitespace-pre-line text-sm text-muted">{plant.notes}</p>}
      <div className="w-fit">
        <GenerateReportButton request={{ type: "plant_progress", subject_id: plant.id }} label={t.reports.progressReport} />
      </div>
      {actionError && <Alert tone="error">{actionError}</Alert>}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex flex-col gap-5">
          <AssessmentCard assessment={assessment} busy={busy === "reassess"}
                          onRecheck={() => void run("reassess", () => plantsApi.reassess(plant.id))} />

          <Section icon="chart" title={d.areaChart}>
            {assessment.area_series.length >= 2 ? (
              <LineChart ariaLabel={d.areaChart} unit="%"
                         points={assessment.area_series.map((s) => ({ label: s.taken_at.slice(5, 10), value: s.area_pct }))} />
            ) : (
              <p className="text-sm text-muted">{d.areaChartEmpty}</p>
            )}
          </Section>

          {scans.length >= 2 && <CompareCard plantId={plant.id} scans={scans} />}

          <Section icon="camera" title={d.scans}>
            {scans.length === 0 ? (
              <p className="text-sm text-muted">{p.noScansYet}</p>
            ) : (
              <ul className="flex flex-col divide-y divide-ink/[0.06]">
                {scans.map((s) => (
                  <li key={s.diagnosis_id} className="flex flex-wrap items-center gap-4 py-3">
                    {s.image_url ? (
                      <img src={s.image_url} alt="" className="h-16 w-16 shrink-0 rounded-xl object-cover ring-1 ring-ink/10" />
                    ) : (
                      <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-xl bg-ink/[0.05]"><Icon name="photo" className="h-6 w-6 text-muted" /></span>
                    )}
                    <div className="min-w-0 flex-1 text-sm">
                      <p className="font-medium text-ink">
                        {s.is_healthy ? t.dashboard.healthy : humanizeLabel(s.predicted_condition) || "—"}
                        {s.confidence_score != null && <span className="ms-2 font-data text-xs text-muted">{s.confidence_score.toFixed(0)}%</span>}
                      </p>
                      <p className="text-xs text-muted">
                        {s.diagnosed_at ? formatDate(s.diagnosed_at, locale) : ""} · {p.stages[s.treatment_stage]}
                        {s.affected_area_pct != null && <> · {t.localization.affectedArea}: {s.affected_area_pct.toFixed(1)}%</>}
                      </p>
                      {s.image_quality && !s.image_quality.acceptable && (
                        <p className="text-xs text-severity-mild">
                          {t.quality.title}: {s.image_quality.issues.map((i) => t.quality.issues[i]).join(", ")}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-1">
                      <Link to={`/diagnoses/${s.diagnosis_id}`} className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-primary hover:bg-primary/10">
                        {d.openDiagnosis}
                      </Link>
                      <Button size="sm" variant="ghost" isLoading={busy === `unlink-${s.diagnosis_id}`}
                              onClick={() => void run(`unlink-${s.diagnosis_id}`, () => plantsApi.unlinkScan(plant.id, s.diagnosis_id))}>
                        {d.remove}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {!archived && <FollowUpScan plantId={plant.id} linkedIds={scans.map((s) => s.diagnosis_id)} onDone={refresh} />}
          </Section>

          <Section icon="calendar" title={d.timeline}>
            {events.length > 0 ? (
              <ol className="relative flex flex-col gap-3 border-s border-ink/10 ps-5">
                {events.map((e) => (
                  <li key={e.id} className="text-sm">
                    <span className="absolute -start-1.5 mt-1.5 h-3 w-3 rounded-full bg-primary/70 ring-2 ring-surface" aria-hidden="true" />
                    <p className="font-medium text-ink">{(p.events as Record<string, string>)[e.event_type] ?? humanizeLabel(e.event_type)}</p>
                    <p className="text-xs text-muted">{formatDate(e.occurred_at, locale)}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted">—</p>
            )}
          </Section>
        </div>

        <aside className="flex flex-col gap-5">
          <Section icon="beaker" title={d.treatments}>
            <p className="mb-4 rounded-2xl bg-severity-mild-bg/60 p-3 text-xs leading-relaxed text-ink">{d.treatmentDisclaimer}</p>
            {treatments.length === 0 ? (
              <p className="text-sm text-muted">{d.noTreatments}</p>
            ) : (
              <ul className="flex flex-col gap-2.5">
                {treatments.map((tr) => (
                  <li key={tr.id} className="rounded-2xl bg-ink/[0.035] p-3 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p dir="auto" className="font-medium text-ink">{tr.name}</p>
                        <p className="text-xs text-muted">{p.treatmentCategory[tr.category]} · {tr.applied_on} · {d.userRecorded}</p>
                      </div>
                      <Button size="sm" variant="ghost" icon="close" aria-label={t.common.close} isLoading={busy === `tr-${tr.id}`}
                              onClick={() => void run(`tr-${tr.id}`, () => plantsApi.deleteTreatment(plant.id, tr.id))} />
                    </div>
                    {tr.dosage_text && <p dir="auto" className="mt-1 text-xs text-ink">{p.treatmentForm.dosage}: {tr.dosage_text}</p>}
                    {tr.application_notes && <p dir="auto" className="mt-1 text-xs text-muted">{tr.application_notes}</p>}
                    {tr.documentation_ref && <p dir="auto" className="mt-1 text-xs text-muted">{p.treatmentForm.documentation}: {tr.documentation_ref}</p>}
                  </li>
                ))}
              </ul>
            )}
            {!archived && <TreatmentForm busy={busy === "treatment"} onSubmit={(body) => run("treatment", () => plantsApi.addTreatment(plant.id, body))} />}
          </Section>

          <Section icon="calendar" title={d.followUps}>
            {reminders.length === 0 ? (
              <p className="text-sm text-muted">{d.noReminders}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {reminders.map((r) => (
                  <ReminderRow key={r.id} reminder={r} busy={busy === `rem-${r.id}`}
                               onStatus={(status) => void run(`rem-${r.id}`, () => plantsApi.setReminderStatus(plant.id, r.id, status))} />
                ))}
              </ul>
            )}
            {!archived && <ReminderForm busy={busy === "reminder"} onSubmit={(body) => run("reminder", () => plantsApi.addReminder(plant.id, body))} />}
          </Section>
        </aside>
      </div>

      <Modal isOpen={editing} onClose={() => setEditing(false)} title={d.edit}>
        <PlantForm initial={plant} onCancel={() => setEditing(false)}
                   onSubmit={async (body) => {
                     await plantsApi.update(plant.id, body);
                     setEditing(false);
                     refresh();
                   }} />
      </Modal>
    </div>
  );
}

function AssessmentCard({ assessment, busy, onRecheck }: { assessment: Assessment; busy: boolean; onRecheck: () => void }) {
  const { t } = useLocale();
  const p = t.plants;
  return (
    <Card highlight>
      <CardHeader>
        <CardTitle icon="heart">{p.detail.recovery}</CardTitle>
        <Button size="sm" variant="secondary" icon="refresh" isLoading={busy} onClick={onRecheck}>{p.detail.recheck}</Button>
      </CardHeader>
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={recoveryTone(assessment.status)}>{p.status[assessment.status]}</Badge>
        <span className="text-xs text-muted">{p.detail.method}: <span className="font-data">{assessment.method_version}</span></span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-ink">{p.statusHelp[assessment.status]}</p>

      {assessment.indicators.length > 0 && (
        <>
          <h3 className="mb-2 mt-5 text-sm font-semibold text-ink">{p.detail.indicators}</h3>
          <dl className="grid gap-2 sm:grid-cols-2">
            {assessment.indicators.map((ind) => (
              <div key={ind.code} className="rounded-2xl bg-ink/[0.035] p-3">
                <dt className="text-xs text-muted">{(p.indicator as Record<string, string>)[ind.code] ?? humanizeLabel(ind.code)}</dt>
                <dd className="font-data text-sm font-semibold text-ink">{indicatorValue(ind)}</dd>
              </div>
            ))}
          </dl>
        </>
      )}

      {assessment.limitations.length > 0 && (
        <>
          <h3 className="mb-2 mt-5 text-sm font-semibold text-ink">{p.detail.limitations}</h3>
          <ul className="flex list-disc flex-col gap-1 ps-5 text-sm text-muted">
            {assessment.limitations.map((code) => (
              <li key={code}>{(p.limitation as Record<string, string>)[code] ?? humanizeLabel(code)}</li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

function CompareCard({ plantId, scans }: { plantId: string; scans: PlantScan[] }) {
  const { t, locale } = useLocale();
  const d = t.plants.detail;
  const [first, setFirst] = useState(scans[0].diagnosis_id);
  const [second, setSecond] = useState(scans[scans.length - 1].diagnosis_id);
  const [mode, setMode] = useState("side");
  const result = useAsync(() => plantsApi.compare(plantId, first, second), [plantId, first, second]);
  const label = (s: PlantScan) => `${s.diagnosed_at ? formatDate(s.diagnosed_at, locale) : s.diagnosis_id.slice(0, 8)} · ${t.plants.stages[s.treatment_stage]}`;

  return (
    <Card>
      <CardHeader>
        <CardTitle icon="eye">{d.compare}</CardTitle>
      </CardHeader>
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <Select name="compare-first" label={d.firstScan} value={first} onChange={(e) => setFirst(e.target.value)}>
          {scans.map((s) => <option key={s.diagnosis_id} value={s.diagnosis_id}>{label(s)}</option>)}
        </Select>
        <Select name="compare-second" label={d.secondScan} value={second} onChange={(e) => setSecond(e.target.value)}>
          {scans.map((s) => <option key={s.diagnosis_id} value={s.diagnosis_id}>{label(s)}</option>)}
        </Select>
      </div>
      {result.status === "loading" && <PageLoader label={t.common.loading} />}
      {result.status === "error" && <Alert tone="error">{errorMessage(result.error)}</Alert>}
      {result.status === "success" && (
        <>
          <div className="mb-3 w-fit">
            <Tabs tabs={[{ key: "side", label: d.sideBySide }, { key: "slider", label: d.slider }]} active={mode} onChange={setMode} />
          </div>
          {result.data.first.image_url && result.data.second.image_url && (
            mode === "slider" ? (
              <CompareSlider before={result.data.first.image_url} after={result.data.second.image_url}
                             beforeLabel={d.firstScan} afterLabel={d.secondScan} />
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {[result.data.first, result.data.second].map((s, i) => (
                  <figure key={i}>
                    <img src={s.image_url!} alt={i === 0 ? d.firstScan : d.secondScan} className="w-full rounded-2xl object-cover ring-1 ring-ink/10" />
                    <figcaption className="mt-1 text-xs text-muted">
                      {i === 0 ? d.firstScan : d.secondScan} · {s.is_healthy ? t.dashboard.healthy : humanizeLabel(s.predicted_condition)}
                    </figcaption>
                  </figure>
                ))}
              </div>
            )
          )}
          <dl className="mt-4 grid gap-2 sm:grid-cols-3">
            {[
              [d.daysBetween, result.data.checks.days_between],
              [d.lightingDiff, result.data.checks.lighting_difference],
              [d.resolutionRatio, result.data.checks.resolution_ratio],
            ].map(([k, v]) => (
              <div key={k as string} className="rounded-2xl bg-ink/[0.035] p-3">
                <dt className="text-xs text-muted">{k}</dt>
                <dd className="font-data text-sm font-semibold text-ink">{v != null ? formatValue(v) : "—"}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-4 rounded-2xl bg-ink/[0.035] p-4 text-sm">
            {result.data.area_change ? (
              <p className="text-ink">
                <span className="font-semibold">{d.measuredChange}: </span>
                <span className="font-data">
                  {result.data.area_change.from.toFixed(1)}% → {result.data.area_change.to.toFixed(1)}% (
                  {result.data.area_change.change_pct_points > 0 ? "+" : ""}{result.data.area_change.change_pct_points.toFixed(1)} pp)
                </span>
              </p>
            ) : (
              <p className="text-muted">{d.noMeasuredChange}</p>
            )}
          </div>
          {result.data.limitations.length > 0 && (
            <ul className="mt-3 flex list-disc flex-col gap-1 ps-5 text-xs text-muted">
              {result.data.limitations.map((code) => (
                <li key={code}>{(t.plants.limitation as Record<string, string>)[code] ?? humanizeLabel(code)}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </Card>
  );
}

function FollowUpScan({ plantId, linkedIds, onDone }: { plantId: string; linkedIds: string[]; onDone: () => void }) {
  const { t, locale } = useLocale();
  const d = t.plants.detail;
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<TreatmentStage>("unknown");
  const [existing, setExisting] = useState("");
  const [busy, setBusy] = useState<"upload" | "link" | null>(null);
  const [message, setMessage] = useState<{ tone: "error" | "warning"; text: string } | null>(null);
  const recent = useAsync(() => scansApi.listDiagnoses({ page_size: 50 }), [plantId]);
  const candidates = useMemo(
    () => (recent.status === "success" ? recent.data.items.filter((i) => !linkedIds.includes(i.id)) : []),
    [recent, linkedIds],
  );

  const act = async (kind: "upload" | "link", action: () => Promise<void>) => {
    setMessage(null);
    setBusy(kind);
    try {
      await action();
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof ApiError ? err.message : t.common.unknownError });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mt-5 grid gap-5 border-t border-ink/[0.07] pt-5 md:grid-cols-2">
      <form className="flex flex-col gap-2" onSubmit={(e) => {
        e.preventDefault();
        if (!file) return;
        void act("upload", async () => {
          const res = await scansApi.createScan({ image: file, trackedPlantId: plantId, treatmentStage: stage });
          if (isUnrecognizedPlant(res)) {
            setMessage({ tone: "warning", text: res.message });
          } else {
            setFile(null);
            if (fileRef.current) fileRef.current.value = "";
            onDone();
          }
        });
      }}>
        <p className="text-sm font-semibold text-ink">{d.addFollowUp}</p>
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" aria-label={d.choosePhoto}
               className="text-sm file:me-3 file:rounded-lg file:border-0 file:bg-primary-light file:px-3 file:py-1.5 file:text-primary-dark"
               onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Select name="followup-stage" label={d.stage} value={stage} onChange={(e) => setStage(e.target.value as TreatmentStage)}>
          {STAGES.map((s) => <option key={s} value={s}>{t.plants.stages[s]}</option>)}
        </Select>
        <Button type="submit" size="sm" icon="upload" isLoading={busy === "upload"} disabled={!file}>{d.upload}</Button>
      </form>
      <form className="flex flex-col gap-2" onSubmit={(e) => {
        e.preventDefault();
        if (!existing) return;
        void act("link", async () => {
          await plantsApi.linkScan(plantId, existing, stage);
          setExisting("");
          onDone();
        });
      }}>
        <p className="text-sm font-semibold text-ink">{d.linkExisting}</p>
        {candidates.length === 0 ? (
          <p className="text-sm text-muted">{d.noUnlinked}</p>
        ) : (
          <>
            <Select name="link-existing" label={d.linkExisting} value={existing} onChange={(e) => setExisting(e.target.value)}>
              <option value="">{d.chooseScan}</option>
              {candidates.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.diagnosed_at ? formatDate(c.diagnosed_at, locale) : c.id.slice(0, 8)} · {c.plant ?? ""} {c.disease ? `· ${c.disease}` : ""}
                </option>
              ))}
            </Select>
            <Button type="submit" size="sm" variant="secondary" isLoading={busy === "link"} disabled={!existing}>{d.attach}</Button>
          </>
        )}
      </form>
      {message && <div className="md:col-span-2"><Alert tone={message.tone}>{message.text}</Alert></div>}
    </div>
  );
}

function TreatmentForm({ busy, onSubmit }: { busy: boolean; onSubmit: (body: TreatmentInput) => Promise<boolean> }) {
  const { t } = useLocale();
  const f = t.plants.treatmentForm;
  const empty = { name: "", category: "other" as TreatmentCategoryRecorded, applied_on: localToday(), dosage_text: "", application_notes: "", documentation_ref: "", follow_up_on: "" };
  const [form, setForm] = useState(empty);
  const [open, setOpen] = useState(false);
  const set = (k: keyof typeof empty) => (e: { target: { value: string } }) => setForm((prev) => ({ ...prev, [k]: e.target.value }));

  if (!open) {
    return <Button className="mt-4" size="sm" variant="secondary" icon="plus" onClick={() => setOpen(true)}>{t.plants.detail.addTreatment}</Button>;
  }
  return (
    <form className="mt-4 flex flex-col gap-2.5 border-t border-ink/[0.07] pt-4" onSubmit={(e) => {
      e.preventDefault();
      if (!form.name.trim()) return;
      void onSubmit({
        name: form.name.trim(),
        category: form.category,
        applied_on: form.applied_on,
        dosage_text: form.dosage_text.trim() || null,
        application_notes: form.application_notes.trim() || null,
        documentation_ref: form.documentation_ref.trim() || null,
        follow_up_on: form.follow_up_on || null,
      }).then((ok) => {
        if (ok) {
          setForm(empty);
          setOpen(false);
        }
      });
    }}>
      <Input name="treatment-name" label={f.name} value={form.name} maxLength={200} onChange={set("name")} required />
      <Select name="treatment-category" label={f.category} value={form.category} onChange={set("category")}>
        {CATEGORIES.map((c) => <option key={c} value={c}>{t.plants.treatmentCategory[c]}</option>)}
      </Select>
      <Input name="treatment-applied-on" label={f.appliedOn} type="date" value={form.applied_on} max={localToday()} onChange={set("applied_on")} required />
      <Input name="treatment-dosage" label={f.dosage} value={form.dosage_text} maxLength={500} onChange={set("dosage_text")} />
      <Textarea name="treatment-notes" label={f.notes} value={form.application_notes} maxLength={4000} rows={2} onChange={set("application_notes")} />
      <Input name="treatment-doc" label={f.documentation} value={form.documentation_ref} maxLength={500} onChange={set("documentation_ref")} />
      <Input name="treatment-follow-up" label={f.followUpOn} type="date" value={form.follow_up_on} onChange={set("follow_up_on")} />
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>{t.common.cancel}</Button>
        <Button type="submit" size="sm" isLoading={busy}>{t.common.save}</Button>
      </div>
    </form>
  );
}

function ReminderRow({ reminder, busy, onStatus }: { reminder: Reminder; busy: boolean; onStatus: (s: Reminder["status"]) => void }) {
  const { t } = useLocale();
  const r = t.plants.reminders;
  const open = reminder.state === "pending" || reminder.state === "overdue";
  const tone = reminder.state === "overdue" ? "severe" : reminder.state === "completed" ? "primary" : "neutral";
  const stateLabel = reminder.state === "pending" ? r.due : r[reminder.state];
  return (
    <li className="rounded-2xl bg-ink/[0.035] p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium text-ink">{r[reminder.kind]}</span>
        <Badge tone={tone}>{stateLabel} {reminder.due_on}</Badge>
      </div>
      {reminder.note && <p dir="auto" className="mt-1 text-xs text-muted">{reminder.note}</p>}
      {open && (
        <div className="mt-2 flex gap-2">
          <Button size="sm" variant="secondary" icon="check" isLoading={busy} onClick={() => onStatus("completed")}>{r.done}</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onStatus("dismissed")}>{r.dismiss}</Button>
        </div>
      )}
    </li>
  );
}

function ReminderForm({ busy, onSubmit }: { busy: boolean; onSubmit: (body: { kind: Reminder["kind"]; due_on: string; note?: string | null }) => Promise<boolean> }) {
  const { t } = useLocale();
  const r = t.plants.reminders;
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Reminder["kind"]>("next_scan");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");

  if (!open) {
    return <Button className="mt-4" size="sm" variant="secondary" icon="plus" onClick={() => setOpen(true)}>{t.plants.detail.addFollowUpReminder}</Button>;
  }
  return (
    <form className="mt-4 flex flex-col gap-2.5 border-t border-ink/[0.07] pt-4" onSubmit={(e) => {
      e.preventDefault();
      if (!due) return;
      void onSubmit({ kind, due_on: due, note: note.trim() || null }).then((ok) => {
        if (ok) {
          setDue("");
          setNote("");
          setOpen(false);
        }
      });
    }}>
      <Select name="reminder-kind" label={r.kind} value={kind} onChange={(e) => setKind(e.target.value as Reminder["kind"])}>
        <option value="next_scan">{r.next_scan}</option>
        <option value="treatment_follow_up">{r.treatment_follow_up}</option>
      </Select>
      <Input name="reminder-date" label={r.date} type="date" value={due} onChange={(e) => setDue(e.target.value)} required />
      <Input name="reminder-note" label={r.note} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>{t.common.cancel}</Button>
        <Button type="submit" size="sm" isLoading={busy}>{t.common.save}</Button>
      </div>
    </form>
  );
}
