import { useState } from "react";
import { useParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { scansApi } from "@/lib/endpoints/scans";
import { reportsApi } from "@/lib/endpoints/dashboard";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { ProgressRing } from "@/components/ui/ProgressRing";
import { SeverityBadge, AffectedAreaBar, WeatherCard, RecommendationList, TreatmentSection, AiAnalysisSection } from "@/components/diagnosis/DiagnosisPanels";
import { formatDate } from "@/utils/format";
import { ApiError } from "@/types/api";

const SEVERITY_RING_COLOR: Record<string, string> = {
  mild: "#D8A73D",
  moderate: "#C8722A",
  severe: "#A13D2C",
};

export default function DiagnosisResultPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useLocale();
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const diagnosis = useAsync(() => scansApi.getDiagnosis(id!), [id]);

  if (diagnosis.status === "loading") return <PageLoader label={t.common.loading} />;
  if (diagnosis.status === "error") {
    const msg = diagnosis.error instanceof ApiError && diagnosis.error.status === 403
      ? "You don't have access to this diagnosis."
      : errorMessage(diagnosis.error);
    return <ErrorState message={msg} onRetry={diagnosis.refetch} />;
  }

  const d = diagnosis.data;
  const isHealthy = !d.disease;

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

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5 animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold text-ink">
            {isHealthy ? t.result.healthyResult : d.disease?.name}
          </h1>
          <p className="mt-1 text-sm text-muted">
            {d.plant?.name}
            {d.plant?.scientific_name && <span className="italic"> · {d.plant.scientific_name}</span>}
          </p>
          {d.diagnosed_at && (
            <p className="mt-0.5 text-xs text-muted">
              {t.result.diagnosedOn} {formatDate(d.diagnosed_at, locale)}
            </p>
          )}
        </div>
        <SeverityBadge level={d.severity_level} />
      </div>

      {d.low_confidence_flag && <Alert tone="warning">{t.result.lowConfidence}</Alert>}
      {d.heatmap_image_url && (
        <img src={d.heatmap_image_url} alt="Highlighted diagnosis region" className="w-full rounded-card border border-line" />
      )}

      {/* Confidence + severity gauges */}
      <Card>
        <div className="flex flex-wrap items-center justify-around gap-6">
          <ProgressRing value={d.confidence_score} label={t.result.confidence} color="#2F6B4F" />
          {d.severity_level && d.affected_area_pct != null && (
            <ProgressRing
              value={d.affected_area_pct}
              label={t.result.severity}
              valueLabel={d.severity_level.charAt(0).toUpperCase() + d.severity_level.slice(1)}
              color={SEVERITY_RING_COLOR[d.severity_level]}
            />
          )}
        </div>
        {d.affected_area_pct != null && d.healthy_area_pct != null && (
          <div className="mt-6">
            <AffectedAreaBar affectedPct={d.affected_area_pct} healthyPct={d.healthy_area_pct} severity={d.severity_level} />
          </div>
        )}
      </Card>

      {!isHealthy && d.disease && (
        <Card>
          <CardHeader>
            <CardTitle>{t.result.title}</CardTitle>
          </CardHeader>
          <p className="text-sm text-ink">{d.disease.description}</p>

          {d.disease.symptoms.length > 0 && (
            <div className="mt-4">
              <p className="mb-1.5 text-sm font-semibold text-primary-dark">{t.result.symptoms}</p>
              <ul className="list-disc ps-5 text-sm text-ink">
                {d.disease.symptoms.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          )}
          {d.disease.causes.length > 0 && (
            <div className="mt-4">
              <p className="mb-1.5 text-sm font-semibold text-primary-dark">{t.result.causes}</p>
              <ul className="list-disc ps-5 text-sm text-ink">
                {d.disease.causes.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          {d.disease.transmission_method && (
            <p className="mt-4 text-sm text-ink">
              <span className="font-semibold text-primary-dark">{t.result.transmission}: </span>
              {d.disease.transmission_method}
            </p>
          )}
        </Card>
      )}

      {d.ai_analysis && d.ai_analysis.status !== "disabled" && (
        <Card>
          <CardHeader>
            <CardTitle>{t.result.aiAnalysis}</CardTitle>
          </CardHeader>
          <AiAnalysisSection aiAnalysis={d.ai_analysis} />
        </Card>
      )}

      {d.pests_detected.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t.result.pestsDetected}</CardTitle>
          </CardHeader>
          <ul className="flex flex-col gap-2">
            {d.pests_detected.map((p) => (
              <li key={p.name} className="flex items-center justify-between rounded-card bg-canvas px-3.5 py-2.5 text-sm">
                <span className="font-medium text-ink">{p.name}</span>
                <span className="font-data text-muted">{p.confidence.toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {d.treatment && (
        <Card>
          <CardHeader>
            <CardTitle>{t.result.treatment}</CardTitle>
          </CardHeader>
          <TreatmentSection treatment={d.treatment} />
        </Card>
      )}

      {d.prevention_advice.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t.result.prevention}</CardTitle>
          </CardHeader>
          <ul className="list-disc ps-5 text-sm text-ink">
            {d.prevention_advice.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </Card>
      )}

      {(d.recovery_probability != null || d.estimated_recovery_time) && (
        <Card>
          <CardHeader>
            <CardTitle>{t.result.recovery}</CardTitle>
          </CardHeader>
          <div className="flex gap-8">
            {d.recovery_probability != null && (
              <div>
                <p className="text-xs text-muted">{t.result.recoveryProbability}</p>
                <p className="font-data text-xl font-semibold text-primary">{d.recovery_probability}%</p>
              </div>
            )}
            {d.estimated_recovery_time && (
              <div>
                <p className="text-xs text-muted">{t.result.recoveryTime}</p>
                <p className="font-display text-xl font-semibold text-ink">{d.estimated_recovery_time}</p>
              </div>
            )}
          </div>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t.result.weather}</CardTitle>
        </CardHeader>
        <WeatherCard weather={d.weather} />
      </Card>

      {d.recommendation && (
        <Card>
          <CardHeader>
            <CardTitle>{t.result.recommendation}</CardTitle>
          </CardHeader>
          <RecommendationList recommendation={d.recommendation} />
        </Card>
      )}

      <div className="sticky bottom-16 lg:bottom-0 lg:static">
        {downloadError && (
          <Alert tone="error">
            {downloadError}
          </Alert>
        )}
        <Button fullWidth size="lg" isLoading={isDownloading} onClick={() => void handleDownload()} className="mt-2">
          {isDownloading ? t.result.downloadingReport : t.result.downloadReport}
        </Button>
      </div>
    </div>
  );
}
