/**
 * Display helpers for the server's weather guidance. They format what the backend decided;
 * they never assess weather, apply thresholds or choose a verdict.
 */
import type { WeatherGuidance, WeatherGuidanceItem, WeatherMeasurement, WeatherMeasurementKey, WeatherVerdict } from "@/types/api";

export type UiLocale = "en" | "ar";

export const MEASUREMENT_ORDER: WeatherMeasurementKey[] = [
  "wind_speed_kmh", "rain_probability_pct", "temperature_c", "humidity_pct", "uv_index",
];

/** Badge tone for each server verdict (presentation only). */
export const VERDICT_TONE: Record<WeatherVerdict, "primary" | "moderate" | "mild" | "neutral"> = {
  within_limits: "primary",
  wait: "moderate",
  incomplete: "mild",
  not_assessed: "neutral",
  not_applicable: "neutral",
};

export function formatNumber(value: number, locale: UiLocale, maxFractionDigits = 1, minFractionDigits = 0): string {
  return new Intl.NumberFormat(locale === "ar" ? "ar-EG" : "en-US", {
    minimumFractionDigits: minFractionDigits, maximumFractionDigits: maxFractionDigits,
  }).format(value);
}

export interface MeasurementLabels {
  notRecorded: string;
  invalid: string;
  kmh: string;
  celsius: string;
}

/** A measurement as text in the reader's language, or the reason it is not shown. */
export function formatMeasurement(key: WeatherMeasurementKey, m: WeatherMeasurement | undefined, locale: UiLocale,
                                  labels: MeasurementLabels): { text: string; state: WeatherMeasurement["state"] } {
  // The server sends no value for invalid readings, so check the state before the value.
  if (m?.state === "invalid") return { text: labels.invalid, state: "invalid" };
  if (!m || m.state === "missing" || m.value == null) return { text: labels.notRecorded, state: "missing" };
  // Same precision as the server's guidance texts: wind and temperature to one decimal, percentages whole.
  const n = key.endsWith("_pct") ? formatNumber(m.value, locale, 0)
    : key === "uv_index" ? formatNumber(m.value, locale, 1)
    : formatNumber(m.value, locale, 1, 1);
  const percent = locale === "ar" ? "٪" : "%";
  const text = key === "wind_speed_kmh" ? `${n} ${labels.kmh}`
    : key === "temperature_c" ? `${n} ${labels.celsius}`
    : key.endsWith("_pct") ? `${n}${percent}`
    : n;
  return { text, state: "ok" };
}

/** Text in the reader's language. The server always sends both; English is only a guard. */
export function localized(text: Partial<Record<UiLocale, string>> | undefined, locale: UiLocale): string {
  return text?.[locale] ?? text?.en ?? "";
}

/** Citation numbers an item points to, in the order of the source list. */
export function itemRefNumbers(item: WeatherGuidanceItem, guidance: WeatherGuidance): number[] {
  const byId = new Map(guidance.references.map((r) => [r.id, r.n]));
  return [...new Set(item.refs.map((id) => byId.get(id)).filter((n): n is number => n != null))].sort((a, b) => a - b);
}
