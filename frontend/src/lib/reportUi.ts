/** Helpers shared by the report screens. */
import featuresEn from "@/i18n/features.en";
import featuresAr from "@/i18n/features.ar";
import type { Horizon, ProvenanceKind, ReportFact, ReportRecommendation, ReportReference, StatementKind } from "@/types/reports";

export const PROVENANCE_COLORS: Record<ProvenanceKind, string> = {
  model: "#2563eb", model_evaluation: "#1d4ed8", model_measurement: "#0f766e", model_estimate: "#b45309", rule: "#475569",
  sourced_rule: "#4338ca", reference: "#4338ca", knowledge_base: "#15803d", general_guidance: "#6b7280",
  user_recorded: "#7c3aed", observation: "#0e7490", historical: "#334155", weather_provider: "#0369a1",
  llm_summary: "#be185d", system: "#6b7280",
};

export const STATEMENT_COLORS: Record<StatementKind, string> = {
  measured: "#0f766e", model: "#2563eb", estimate: "#b45309", evaluation: "#1d4ed8", knowledge: "#15803d",
  reference: "#4338ca", rule: "#475569", hypothesis: "#a16207", missing: "#9a3412", observation: "#0e7490",
};

export const HORIZONS: Horizon[] = ["immediate", "short_term", "long_term"];

/** Feature strings in a report's own language (a report is a document in one language). */
export function featuresFor(locale: "en" | "ar") {
  return locale === "ar" ? featuresAr : featuresEn;
}

export function reportDict(locale: "en" | "ar") {
  return featuresFor(locale).reports;
}

/** Numeric difference between two facts with the same key, or null when not comparable. */
export function factDelta(a?: ReportFact, b?: ReportFact): number | null {
  if (!a || !b || !a.available || !b.available) return null;
  if (typeof a.value !== "number" || typeof b.value !== "number") return null;
  if ((a.unit ?? "") !== (b.unit ?? "")) return null;
  return Math.round((b.value - a.value) * 100) / 100;
}

/** v2 reports: recommendations by time horizon, in order, skipping empty horizons. */
export function groupByHorizon(recs: ReportRecommendation[]): { horizon: Horizon; label: string; items: ReportRecommendation[] }[] {
  return HORIZONS.map((h) => {
    const items = recs.filter((r) => r.horizon === h);
    return { horizon: h, label: items[0]?.horizon_label ?? h, items };
  }).filter((g) => g.items.length > 0);
}

/** Citation numbers for a list of reference ids, sorted and de-duplicated; unknown ids are dropped. */
export function refNumbers(refs: string[] | undefined, references: ReportReference[] | undefined): number[] {
  if (!refs?.length || !references?.length) return [];
  const byId = new Map(references.map((r) => [r.id, r.n]));
  return [...new Set(refs.map((id) => byId.get(id)).filter((n): n is number => n != null))].sort((a, b) => a - b);
}

/** Digits in the report's language. */
export function localDigits(n: number, locale: "en" | "ar"): string {
  return locale === "ar" ? String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[Number(d)]) : String(n);
}
