import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { scansApi } from "@/lib/endpoints/scans";
import { reportsApi } from "@/lib/endpoints/dashboard";
import { plantsApi } from "@/lib/endpoints/plants";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Icon } from "@/components/ui/Icon";
import { ProgressRing } from "@/components/ui/ProgressRing";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Input";
import {
  WeatherCard,
  RecommendationList,
  TreatmentSection,
  AiAnalysisSection,
  BulletList,
  SubHeading,
  SeverityBadge,
} from "@/components/diagnosis/DiagnosisPanels";
import {
  AlsoConsiderPanel,
  CandidatesPanel,
  DecisionBanner,
  ExpertReviewNotice,
  FollowUpForm,
  ImagePanels,
  LimitationsList,
  MeasurementPanel,
  ProvenanceLine,
  QualityNotes,
  StatusBadge,
} from "@/components/diagnosis/ReliabilityPanels";
import { formatDate } from "@/utils/format";
import { labelDisplay, plantName } from "@/utils/labels";
import { ApiError, type DiagnosisResponse, type ObservationNote } from "@/types/api";

export default function DiagnosisResultPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useLocale();
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [override, setOverride] = useState<DiagnosisResponse | null>(null);

  const diagnosis = useAsync(() => scansApi.getDiagnosis(id!), [id]);
  const modelInfo = useAsync(() => scansApi.modelInfo(), []);

  if (diagnosis.status === "loading") return <PageLoader label={t.common.loading} />;
  if (diagnosis.status === "error") {
    const msg =
      diagnosis.error instanceof ApiError && diagnosis.error.status === 403 ? t.result.noAccess : errorMessage(diagnosis.error);
    return <ErrorState message={msg} onRetry={diagnosis.refetch} />;
  }

  const d = override ?? diagnosis.data;
  const status = d.decision_status ?? "legacy";
  const confident = status === "confident";
  const questions = modelInfo.status === "success" ? modelInfo.data.follow_up_questions : [];

  const title =
    status === "inconclusive"
      ? t.status.noConditionNamed
      : d.disease?.name ?? (d.predicted_label ? labelDisplay(d.predicted_label, t) : d.plant ? plantName(d.plant.name, t) : "—");

  const handleDownload = async () => {
    setDownloadError(null);
    setIsDownloading(true);
    try {
      const blob = await reportsApi.downloadReport(d.diagnosis_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `agriguard-report-${d.diagnosis_id}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : t.common.unknownError);
    } finally {
      setIsDownloading(false);
    }
  };

  const submitFollowUp = async (answers: Record<string, string | string[]>) => {
    const differential = await scansApi.submitFollowUp(d.diagnosis_id, answers);
    setOverride({ ...d, differential });
  };

  return (
    <div className="flex flex-col gap-5 stagger">
      <Link
        to={d.plant_profile ? `/plants/${d.plant_profile.id}` : "/history"}
        className="group inline-flex w-fit items-center gap-2 rounded-xl py-1 text-sm font-medium text-muted transition-colors hover:text-primary"
      >
        <span className="flip-rtl inline-flex">
          <Icon name="arrowLeft" className="h-4 w-4 transition-transform duration-300 ease-spring group-hover:-translate-x-1" />
        </span>
        {d.plant_profile ? d.plant_profile.name : t.result.backToHistory}
      </Link>

      {/* ---------- Result hero ---------- */}
      <Card highlight className="relative overflow-hidden !p-6 sm:!p-8">
        <div className="relative grid items-center gap-8 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <div className="mb-4 flex flex-wrap items-center gap-2.5">
              <StatusBadge status={status} className="px-3 py-1.5 text-sm" />
              {confident && d.severity_level && <SeverityBadge level={d.severity_level} />}
            </div>
            {status === "uncertain" && <p className="mb-1 text-sm font-medium text-muted">{t.status.leadingCandidate}</p>}
            <h1 dir="auto" className="text-balance text-start font-display text-[1.9rem] font-semibold leading-tight text-ink sm:text-[2.35rem]">
              {title}
            </h1>
            {d.plant && (
              <p className="mt-2 flex flex-wrap items-center gap-x-2 text-[0.98rem] text-muted">
                <Icon name="leaf" className="h-4 w-4 text-primary" />
                <span className="font-medium text-ink">{plantName(d.plant.name, t)}</span>
                {d.plant.scientific_name && <span className="italic">({d.plant.scientific_name})</span>}
              </p>
            )}
            {d.diagnosed_at && (
              <p className="mt-1.5 flex items-center gap-2 text-sm text-muted">
                <Icon name="calendar" className="h-4 w-4" />
                {t.result.diagnosedOn} {formatDate(d.diagnosed_at, locale)}
              </p>
            )}
          </div>
          {status !== "inconclusive" && (
            <div className="flex justify-center">
              <ProgressRing value={d.confidence_score} label={t.result.confidence} size={136} />
            </div>
          )}
        </div>
      </Card>

      <DecisionBanner d={d} />
      <QualityNotes quality={d.image_quality} />
      <ExpertReviewNotice differential={d.differential} />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex flex-col gap-5">
          {d.differential && d.differential.model_candidates.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle icon="target">{t.reliability.candidatesTitle}</CardTitle>
              </CardHeader>
              <CandidatesPanel differential={d.differential} />
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle icon="eye">{t.reliability.imagesTitle}</CardTitle>
            </CardHeader>
            <ImagePanels d={d} />
          </Card>

          {confident && d.disease && (
            <Card>
              <CardHeader>
                <CardTitle icon="bug">{t.result.title}</CardTitle>
              </CardHeader>
              <p dir="auto" className="text-start text-[0.98rem] leading-relaxed text-ink">{d.disease.description}</p>
              <div className="mt-6 grid gap-6 sm:grid-cols-2">
                {d.disease.symptoms.length > 0 && (
                  <div>
                    <SubHeading icon="search">{t.result.symptoms}</SubHeading>
                    <BulletList items={d.disease.symptoms} />
                  </div>
                )}
                {d.disease.causes.length > 0 && (
                  <div>
                    <SubHeading icon="microbe">{t.result.causes}</SubHeading>
                    <BulletList items={d.disease.causes} />
                  </div>
                )}
              </div>
            </Card>
          )}

          {d.differential && (d.differential.also_consider.length > 0 || d.differential.follow_up_questions.length > 0) && (
            <Card>
              <CardHeader>
                <CardTitle icon="question">{t.reliability.followUpTitle}</CardTitle>
              </CardHeader>
              <div className="flex flex-col gap-6">
                <div>
                  <SubHeading icon="info">{t.reliability.alsoConsiderTitle}</SubHeading>
                  <AlsoConsiderPanel differential={d.differential} />
                </div>
                {questions.length > 0 && !d.is_legacy && (
                  <FollowUpForm differential={d.differential} questions={questions} onSubmit={submitFollowUp} />
                )}
              </div>
            </Card>
          )}

          {d.ai_analysis && d.ai_analysis.status !== "disabled" && (
            <Card highlight>
              <CardHeader>
                <CardTitle icon="sparkles">{t.result.aiAnalysis}</CardTitle>
              </CardHeader>
              <AiAnalysisSection aiAnalysis={d.ai_analysis} />
            </Card>
          )}

          {confident && d.treatment && (
            <Card>
              <CardHeader>
                <CardTitle icon="beaker">{t.result.treatment}</CardTitle>
              </CardHeader>
              <TreatmentSection treatment={d.treatment} />
            </Card>
          )}

          {confident && d.prevention_advice.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle icon="shieldCheck">{t.result.prevention}</CardTitle>
              </CardHeader>
              <BulletList items={d.prevention_advice} icon="check" />
            </Card>
          )}

          <NotesCard diagnosisId={d.diagnosis_id} />

          <Card>
            <CardHeader>
              <CardTitle icon="info">{t.reliability.limitationsTitle}</CardTitle>
            </CardHeader>
            <LimitationsList codes={d.limitations ?? []} />
            <div className="mt-4">
              <ProvenanceLine d={d} />
            </div>
          </Card>
        </div>

        <aside className="flex flex-col gap-5">
          <div className="hidden flex-col gap-3 lg:flex">
            {downloadError && <Alert tone="error">{downloadError}</Alert>}
            <Button fullWidth size="lg" icon="download" isLoading={isDownloading} onClick={() => void handleDownload()}>
              {isDownloading ? t.result.downloadingReport : t.result.downloadReport}
            </Button>
            <ButtonLink to={`/assistant?diagnosis=${d.diagnosis_id}`} variant="glass" icon="chat" fullWidth>
              {t.reliability.askAssistant}
            </ButtonLink>
          </div>

          <Card>
            <CardHeader>
              <CardTitle icon="chart">{t.reliability.measurementTitle}</CardTitle>
            </CardHeader>
            <MeasurementPanel d={d} />
          </Card>

          <PlantLinkCard d={d} onChange={setOverride} />

          {d.recommendation && (d.recommendation.irrigation_advice || d.recommendation.spraying_advice || d.recommendation.fertilizer_advice) && (
            <Card>
              <CardHeader>
                <CardTitle icon="lightning">{t.result.recommendation}</CardTitle>
              </CardHeader>
              <RecommendationList recommendation={d.recommendation} />
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle icon="sun">{t.result.weather}</CardTitle>
            </CardHeader>
            <WeatherCard weather={d.weather} />
          </Card>
        </aside>
      </div>

      {/* Mobile: actions stay within thumb reach above the tab bar. */}
      <div className="sticky bottom-24 z-20 flex flex-col gap-2 lg:hidden">
        {downloadError && <Alert tone="error">{downloadError}</Alert>}
        <div className="flex gap-2">
          <Button fullWidth size="lg" icon="download" isLoading={isDownloading} onClick={() => void handleDownload()}>
            {isDownloading ? t.result.downloadingReport : t.result.downloadReport}
          </Button>
          <ButtonLink to={`/assistant?diagnosis=${d.diagnosis_id}`} variant="glass" size="lg" icon="chat" aria-label={t.reliability.askAssistant}>
            <span className="sr-only">{t.reliability.askAssistant}</span>
          </ButtonLink>
        </div>
      </div>
    </div>
  );
}

function PlantLinkCard({ d, onChange }: { d: DiagnosisResponse; onChange: (d: DiagnosisResponse) => void }) {
  const { t } = useLocale();
  const plants = useAsync(() => plantsApi.list({ page_size: 100 }), []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assign = async (plantId: string | null) => {
    setSaving(true);
    setError(null);
    try {
      onChange(await scansApi.assignPlant(d.diagnosis_id, plantId));
    } catch (e) {
      setError(e instanceof Error ? e.message : t.common.unknownError);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle icon="leaf">{t.reliability.linkedPlant}</CardTitle>
      </CardHeader>
      {d.plant_profile ? (
        <div className="flex items-center justify-between gap-3">
          <Link to={`/plants/${d.plant_profile.id}`} className="font-medium text-primary hover:underline">
            {d.plant_profile.name}
          </Link>
          <Button variant="ghost" size="sm" isLoading={saving} onClick={() => void assign(null)}>
            {t.reliability.unlink}
          </Button>
        </div>
      ) : (
        <Select
          compact
          aria-label={t.reliability.linkToPlant}
          value=""
          disabled={saving || plants.status !== "success"}
          onChange={(e) => e.target.value && void assign(e.target.value)}
        >
          <option value="">{t.reliability.linkToPlant}</option>
          {plants.status === "success" &&
            plants.data.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
        </Select>
      )}
      {error && <div className="mt-3"><Alert tone="error">{error}</Alert></div>}
    </Card>
  );
}

function NotesCard({ diagnosisId }: { diagnosisId: string }) {
  const { t, locale } = useLocale();
  const notes = useAsync(() => scansApi.listNotes(diagnosisId), [diagnosisId]);
  const [body, setBody] = useState("");
  const [type, setType] = useState<"user_note" | "treatment_applied" | "correction">("user_note");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<ObservationNote[]>([]);

  const submit = async () => {
    if (!body.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const note = await scansApi.addNote(diagnosisId, type, body.trim());
      setAdded((prev) => [...prev, note]);
      setBody("");
    } catch (e) {
      setError(e instanceof Error ? e.message : t.common.unknownError);
    } finally {
      setSaving(false);
    }
  };

  const items = [...(notes.status === "success" ? notes.data : []), ...added];

  return (
    <Card>
      <CardHeader>
        <CardTitle icon="document">{t.reliability.notesTitle}</CardTitle>
      </CardHeader>
      {items.length === 0 ? (
        <p className="text-sm text-muted">{t.reliability.noNotes}</p>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {items.map((n) => (
            <li key={n.id} className="rounded-2xl bg-ink/[0.035] px-4 py-3 text-sm">
              <p className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
                <span className="font-semibold text-ink">{t.reliability.noteTypes[n.note_type] ?? n.note_type}</span>
                {n.created_at && <span>{formatDate(n.created_at, locale)}</span>}
              </p>
              {n.body && <p dir="auto" className="mt-1 whitespace-pre-wrap text-start text-ink">{n.body}</p>}
              {n.note_type === "follow_up" && n.data && typeof n.data === "object" && "answers" in n.data && (
                <p className="mt-1 text-xs text-muted">
                  {Object.entries((n.data as { answers: Record<string, string | string[]> }).answers)
                    .map(([q, a]) => `${t.reliability.questions[q] ?? q} ${(Array.isArray(a) ? a : [a]).map((x) => t.reliability.options[x] ?? x).join(", ")}`)
                    .join(" · ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4 flex flex-col gap-3">
        <Select compact aria-label={t.reliability.addNote} value={type} onChange={(e) => setType(e.target.value as typeof type)}>
          <option value="user_note">{t.reliability.noteTypes.user_note}</option>
          <option value="treatment_applied">{t.reliability.noteTypes.treatment_applied}</option>
          <option value="correction">{t.reliability.noteTypes.correction}</option>
        </Select>
        <Textarea
          rows={3}
          maxLength={4000}
          aria-label={t.reliability.addNote}
          placeholder={t.reliability.notePlaceholder}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        {error && <Alert tone="error">{error}</Alert>}
        <Button size="sm" icon="plus" className="w-fit" isLoading={saving} disabled={!body.trim()} onClick={() => void submit()}>
          {t.reliability.addNote}
        </Button>
      </div>
    </Card>
  );
}
