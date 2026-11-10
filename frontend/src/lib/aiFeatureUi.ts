/** Pure helpers shared by the AI-feature screens (unit-tested in aiFeatureUi.test.ts). */
import type { Readiness, RecoveryStatus, RiskLevel } from "@/types/aiFeatures";

/** Replace {name} placeholders in a translated string. */
export function formatTemplate(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => (key in values ? String(values[key]) : match));
}

export const RISK_COLORS: Record<RiskLevel, string> = {
  low: "#3f9d5a",
  moderate: "#e0a400",
  high: "#e46a1f",
  critical: "#c62828",
  insufficient_data: "#9ca3af",
  unavailable: "#9ca3af",
};

/** Color for the share of inspections that found the disease (observed layer). */
export function positiveRateColor(rate: number | null | undefined): string {
  if (rate == null) return "#9ca3af";
  if (rate < 0.1) return "#3f9d5a";
  if (rate < 0.3) return "#e0a400";
  if (rate < 0.6) return "#e46a1f";
  return "#c62828";
}

export const POSITIVE_RATE_BANDS: { label: string; color: string }[] = [
  { label: "< 10%", color: "#3f9d5a" },
  { label: "10–30%", color: "#e0a400" },
  { label: "30–60%", color: "#e46a1f" },
  { label: "≥ 60%", color: "#c62828" },
];

export type BadgeTone = "primary" | "mild" | "moderate" | "severe" | "neutral";

export function recoveryTone(status: RecoveryStatus | null | undefined): BadgeTone {
  switch (status) {
    case "improving":
      return "primary";
    case "worsening":
      return "severe";
    case "stable":
      return "mild";
    default:
      return "neutral";
  }
}

export function readinessTone(readiness: Readiness | "ok" | "failed"): BadgeTone {
  if (readiness === "ready" || readiness === "ok") return "primary";
  if (readiness === "error" || readiness === "failed" || readiness === "unavailable") return "severe";
  return "neutral";
}

/** Which "not available" message a non-ok segmentation status maps to. */
export function segmentationNotice(status: string | null | undefined): "older" | "waiting" | "failed" | "unavailable" {
  if (!status) return "older";
  if (status === "failed") return "failed";
  if (status === "unavailable" || status === "error") return "unavailable";
  return "waiting";
}

/**
 * Hide overlay pixels whose color is not in `visible` (for toggling individual
 * disease classes on the client). Works in place on RGBA ImageData-style bytes and
 * returns the same array. Colors are matched exactly — the server renders each class
 * in one flat color with no anti-aliasing.
 */
export function filterOverlayPixels(data: Uint8ClampedArray, visible: number[][]): Uint8ClampedArray {
  const keys = new Set(visible.map((c) => (c[0] << 16) | (c[1] << 8) | c[2]));
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] === 0) continue;
    if (!keys.has((data[i] << 16) | (data[i + 1] << 8) | data[i + 2])) data[i + 3] = 0;
  }
  return data;
}

/** "late_blight" -> "Late blight" (labels from the model are snake_case). */
export function humanizeLabel(label: string | null | undefined): string {
  if (!label) return "";
  const text = label.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Polyline points for a small line chart, values mapped into [pad, height - pad]. */
export function linePoints(values: number[], width: number, height: number, pad = 6, maxValue?: number): string {
  if (values.length === 0) return "";
  const max = maxValue ?? Math.max(...values, 1);
  const step = values.length > 1 ? (width - 2 * pad) / (values.length - 1) : 0;
  return values
    .map((v, i) => `${(pad + i * step).toFixed(1)},${(height - pad - (v / max) * (height - 2 * pad)).toFixed(1)}`)
    .join(" ");
}
