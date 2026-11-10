import { describe, expect, it } from "vitest";
import { safeRedirectPath } from "@/lib/safeRedirect";

describe("safeRedirectPath", () => {
  it("keeps paths inside the app", () => {
    expect(safeRedirectPath("/diagnoses/123")).toBe("/diagnoses/123");
    expect(safeRedirectPath("/reports/compare?a=1&b=2")).toBe("/reports/compare?a=1&b=2");
  });

  it("falls back for anything that could leave the site", () => {
    for (const path of ["//evil.example", "/\\evil.example", "\\\\evil.example", "/%5Cevil.example", "/%2F%2Fevil.example",
                        "https://evil.example", "javascript:alert(1)", "/\tevil", "", undefined, null, 42]) {
      expect(safeRedirectPath(path)).toBe("/dashboard");
    }
  });
});
