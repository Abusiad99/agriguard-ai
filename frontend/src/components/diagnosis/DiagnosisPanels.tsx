import type { AiAnalysisSchema, AnalysisUrgency, CvConsistency, RecommendationSchema, SeverityLevel, TreatmentSchema, WeatherSchema } from "@/types/api";
import { Badge, severityTone } from "@/components/ui/Badge";
import { Alert } from "@/components/ui/Alert";
import { useLocale } from "@/context/LocaleContext";

const SEVERITY_COLOR: Record<SeverityLevel, string> = {
  mild: "#D8A73D",
  moderate: "#C8722A",
  severe: "#A13D2C",
};

export function SeverityBadge({ level }: { level?: SeverityLevel | null }) {
  if (!level) return null;
  return <Badge tone={severityTone(level)}>{level.charAt(0).toUpperCase() + level.slice(1)}</Badge>;
}

/** Affected vs. healthy area, shown as a segmented horizontal bar — the visual
 * required for FR-RESULT-1's "Affected Area % / Healthy Area %" fields. */
export function AffectedAreaBar({
  affectedPct,
  healthyPct,
  severity,
}: {
  affectedPct?: number | null;
  healthyPct?: number | null;
  severity?: SeverityLevel | null;
}) {
  const { t } = useLocale();
  if (affectedPct == null || healthyPct == null) return null;
  const color = severity ? SEVERITY_COLOR[severity] : "#C8722A";

  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-line/50">
        <div style={{ width: `${affectedPct}%`, backgroundColor: color }} className="transition-all duration-500" />
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted">
        <span>
          {t.result.affectedArea}: <strong className="font-data text-ink">{affectedPct.toFixed(1)}%</strong>
        </span>
        <span>
          {t.result.healthyArea}: <strong className="font-data text-ink">{healthyPct.toFixed(1)}%</strong>
        </span>
      </div>
    </div>
  );
}

export function WeatherCard({ weather }: { weather?: WeatherSchema | null }) {
  const { t } = useLocale();
  if (!weather || weather.temperature_c == null) {
    return <p className="text-sm text-muted">{t.result.weatherUnavailable}</p>;
  }
  const items = [
    { label: t.result.temperature, value: weather.temperature_c != null ? `${weather.temperature_c}°C` : "—" },
    { label: t.result.humidity, value: weather.humidity_pct != null ? `${weather.humidity_pct}%` : "—" },
    { label: t.result.wind, value: weather.wind_speed_kmh != null ? `${weather.wind_speed_kmh} km/h` : "—" },
    { label: t.result.rain, value: weather.rain_probability_pct != null ? `${weather.rain_probability_pct}%` : "—" },
    { label: t.result.uvIndex, value: weather.uv_index != null ? weather.uv_index : "—" },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {items.map((item) => (
        <div key={item.label} className="rounded-card bg-canvas px-3 py-2.5 text-center">
          <dt className="text-xs text-muted">{item.label}</dt>
          <dd className="font-data mt-0.5 text-sm font-semibold text-ink">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function RecommendationList({ recommendation }: { recommendation?: RecommendationSchema | null }) {
  const { t } = useLocale();
  if (!recommendation) return null;
  const items = [
    { label: t.result.irrigation, value: recommendation.irrigation_advice },
    { label: t.result.spraying, value: recommendation.spraying_advice },
    { label: t.result.fertilizer, value: recommendation.fertilizer_advice },
  ].filter((i) => i.value);

  if (items.length === 0) return null;

  return (
    <ul className="flex flex-col gap-2.5">
      {items.map((item) => (
        <li key={item.label} className="flex gap-3 rounded-card bg-canvas px-3.5 py-3 text-sm">
          <span className="shrink-0 font-semibold text-primary-dark">{item.label}:</span>
          <span className="text-ink">{item.value}</span>
        </li>
      ))}
    </ul>
  );
}

export function TreatmentSection({ treatment }: { treatment?: TreatmentSchema | null }) {
  const { t } = useLocale();
  if (!treatment) return null;

  const groups = [
    { key: "organic", label: t.result.organic, data: treatment.organic },
    { key: "chemical", label: t.result.chemical, data: treatment.chemical },
    { key: "biological", label: t.result.biological, data: treatment.biological },
  ].filter((g) => g.data);

  if (groups.length === 0) return null;

  return (
    <div className="flex flex-col gap-4">
      {groups.map((group) => (
        <div key={group.key} className="rounded-card border border-line px-4 py-3.5">
          <p className="mb-1.5 font-semibold text-primary-dark">{group.label}</p>
          <p className="text-sm text-ink">{group.data?.instructions}</p>
          {group.data?.safety_notes && (
            <p className="mt-2 text-xs text-muted">
              <span className="font-semibold">{t.result.safetyNotes}: </span>
              {group.data.safety_notes}
            </p>
          )}
          {group.data?.source_citation && (
            <p className="mt-1 text-xs text-muted italic">{group.data.source_citation}</p>
          )}
        </div>
      ))}
    </div>
  );
}

const CONSISTENCY_TONE: Record<CvConsistency, "primary" | "mild" | "moderate" | "severe"> = {
  consistent: "primary",
  partially_consistent: "mild",
  inconsistent: "severe",
  uncertain: "moderate",
};

const URGENCY_TONE: Record<AnalysisUrgency, "primary" | "moderate" | "severe"> = {
  low: "primary",
  medium: "moderate",
  high: "severe",
};

/** "AI Agricultural Analysis" — the Gemini multimodal reasoning layer's
 * explanation on top of the existing CV diagnosis (never a replacement for it).
 * Renders one of three states:
 *   - no `aiAnalysis` prop at all / status "disabled": section is omitted entirely
 *     (Gemini wasn't configured for this deployment — not an error, nothing to show)
 *   - status "unavailable": a single Alert explaining the analysis couldn't be
 *     produced this time, CV diagnosis above is unaffected
 *   - status "ok": the full structured explanation
 */
export function AiAnalysisSection({ aiAnalysis }: { aiAnalysis?: AiAnalysisSchema | null }) {
  const { t } = useLocale();
  if (!aiAnalysis || aiAnalysis.status === "disabled") return null;

  if (aiAnalysis.status === "unavailable" || !aiAnalysis.analysis) {
    return <Alert tone="warning">{aiAnalysis.message || t.result.aiAnalysisUnavailable}</Alert>;
  }

  const a = aiAnalysis.analysis;
  const consistencyLabel: Record<CvConsistency, string> = {
    consistent: t.result.aiConsistencyConsistent,
    partially_consistent: t.result.aiConsistencyPartiallyConsistent,
    inconsistent: t.result.aiConsistencyInconsistent,
    uncertain: t.result.aiConsistencyUncertain,
  };
  const urgencyLabel: Record<AnalysisUrgency, string> = {
    low: t.result.aiUrgencyLow,
    medium: t.result.aiUrgencyMedium,
    high: t.result.aiUrgencyHigh,
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={CONSISTENCY_TONE[a.cv_consistency]}>
          {t.result.aiConsistency}: {consistencyLabel[a.cv_consistency]}
        </Badge>
        <Badge tone={URGENCY_TONE[a.urgency]}>
          {t.result.aiUrgency}: {urgencyLabel[a.urgency]}
        </Badge>
      </div>

      <p className="text-sm text-ink">{a.diagnosis_explanation}</p>

      {a.observed_symptoms.length > 0 && (
        <div>
          <p className="mb-1.5 text-sm font-semibold text-primary-dark">{t.result.aiObservedSymptoms}</p>
          <ul className="list-disc ps-5 text-sm text-ink">
            {a.observed_symptoms.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="mb-1 text-sm font-semibold text-primary-dark">{t.result.aiConfidenceAssessment}</p>
        <p className="text-sm text-ink">{a.confidence_assessment}</p>
      </div>

      <div>
        <p className="mb-1 text-sm font-semibold text-primary-dark">{t.result.aiSeverityExplanation}</p>
        <p className="text-sm text-ink">{a.severity_explanation}</p>
      </div>

      {a.treatment_guidance.length > 0 && (
        <div>
          <p className="mb-1.5 text-sm font-semibold text-primary-dark">{t.result.aiTreatmentGuidance}</p>
          <ul className="list-disc ps-5 text-sm text-ink">
            {a.treatment_guidance.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </div>
      )}

      {a.prevention_guidance.length > 0 && (
        <div>
          <p className="mb-1.5 text-sm font-semibold text-primary-dark">{t.result.aiPreventionGuidance}</p>
          <ul className="list-disc ps-5 text-sm text-ink">
            {a.prevention_guidance.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="mb-1 text-sm font-semibold text-primary-dark">{t.result.aiEnvironmentalRisk}</p>
        <p className="text-sm text-ink">{a.environmental_risk}</p>
      </div>
    </div>
  );
}
