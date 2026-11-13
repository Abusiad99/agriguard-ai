import { describe, expect, it } from "vitest";
import en from "@/i18n/en";
import ar from "@/i18n/ar";
import { apiErrorText } from "@/lib/apiErrorText";
import { ApiError } from "@/types/api";

// Codes the backend can send (backend/app/core/exceptions.py, exception_middleware.py,
// security_middleware.py, application/reporting/service.py).
const BACKEND_CODES = [
  "VALIDATION_ERROR", "INVALID_CREDENTIALS", "INVALID_OR_REVOKED_TOKEN", "FORBIDDEN", "NOT_FOUND", "CONFLICT",
  "UNPROCESSABLE_ENTITY", "INVALID_IMAGE", "FILE_TOO_LARGE", "RATE_LIMITED", "SERVICE_UNAVAILABLE",
  "DOSAGE_SOURCE_REQUIRED", "REPORT_INTEGRITY_ERROR", "INTERNAL_ERROR",
];
const ARABIC = /[؀-ۿ]/;
const LATIN_WORD = /[A-Za-z]{3,}/;

const apiError = (code: string, message: string, status = 400) =>
  new ApiError(status, { error: { code, message, details: [] }, request_id: null });

describe("apiErrorText", () => {
  it("gives Arabic readers a translation for every backend error code, with no English left", () => {
    for (const code of BACKEND_CODES) {
      const text = apiErrorText(apiError(code, "Some English server message."), ar, "ar");
      expect(text, code).toMatch(ARABIC);
      expect(text, code).not.toMatch(LATIN_WORD);
      expect(text, code).not.toBe(ar.common.unknownError); // a specific message, not the generic one
    }
  });

  it("keeps the server's specific message for English readers", () => {
    expect(apiErrorText(apiError("CONFLICT", "That scan is already linked to another tracked plant.", 409), en, "en"))
      .toBe("That scan is already linked to another tracked plant.");
  });

  it("falls back to the generic message for codes it does not know", () => {
    expect(apiErrorText(apiError("SOMETHING_NEW", "New server message."), ar, "ar")).toBe(ar.common.unknownError);
    expect(apiErrorText(apiError("toString", "x"), ar, "ar")).toBe(ar.common.unknownError);
    expect(apiErrorText(apiError("SOMETHING_NEW", ""), en, "en")).toBe(en.common.unknownError);
  });

  it("reports a failed request as a connection problem, never the browser's raw error", () => {
    expect(apiErrorText(new TypeError("Failed to fetch"), en, "en")).toBe(en.errors.network);
    expect(apiErrorText(new TypeError("Failed to fetch"), ar, "ar")).toBe(ar.errors.network);
    expect(apiErrorText(new Error("boom"), ar, "ar")).toBe(ar.common.unknownError);
    expect(apiErrorText("not even an error", en, "en")).toBe(en.common.unknownError);
  });

  it("has the same error codes in both dictionaries", () => {
    expect(Object.keys(ar.errors).sort()).toEqual(Object.keys(en.errors).sort());
    for (const code of BACKEND_CODES) expect(Object.keys(en.errors)).toContain(code);
  });
});
