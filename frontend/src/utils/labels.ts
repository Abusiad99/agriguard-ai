import type { TranslationDict } from "@/i18n/en";

/** Human-readable text for a model token like "early_blight" → "Early blight". */
export function humanize(token?: string | null): string {
  if (!token) return "";
  const text = token.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function plantName(plant: string | null | undefined, t: TranslationDict): string {
  if (!plant) return "";
  return t.plantNames[plant] ?? humanize(plant);
}

/** "tomato___early_blight" → "Tomato — Early blight" (plant localized when a
 * translation exists; disease names are shown as the model's English class names). */
export function labelDisplay(label: string | null | undefined, t: TranslationDict): string {
  if (!label) return "";
  const [plant, condition] = label.includes("___") ? label.split("___", 2) : [null, label];
  const parts = [plant ? plantName(plant, t) : null, humanize(condition)].filter(Boolean);
  return parts.join(" — ");
}
