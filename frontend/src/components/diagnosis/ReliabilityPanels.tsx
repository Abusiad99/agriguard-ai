import { useMemo, useState } from "react";
import type {
  Candidate,
  DecisionStatus,
  DiagnosisResponse,
  Differential,
  FollowUpQuestion,
  ImageQuality,
} from "@/types/api";
import { useLocale } from "@/context/LocaleContext";
import { Badge } from "@/components/ui/Badge";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Icon, type IconName } from "@/components/ui/Icon";
import { labelDisplay } from "@/utils/labels";

type Tone = "primary" | "mild" | "moderate" | "severe" | "neutral";

const STATUS_TONE: Record<DecisionStatus, Tone> = {
  confident: "primary",
  uncertain: "mild",
  inconclusive: "moderate",
  legacy: "neutral",
};

const STATUS_ICON: Record<DecisionStatus, IconName> = {
  confident: "shieldCheck",
  uncertain: "question",
  inconclusive: "search",
  legacy: "history",
};

export function StatusBadge({ status, className = "" }: { status?: DecisionStatus | null; className?: string }) {
  const { t } = useLocale();
  const s = status ?? "legacy";
  return (
    <Badge tone={STATUS_TONE[s]} className={className}>
      {t.status[s]}
    </Badge>
  );
}

/** Prominent explanation of what the decision status means — the first thing a user
 * reads, so an uncertain result is never mistaken for a diagnosis. */
export function DecisionBanner({ d }: { d: DiagnosisResponse }) {
  const { t } = useLocale();
  const status = d.decision_status ?? "legacy";
  const body = {
    confident: t.status.confidentBody,
    uncertain: t.status.uncertainBody,
    inconclusive: t.status.inconclusiveBody,
    legacy: t.status.legacyBody,
  }[status];
  const tones: Record<DecisionStatus, string> = {
    confident: "border-primary/25 bg-primary-light/60 text-primary-dark",
    uncertain: "border-severity-mild/35 bg-severity-mild-bg/70 text-severity-mild",
    inconclusive: "border-severity-moderate/35 bg-severity-moderate-bg/70 text-severity-moderate",
    legacy: "border-line bg-ink/[0.04] text-muted",
  };
  const source = d.decision?.thresholds?.source;
  return (
    <div role="status" className={`flex items-start gap-3 rounded-2xl border px-4 py-3.5 ${tones[status]}`}>
      <Icon name={STATUS_ICON[status]} className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="min-w-0 text-start text-sm leading-relaxed">
        <p className="font-semibold">{t.status[status]}</p>
        <p className="mt-0.5">{body}</p>
        {status !== "legacy" && source && (
          <p className="mt-1.5 text-xs opacity-80">
            {source === "validation"
              ? t.status.thresholdsValidated
              : source === "env_override"
                ? t.status.thresholdsOverride
                : t.status.thresholdsUnvalidated}
          </p>
        )}
      </div>
    </div>
  );
}

export function QualityNotes({ quality }: { quality?: ImageQuality | null }) {
  const { t } = useLocale();
  if (!quality || quality.issues.length === 0) return null;
  return (
    <div className="rounded-2xl border border-severity-mild/30 bg-severity-mild-bg/50 p-4">
      <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-severity-mild">
        <Icon name="photo" className="h-4 w-4" />
        {t.quality.warningTitle}
      </p>
      <QualityIssueList quality={quality} />
    </div>
  );
}

export function QualityIssueList({ quality }: { quality: ImageQuality }) {
  const { t } = useLocale();
  return (
    <ul className="flex flex-col gap-2">
      {quality.issues.map((issue) => {
        const [title, hint] = t.quality.codes[issue.code] ?? [issue.message, issue.hint];
        return (
          <li key={issue.code} className="flex items-start gap-2.5 text-sm text-ink">
            <Icon
              name={issue.severity === "reject" ? "error" : "warning"}
              className={`mt-0.5 h-4 w-4 shrink-0 ${issue.severity === "reject" ? "text-severity-severe" : "text-severity-mild"}`}
            />
            <span className="min-w-0">
              <span className="font-semibold">{title}.</span> <span className="text-muted">{hint}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function CandidateRow({ c, rank }: { c: Candidate; rank: number }) {
  const { t } = useLocale();
  const pct = Math.max(0, Math.min(100, c.probability_pct ?? 0));
  return (
    <li className="rounded-2xl bg-ink/[0.035] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink">
            <span className="me-2 font-data text-muted">{rank}.</span>
            {labelDisplay(c.label, t)}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            {c.cause_type && <span>{t.reliability.causeTypes[c.cause_type] ?? c.cause_type}</span>}
            {!c.has_knowledge_base_entry && <span>· {t.reliability.noKbEntry}</span>}
          </p>
          {c.regulated_in_many_regions && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs font-medium text-severity-severe">
              <Icon name="warning" className="h-3.5 w-3.5" />
              {t.reliability.regulated}
            </p>
          )}
        </div>
        <span className="shrink-0 font-data text-sm font-semibold tabular-nums text-ink">{pct.toFixed(1)}%</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink/[0.07]" aria-hidden="true">
        <div className="h-full rounded-full bg-primary/70" style={{ width: `${pct}%` }} />
      </div>
    </li>
  );
}

export function CandidatesPanel({ differential }: { differential?: Differential | null }) {
  const { t } = useLocale();
  if (!differential || differential.model_candidates.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-sm text-muted">{t.reliability.candidatesBody}</p>
      <ul className="mt-3 flex flex-col gap-2.5">
        {differential.model_candidates.map((c, i) => (
          <CandidateRow key={c.label ?? i} c={c} rank={i + 1} />
        ))}
      </ul>
    </div>
  );
}

export function AlsoConsiderPanel({ differential }: { differential?: Differential | null }) {
  const { t } = useLocale();
  if (!differential || differential.also_consider.length === 0) return null;
  return (
    <div>
      <p className="mb-3 text-sm text-muted">{t.reliability.alsoConsiderBody}</p>
      <ul className="flex flex-wrap gap-2">
        {differential.also_consider.map((c) => (
          <li key={c} className="rounded-full bg-ink/[0.05] px-3 py-1.5 text-sm text-ink ring-1 ring-inset ring-ink/10">
            {t.reliability.categories[c] ?? c}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ExpertReviewNotice({ differential }: { differential?: Differential | null }) {
  const { t } = useLocale();
  if (!differential?.expert_review_recommended) return null;
  const reasons = differential.expert_review_reasons.map((r) => t.reliability.expertReasons[r] ?? r);
  return (
    <Alert tone="warning" title={t.reliability.expertTitle}>
      {reasons.join(" · ")}
    </Alert>
  );
}

/** Follow-up questions. Answers are saved as the user's own observations and
 * produce "what to check" hints; they never alter model probabilities. */
export function FollowUpForm({
  differential,
  questions,
  onSubmit,
  readOnly,
}: {
  differential: Differential;
  questions: FollowUpQuestion[];
  onSubmit: (answers: Record<string, string | string[]>) => Promise<void>;
  readOnly?: boolean;
}) {
  const { t } = useLocale();
  const relevant = useMemo(
    () => questions.filter((q) => differential.follow_up_questions.includes(q.id)),
    [questions, differential.follow_up_questions]
  );
  const [answers, setAnswers] = useState<Record<string, string | string[]>>(differential.answers ?? {});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (relevant.length === 0) return null;

  const toggle = (qid: string, value: string, multi: boolean) => {
    setSaved(false);
    setAnswers((prev) => {
      if (!multi) return { ...prev, [qid]: value };
      const current = Array.isArray(prev[qid]) ? (prev[qid] as string[]) : [];
      const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
      return { ...prev, [qid]: next };
    });
  };

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const cleaned = Object.fromEntries(
        Object.entries(answers).filter(([, v]) => (Array.isArray(v) ? v.length > 0 : Boolean(v)))
      );
      await onSubmit(cleaned);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : t.common.unknownError);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-muted">{t.reliability.followUpBody}</p>
      {relevant.map((q) => (
        <fieldset key={q.id} disabled={readOnly}>
          <legend className="mb-2 text-sm font-semibold text-ink">{t.reliability.questions[q.id] ?? q.id}</legend>
          <div className="flex flex-wrap gap-2">
            {q.options.map((opt) => {
              const value = answers[q.id];
              const selected = Array.isArray(value) ? value.includes(opt) : value === opt;
              return (
                <button
                  key={opt}
                  type="button"
                  role={q.type === "multi" ? "checkbox" : "radio"}
                  aria-checked={selected}
                  onClick={() => toggle(q.id, opt, q.type === "multi")}
                  className={`rounded-full px-3.5 py-1.5 text-sm ring-1 ring-inset transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary
                    ${selected ? "bg-primary text-white ring-primary" : "bg-surface/60 text-ink ring-line hover:ring-primary/40"}`}
                >
                  {t.reliability.options[opt] ?? opt}
                </button>
              );
            })}
          </div>
        </fieldset>
      ))}
      {error && <Alert tone="error">{error}</Alert>}
      {!readOnly && (
        <div className="flex items-center gap-3">
          <Button icon="check" isLoading={saving} onClick={() => void submit()}>
            {t.reliability.followUpSubmit}
          </Button>
          {saved && <span className="text-sm text-primary">{t.reliability.followUpSaved}</span>}
        </div>
      )}
      {differential.hints.length > 0 && (
        <div className="rounded-2xl bg-ink/[0.035] p-4">
          <p className="mb-2 text-sm font-semibold text-ink">{t.reliability.hintsTitle}</p>
          <ul className="flex flex-col gap-2">
            {differential.hints.map((h) => (
              <li key={h.code} className="flex items-start gap-2 text-sm text-ink">
                <Icon name={h.kind === "consistent" ? "check" : "search"} className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <span>
                  <span className="font-semibold">{t.reliability.hintKinds[h.kind]}: </span>
                  {t.reliability.hints[h.code] ?? h.code}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Original photo next to the model-attention map, each clearly captioned. */
export function ImagePanels({ d }: { d: DiagnosisResponse }) {
  const { t } = useLocale();
  const original = d.original_image_url ?? d.roi_image_url;
  const attention = d.explanation?.available ? d.explanation.image_url ?? d.heatmap_image_url : d.heatmap_image_url;
  const seg = d.segmentation?.overlay_url;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Figure src={original} caption={t.reliability.original} alt={t.reliability.original} />
      {attention ? (
        <Figure src={attention} caption={t.reliability.attention} note={t.reliability.attentionNote} alt={t.reliability.attention} />
      ) : (
        <div className="flex min-h-[10rem] items-center justify-center rounded-2xl border border-dashed border-line p-4 text-center text-sm text-muted">
          {t.reliability.attentionUnavailable}
        </div>
      )}
      {seg && <Figure src={seg} caption={t.reliability.segmentationOverlay} alt={t.reliability.segmentationOverlay} />}
    </div>
  );
}

function Figure({ src, caption, note, alt }: { src?: string | null; caption: string; note?: string; alt: string }) {
  return (
    <figure className="flex flex-col gap-2">
      <div className="overflow-hidden rounded-2xl bg-grove/10">
        {src ? (
          <img src={src} alt={alt} loading="lazy" className="aspect-square w-full object-contain" />
        ) : (
          <div className="flex aspect-square items-center justify-center text-muted">
            <Icon name="photo" className="h-8 w-8" />
          </div>
        )}
      </div>
      <figcaption className="text-start">
        <span className="text-sm font-semibold text-ink">{caption}</span>
        {note && <span className="mt-0.5 block text-xs leading-relaxed text-muted">{note}</span>}
      </figcaption>
    </figure>
  );
}

/** Affected-area measurement, or an explicit "not measured" state. Legacy
 * attention-derived numbers are labelled as such and never shown as a measurement. */
export function MeasurementPanel({ d }: { d: DiagnosisResponse }) {
  const { t } = useLocale();
  if (d.measurement_basis === "segmentation" && d.affected_area_pct != null) {
    const m = d.segmentation?.measurement;
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-baseline gap-3">
          <span className="font-display text-4xl font-semibold tabular-nums text-ink">{d.affected_area_pct.toFixed(1)}%</span>
          <Badge tone="primary">{t.reliability.measured}</Badge>
        </div>
        <p className="text-sm leading-relaxed text-muted">{t.reliability.measuredBody}</p>
        {m && (
          <p className="text-xs text-muted">
            {t.reliability.regions.replace("{leaf}", String(m.leaf_regions)).replace("{lesion}", String(m.lesion_regions))}
          </p>
        )}
        {!d.severity_level && <p className="text-xs text-muted">{t.reliability.severityNoScale}</p>}
      </div>
    );
  }
  if (d.measurement_basis === "legacy_attention_estimate" && d.affected_area_pct != null) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-baseline gap-3">
          <span className="font-display text-2xl font-semibold tabular-nums text-muted line-through decoration-1">
            {d.affected_area_pct.toFixed(1)}%
          </span>
          <Badge tone="neutral">{t.reliability.legacyEstimate}</Badge>
        </div>
        <p className="text-sm leading-relaxed text-muted">{t.reliability.legacyEstimateBody}</p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <Badge tone="neutral" className="w-fit">
        {t.reliability.notMeasured}
      </Badge>
      <p className="text-sm leading-relaxed text-muted">{t.reliability.notMeasuredBody}</p>
    </div>
  );
}

export function LimitationsList({ codes }: { codes: string[] }) {
  const { t } = useLocale();
  if (codes.length === 0) return null;
  return (
    <ul className="flex flex-col gap-2">
      {codes.map((c) => (
        <li key={c} className="flex items-start gap-2.5 text-sm leading-relaxed text-muted">
          <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0" />
          {t.reliability.limitations[c] ?? c}
        </li>
      ))}
    </ul>
  );
}

export function ProvenanceLine({ d }: { d: DiagnosisResponse }) {
  const { t } = useLocale();
  if (!d.model_version && !d.pipeline_version) return null;
  return (
    <p className="break-all text-xs text-muted" dir="ltr">
      {t.reliability.modelVersion}: {d.model_version ?? "—"} · {t.reliability.pipelineVersion}: {d.pipeline_version ?? "—"}
    </p>
  );
}
