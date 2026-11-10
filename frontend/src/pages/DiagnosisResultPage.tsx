import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync } from "@/hooks/useAsync";
import { scansApi } from "@/lib/endpoints/scans";
import { reportsApi } from "@/lib/endpoints/dashboard";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Icon } from "@/components/ui/Icon";
import { ProgressRing } from "@/components/ui/ProgressRing";
import {
  SeverityBadge,
  AffectedAreaBar,
  WeatherCard,
  TreatmentSection,
  DiseaseDescription,
  AiAnalysisSection,
  BulletList,
  SubHeading,
} from "@/components/diagnosis/DiagnosisPanels";
import { SEVERITY_COLOR, useSeverityLabel } from "@/components/diagnosis/severity";
import { SegmentationPanel } from "@/components/diagnosis/SegmentationPanel";
import { TrackPlantCard } from "@/components/diagnosis/TrackPlantCard";
import { GenerateReportButton } from "@/components/reports/GenerateReportButton";
import { WeatherGuidancePanel } from "@/components/diagnosis/WeatherGuidancePanel";
import { formatDate } from "@/utils/format";
import { diagnosisLoadError, preventionAdvice, reportDownloadError } from "@/lib/diagnosisText";

export default function DiagnosisResultPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useLocale();
  const severityLabel = useSeverityLabel();
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const diagnosis = useAsync(() => scansApi.getDiagnosis(id!), [id]);

  if (diagnosis.status === "loading") return <PageLoader label={t.common.loading} />;
  if (diagnosis.status === "error") {
    return <ErrorState message={diagnosisLoadError(diagnosis.error, t, locale)} onRetry={diagnosis.refetch} />;
  }

  const d = diagnosis.data;
  const isHealthy = !d.disease;
  const heroTone = isHealthy ? "primary" : d.severity_level ?? "moderate";

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
      setDownloadError(reportDownloadError(err, t, locale));
    } finally {
      setIsDownloading(false);
    }
  };

  const downloadButton = (
    <Button fullWidth size="lg" icon="download" isLoading={isDownloading} onClick={() => void handleDownload()}>
      {isDownloading ? t.result.downloadingReport : t.result.downloadReport}
    </Button>
  );

  return (
    <div className="flex flex-col gap-5 stagger">
      <Link
        to="/history"
        className="group inline-flex w-fit items-center gap-2 rounded-xl py-1 text-sm font-medium text-muted transition-colors hover:text-primary"
      >
        <span className="flip-rtl inline-flex">
          <Icon name="arrowLeft" className="h-4 w-4 transition-transform duration-300 ease-spring group-hover:-translate-x-1" />
        </span>
        {t.result.backToHistory}
      </Link>

      {/* ---------- Result hero ---------- */}
      <Card highlight className="relative overflow-hidden !p-6 sm:!p-8">
        <div
          className="pointer-events-none absolute -end-24 -top-24 h-72 w-72 rounded-full opacity-25 blur-3xl"
          style={{ background: heroTone === "primary" ? "rgb(var(--c-primary))" : SEVERITY_COLOR[heroTone] }}
          aria-hidden="true"
        />
        <div className="relative grid items-center gap-8 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <div className="mb-4 flex flex-wrap items-center gap-2.5">
              {isHealthy ? (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-primary-light px-3 py-1.5 text-sm font-semibold text-primary-dark ring-1 ring-inset ring-primary/20">
                  <Icon name="check" className="h-4 w-4" />
                  {t.dashboard.healthy}
                </span>
              ) : (
                <SeverityBadge level={d.severity_level} />
              )}
              {d.disease?.type && (
                <span className="rounded-full bg-ink/[0.05] px-3 py-1.5 text-sm font-medium capitalize text-muted ring-1 ring-inset ring-ink/10">
                  {d.disease.type}
                </span>
              )}
            </div>
            <h1 className="text-balance font-display text-[2rem] font-semibold leading-tight text-ink sm:text-[2.5rem]">
              {isHealthy ? t.result.healthyResult : d.disease?.name}
            </h1>
            <p className="mt-2 flex flex-wrap items-center gap-x-2 text-[0.98rem] text-muted">
              <Icon name="leaf" className="h-4 w-4 text-primary" />
              <span className="font-medium text-ink">{d.plant?.name}</span>
              {d.plant?.scientific_name && <span className="italic">({d.plant.scientific_name})</span>}
            </p>
            {d.diagnosed_at && (
              <p className="mt-1.5 flex items-center gap-2 text-sm text-muted">
                <Icon name="calendar" className="h-4 w-4" />
                {t.result.diagnosedOn} {formatDate(d.diagnosed_at, locale)}
              </p>
            )}
            {d.affected_area_pct != null && d.healthy_area_pct != null && (
              <div className="mt-7 max-w-xl">
                <AffectedAreaBar affectedPct={d.affected_area_pct} healthyPct={d.healthy_area_pct} severity={d.severity_level} />
                {d.severity_method === "explainability_heatmap" && (
                  <p className="mt-2 text-xs text-muted">{t.gradcam.estimateNote}</p>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-center gap-8 sm:gap-10">
            <ProgressRing value={d.confidence_score} label={t.result.confidence} size={136} />
            {d.severity_level && d.affected_area_pct != null && (
              <ProgressRing
                value={d.affected_area_pct}
                label={t.result.severity}
                size={136}
                valueLabel={severityLabel(d.severity_level)}
                sublabel={`${d.affected_area_pct.toFixed(0)}%`}
                color={SEVERITY_COLOR[d.severity_level]}
              />
            )}
          </div>
        </div>
      </Card>

      {d.low_confidence_flag && <Alert tone="warning">{t.result.lowConfidence}</Alert>}

      {d.image_quality && !d.image_quality.acceptable && (
        <Alert tone="warning" title={t.quality.title}>
          {d.image_quality.issues.map((issue) => t.quality.issues[issue]).join(", ")}. {t.quality.caveat}
        </Alert>
      )}

      {d.heatmap_image_url && (
        <figure className="glass overflow-hidden rounded-panel p-2">
          <img src={d.heatmap_image_url} alt={t.gradcam.heatmapCaption} className="w-full rounded-[1.1rem]" />
          <figcaption className="px-2 pb-1 pt-2.5 text-xs leading-relaxed text-muted">{t.gradcam.heatmapCaption}</figcaption>
        </figure>
      )}

      <SegmentationPanel segmentation={d.segmentation} originalUrl={d.roi_image_url} />

      {/* ---------- Details ---------- */}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex flex-col gap-5">
          {!isHealthy && d.disease && (
            <Card>
              <CardHeader>
                <CardTitle icon="bug">{t.result.title}</CardTitle>
              </CardHeader>
              <DiseaseDescription disease={d.disease} />

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
              {d.disease.transmission_method && (
                <div className="mt-6 flex items-start gap-3 rounded-2xl bg-ink/[0.035] p-4">
                  <Icon name="spread" className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                  <p className="text-sm leading-relaxed text-ink">
                    <span className="font-semibold text-primary-dark">{t.result.transmission}: </span>
                    <span dir="auto">{d.disease.transmission_method}</span>
                  </p>
                </div>
              )}
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

          {d.treatment && (
            <Card>
              <CardHeader>
                <CardTitle icon="beaker">{t.result.treatment}</CardTitle>
              </CardHeader>
              <TreatmentSection treatment={d.treatment} />
            </Card>
          )}

          {d.prevention_advice.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle icon="shieldCheck">{t.result.prevention}</CardTitle>
              </CardHeader>
              <BulletList items={preventionAdvice(d, t)} icon="check" />
            </Card>
          )}
        </div>

        <aside className="flex flex-col gap-5">
          <div className="hidden lg:block">
            {downloadError && (
              <div className="mb-3">
                <Alert tone="error">{downloadError}</Alert>
              </div>
            )}
            {downloadButton}
          </div>

          {d.viewer_is_owner !== false && (
            <GenerateReportButton request={{ type: "diagnosis", subject_id: d.diagnosis_id }} fullWidth />
          )}

          {d.viewer_is_owner !== false && <TrackPlantCard diagnosis={d} onTracked={diagnosis.refetch} />}


          {(d.recovery_probability != null || d.estimated_recovery_time) && (
            <Card>
              <CardHeader>
                <CardTitle icon="heart">{t.result.recovery}</CardTitle>
              </CardHeader>
              <div className="flex items-center gap-5">
                {d.recovery_probability != null && <ProgressRing value={d.recovery_probability} size={92} strokeWidth={8} />}
                <div className="flex flex-col gap-3">
                  {d.recovery_probability != null && <p className="text-sm text-muted">{t.result.recoveryProbability}</p>}
                  {d.estimated_recovery_time && (
                    <div>
                      <p className="text-xs text-muted">{t.result.recoveryTime}</p>
                      <p className="font-display text-xl font-semibold text-ink">{d.estimated_recovery_time}</p>
                    </div>
                  )}
                </div>
              </div>
            </Card>
          )}

          {/* Weather and spraying conditions: assessed on the server from measured values
              and verified sources (weather_guidance), shown in the reader's language. */}
          <Card>
            <CardHeader>
              <CardTitle icon="sun">{d.weather_guidance ? t.result.weatherGuidance.title : t.result.weather}</CardTitle>
            </CardHeader>
            {d.weather_guidance ? <WeatherGuidancePanel guidance={d.weather_guidance} /> : <WeatherCard weather={d.weather} />}
          </Card>

          {d.pests_detected.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle icon="bug">{t.result.pestsDetected}</CardTitle>
              </CardHeader>
              <ul className="flex flex-col gap-2.5">
                {d.pests_detected.map((p) => (
                  <li key={p.name} className="rounded-2xl bg-ink/[0.035] px-4 py-3">
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="font-medium text-ink">{p.name}</span>
                      <span className="font-data font-semibold tabular-nums text-muted">{p.confidence.toFixed(1)}%</span>
                    </div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink/[0.07]">
                      <div className="h-full origin-start animate-grow-x rounded-full bg-severity-moderate" style={{ width: `${p.confidence}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </aside>
      </div>

      {/* Mobile: report download stays within thumb reach above the tab bar. */}
      <div className="sticky bottom-24 z-20 lg:hidden">
        {downloadError && (
          <div className="mb-2">
            <Alert tone="error">{downloadError}</Alert>
          </div>
        )}
        {downloadButton}
      </div>
    </div>
  );
}
