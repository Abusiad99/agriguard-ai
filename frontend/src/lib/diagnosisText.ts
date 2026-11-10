/**
 * Diagnosis texts in the reader's language.
 *
 * For a few fixed notices the server sends English text together with a status
 * (`disease.knowledge_base_status`, `instructions_withheld`, `prevention_advice_codes`).
 * These helpers show the translation for that status and pass knowledge-base content
 * (descriptions, instructions written by agronomists) through unchanged. They decide
 * nothing about the diagnosis itself.
 */
import type { TranslationDict } from "@/i18n/en";
import { ApiError, type DiagnosisResponse, type DiseaseSchema, type TreatmentGroupSchema } from "@/types/api";

type GenericPreventionCode = keyof TranslationDict["result"]["genericPrevention"];

/** The knowledge-base description, or the translated "not in the knowledge base yet" notice. */
export function diseaseDescription(disease: DiseaseSchema, t: TranslationDict): string {
  return disease.knowledge_base_status === "not_listed" ? t.result.notInKnowledgeBase : disease.description;
}

/** Treatment instructions, or the translated referral when the server withheld them (BR6). */
export function treatmentInstructions(group: TreatmentGroupSchema, t: TranslationDict): string | null {
  if (group.instructions_withheld) return t.result.authorityReferral;
  return group.instructions ?? null;
}

/** General prevention practice, translated by code; an unknown code keeps the server's text. */
export function preventionAdvice(
  d: Pick<DiagnosisResponse, "prevention_advice" | "prevention_advice_codes">,
  t: TranslationDict,
): string[] {
  const codes = d.prevention_advice_codes ?? [];
  return d.prevention_advice.map((text, i) => {
    const code = codes[i];
    return code && Object.prototype.hasOwnProperty.call(t.result.genericPrevention, code)
      ? t.result.genericPrevention[code as GenericPreventionCode]
      : text;
  });
}

/**
 * Why a diagnosis could not be shown. Access and not-found are translated; anything else
 * keeps the server's (English) message for English readers and a translated generic
 * message for everyone else, so no untranslated text reaches an Arabic page.
 */
export function diagnosisLoadError(error: unknown, t: TranslationDict, locale: string): string {
  if (error instanceof ApiError && error.status === 403) return t.result.noAccess;
  if (error instanceof ApiError && error.status === 404) return t.result.notFound;
  return fallback(error, t, locale);
}

/** Why the per-scan PDF could not be downloaded, in the reader's language. */
export function reportDownloadError(error: unknown, t: TranslationDict, locale: string): string {
  if (error instanceof ApiError && error.status === 403) return t.result.noAccess;
  if (error instanceof ApiError && error.status === 404) return t.result.reportNotAvailable;
  return locale === "en" && error instanceof ApiError && error.message ? error.message : t.result.reportDownloadFailed;
}

function fallback(error: unknown, t: TranslationDict, locale: string): string {
  return locale === "en" && error instanceof Error && error.message ? error.message : t.common.unknownError;
}
