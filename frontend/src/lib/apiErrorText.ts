/**
 * An error from the API, in the reader's language.
 *
 * The server's messages are English. English readers get them as they are (they are the
 * most specific); everyone else gets the translation for the error's code, so no English
 * sentence lands on an Arabic page. A request that never reached the server (offline,
 * server down) is reported as a connection problem instead of the browser's
 * "Failed to fetch".
 */
import type { TranslationDict } from "@/i18n/en";
import { ApiError } from "@/types/api";

type ErrorCode = keyof TranslationDict["errors"];

export function apiErrorText(error: unknown, t: TranslationDict, locale: string): string {
  if (error instanceof ApiError) {
    if (locale === "en" && error.message) return error.message;
    return Object.prototype.hasOwnProperty.call(t.errors, error.code)
      ? t.errors[error.code as ErrorCode]
      : t.common.unknownError;
  }
  if (error instanceof TypeError) return t.errors.network; // fetch() rejects with TypeError when the request fails
  return t.common.unknownError;
}
