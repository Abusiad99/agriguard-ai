import { useState } from "react";
import type { AiAnalysisSchema, AnalysisUrgency, CvConsistency, RecommendationSchema, SeverityLevel, TreatmentSchema, WeatherSchema } from "@/types/api";
import { Badge, severityTone } from "@/components/ui/Badge";
import { Alert } from "@/components/ui/Alert";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Tabs } from "@/components/ui/Tabs";
import { useLocale } from "@/context/LocaleContext";
import { SEVERITY_COLOR, useSeverityLabel } from "./severity";

export function SeverityBadge({ level }: { level?: SeverityLevel | null }) {
  const label = useSeverityLabel();
  if (!level) return null;
  return (
    <Badge tone={severityTone(level)} pulse={level === "severe"} className="px-3 py-1.5 text-sm">
      {label(level)}
    </Badge>
  );
}

/** Affected vs. healthy area as one segmented bar — the visual required for
 * FR-RESULT-1's "Affected Area % / Healthy Area %" fields. */
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
  const color = severity ? SEVERITY_COLOR[severity] : SEVERITY_COLOR.moderate;

  return (
    <div>
      <div className="flex h-3 w-full gap-1 overflow-hidden rounded-full">
        <div
          style={{ width: `${affectedPct}%`, backgroundColor: color }}
          className="h-full origin-start animate-grow-x rounded-full shadow-[0_0_12px_-2px_currentColor] [animation-delay:500ms]"
        />
        <div style={{ width: `${healthyPct}%` }} className="h-full origin-start animate-grow-x rounded-full bg-primary/70 [animation-delay:700ms]" />
      </div>
      <div className="mt-3 flex flex-wrap justify-between gap-2 text-sm text-muted">
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
          {t.result.affectedArea}
          <strong className="font-data font-semibold tabular-nums text-ink">{affectedPct.toFixed(1)}%</strong>
        </span>
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-primary/70" />
          {t.result.healthyArea}
          <strong className="font-data font-semibold tabular-nums text-ink">{healthyPct.toFixed(1)}%</strong>
        </span>
      </div>
    </div>
  );
}

export function WeatherCard({ weather }: { weather?: WeatherSchema | null }) {
  const { t } = useLocale();
  if (!weather || weather.temperature_c == null) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted">
        <Icon name="info" className="h-4 w-4" />
        {t.result.weatherUnavailable}
      </p>
    );
  }
  const items: { icon: IconName; label: string; value: string | number }[] = [
    { icon: "thermometer", label: t.result.temperature, value: weather.temperature_c != null ? `${weather.temperature_c}°C` : "—" },
    { icon: "droplet", label: t.result.humidity, value: weather.humidity_pct != null ? `${weather.humidity_pct}%` : "—" },
    { icon: "wind", label: t.result.wind, value: weather.wind_speed_kmh != null ? `${weather.wind_speed_kmh} km/h` : "—" },
    { icon: "rain", label: t.result.rain, value: weather.rain_probability_pct != null ? `${weather.rain_probability_pct}%` : "—" },
    { icon: "sun", label: t.result.uvIndex, value: weather.uv_index != null ? weather.uv_index : "—" },
  ];
  return (
    <dl className="grid grid-cols-2 gap-2.5">
      {items.map((item, i) => (
        <div
          key={item.label}
          className={`flex items-center gap-3 rounded-2xl bg-ink/[0.035] px-3.5 py-3 ${i === 0 ? "col-span-2 bg-gradient-to-br from-accent/15 to-transparent" : ""}`}
        >
          <Icon name={item.icon} className={`shrink-0 ${i === 0 ? "h-7 w-7 text-accent-dark dark:text-accent" : "h-5 w-5 text-primary"}`} />
          <div className="min-w-0">
            <dt className="truncate text-xs text-muted">{item.label}</dt>
            <dd className={`font-data font-semibold tabular-nums text-ink ${i === 0 ? "text-2xl" : "text-sm"}`}>{item.value}</dd>
          </div>
        </div>
      ))}
    </dl>
  );
}

export function RecommendationList({ recommendation }: { recommendation?: RecommendationSchema | null }) {
  const { t } = useLocale();
  if (!recommendation) return null;
  const all: { icon: IconName; label: string; value?: string | null }[] = [
    { icon: "droplet", label: t.result.irrigation, value: recommendation.irrigation_advice },
    { icon: "spray", label: t.result.spraying, value: recommendation.spraying_advice },
    { icon: "sprout", label: t.result.fertilizer, value: recommendation.fertilizer_advice },
  ];
  const items = all.filter((i) => i.value);

  if (items.length === 0) return null;

  return (
    <ul className="flex flex-col gap-3">
      {items.map((item) => (
        <li key={item.label} className="flex gap-3.5 rounded-2xl border border-line/80 bg-surface/50 p-4 dark:bg-surface/30">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Icon name={item.icon} className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink">{item.label}</p>
            <p dir="auto" className="mt-0.5 text-start text-sm leading-relaxed text-muted">{item.value}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

const TREATMENT_ICON: Record<string, IconName> = {
  organic: "leaf",
  chemical: "beaker",
  biological: "microbe",
};

export function TreatmentSection({ treatment }: { treatment?: TreatmentSchema | null }) {
  const { t } = useLocale();
  const groups = treatment
    ? [
        { key: "organic", label: t.result.organic, data: treatment.organic },
        { key: "chemical", label: t.result.chemical, data: treatment.chemical },
        { key: "biological", label: t.result.biological, data: treatment.biological },
      ].filter((g) => g.data)
    : [];
  const [active, setActive] = useState(groups[0]?.key ?? "organic");

  if (groups.length === 0) return null;
  const current = groups.find((g) => g.key === active) ?? groups[0];

  return (
    <div className="flex flex-col gap-4">
      {groups.length > 1 && (
        <Tabs
          tabs={groups.map((g) => ({ key: g.key, label: g.label, icon: <Icon name={TREATMENT_ICON[g.key]} className="h-4 w-4" /> }))}
          active={current.key}
          onChange={setActive}
        />
      )}
      <div key={current.key} className="rounded-2xl border border-line/80 bg-surface/50 p-5 animate-fade-in dark:bg-surface/30">
        <p className="flex items-center gap-2 font-semibold text-primary-dark">
          <Icon name={TREATMENT_ICON[current.key]} className="h-5 w-5 text-primary" />
          {current.label}
        </p>
        <p dir="auto" className="mt-2.5 text-start text-[0.95rem] leading-relaxed text-ink">{current.data?.instructions}</p>
        {current.data?.safety_notes && (
          <p className="mt-4 flex items-start gap-2.5 rounded-xl bg-severity-mild-bg/70 px-3.5 py-3 text-sm text-severity-mild">
            <Icon name="warning" className="mt-px h-[18px] w-[18px] shrink-0" />
            <span>
              <span className="font-semibold">{t.result.safetyNotes}: </span>
              <span dir="auto">{current.data.safety_notes}</span>
            </span>
          </p>
        )}
        {current.data?.source_citation && (
          <p className="mt-3 flex items-center gap-2 text-xs text-muted">
            <Icon name="book" className="h-4 w-4 shrink-0" />
            <span dir="auto" className="italic">{current.data.source_citation}</span>
          </p>
        )}
      </div>
    </div>
  );
}

/** A list with a small leaf-green check, used for symptoms, causes and advice. */
export function BulletList({ items, icon = "dot" }: { items: string[]; icon?: "dot" | "check" }) {
  return (
    <ul className="flex flex-col gap-2.5">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-3 text-[0.95rem] leading-relaxed text-ink">
          {icon === "check" ? (
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
              <svg viewBox="0 0 20 20" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth={3} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 10.5l3 3 7-7" />
              </svg>
            </span>
          ) : (
            <span className="mt-[0.6rem] h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
          )}
          <span dir="auto" className="min-w-0 flex-1 text-start">{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function SubHeading({ children, icon }: { children: React.ReactNode; icon?: IconName }) {
  return (
    <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-primary-dark">
      {icon && <Icon name={icon} className="h-4 w-4 text-primary" />}
      {children}
    </p>
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
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={CONSISTENCY_TONE[a.cv_consistency]}>
          {t.result.aiConsistency}: {consistencyLabel[a.cv_consistency]}
        </Badge>
        <Badge tone={URGENCY_TONE[a.urgency]} pulse={a.urgency === "high"}>
          {t.result.aiUrgency}: {urgencyLabel[a.urgency]}
        </Badge>
      </div>

      <p dir="auto" className="border-s-2 border-primary/40 ps-4 text-start text-[0.98rem] leading-relaxed text-ink">{a.diagnosis_explanation}</p>

      {a.observed_symptoms.length > 0 && (
        <div>
          <SubHeading icon="search">{t.result.aiObservedSymptoms}</SubHeading>
          <BulletList items={a.observed_symptoms} />
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <InsightBlock icon="target" title={t.result.aiConfidenceAssessment} body={a.confidence_assessment} />
        <InsightBlock icon="chart" title={t.result.aiSeverityExplanation} body={a.severity_explanation} />
      </div>

      {a.treatment_guidance.length > 0 && (
        <div>
          <SubHeading icon="beaker">{t.result.aiTreatmentGuidance}</SubHeading>
          <BulletList items={a.treatment_guidance} icon="check" />
        </div>
      )}

      {a.prevention_guidance.length > 0 && (
        <div>
          <SubHeading icon="shieldCheck">{t.result.aiPreventionGuidance}</SubHeading>
          <BulletList items={a.prevention_guidance} icon="check" />
        </div>
      )}

      <InsightBlock icon="rain" title={t.result.aiEnvironmentalRisk} body={a.environmental_risk} />
    </div>
  );
}

function InsightBlock({ icon, title, body }: { icon: IconName; title: string; body: string }) {
  return (
    <div className="rounded-2xl bg-ink/[0.035] p-4">
      <SubHeading icon={icon}>{title}</SubHeading>
      <p dir="auto" className="-mt-1 text-start text-sm leading-relaxed text-ink">{body}</p>
    </div>
  );
}
