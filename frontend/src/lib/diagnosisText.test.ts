import { describe, expect, it } from "vitest";
import en from "@/i18n/en";
import ar from "@/i18n/ar";
import { textDirection } from "@/i18n/direction";
import {
  diagnosisLoadError, diseaseDescription, preventionAdvice, reportDownloadError, treatmentInstructions,
} from "@/lib/diagnosisText";
import { ApiError, type DiseaseSchema } from "@/types/api";

// Fixed English notice the server sends with knowledge_base_status = "not_listed".
const SERVER_NOTICE =
  "This condition is not yet in the AgriGuard knowledge base, so no verified description or treatment is available. Please consult your local agricultural authority.";
// Codes the backend sends (backend/app/application/services/guidance.py, GENERIC_PREVENTION_CODES).
const BACKEND_PREVENTION_CODES = ["irrigation_ventilation", "remove_infected_material", "rotation_sanitation"];
const ARABIC = /[؀-ۿ]/;

const unlisted = (): DiseaseSchema => ({
  name: "Late blight", description: SERVER_NOTICE, symptoms: [], causes: [], knowledge_base_status: "not_listed",
});
const apiError = (status: number, message: string) =>
  new ApiError(status, { error: { code: status === 404 ? "NOT_FOUND" : "INTERNAL_ERROR", message, details: [] }, request_id: null });

describe("diseaseDescription", () => {
  it("shows the not-in-knowledge-base notice in the reader's language", () => {
    expect(diseaseDescription(unlisted(), en)).toBe(SERVER_NOTICE);
    const arText = diseaseDescription(unlisted(), ar);
    expect(arText).toBe(ar.result.notInKnowledgeBase);
    expect(arText).toMatch(ARABIC);
    expect(arText).toContain("AgriGuard");
    expect(arText).not.toContain("knowledge base");
  });

  it("passes a knowledge-base description through unchanged, in both languages", () => {
    const listed: DiseaseSchema = { name: "Early blight", description: "SYNTHETIC: a fungal disease.", symptoms: [], causes: [] };
    expect(diseaseDescription(listed, en)).toBe("SYNTHETIC: a fungal disease.");
    expect(diseaseDescription(listed, ar)).toBe("SYNTHETIC: a fungal disease.");
    expect(diseaseDescription({ ...listed, knowledge_base_status: "listed" }, ar)).toBe("SYNTHETIC: a fungal disease.");
  });

  it("leaves the diagnosis data itself untouched", () => {
    const d = unlisted();
    const before = structuredClone(d);
    diseaseDescription(d, ar);
    expect(d).toEqual(before); // name, status and server text unchanged
  });
});

describe("treatmentInstructions", () => {
  it("translates the withheld-dosage referral and keeps real instructions as written", () => {
    const withheld = { instructions: en.result.authorityReferral, instructions_withheld: true };
    expect(treatmentInstructions(withheld, ar)).toBe(ar.result.authorityReferral);
    expect(treatmentInstructions(withheld, en)).toBe(en.result.authorityReferral);
    expect(treatmentInstructions({ instructions: "SYNTHETIC: remove infected leaves." }, ar)).toBe("SYNTHETIC: remove infected leaves.");
    expect(treatmentInstructions({ instructions: null }, ar)).toBeNull();
  });
});

describe("preventionAdvice", () => {
  const server = {
    prevention_advice: [
      "Ensure proper irrigation and ventilation.", "Remove and destroy infected plant material.",
      "Practice crop rotation and field sanitation.",
    ],
    prevention_advice_codes: BACKEND_PREVENTION_CODES,
  };

  it("translates every code the backend sends, in order", () => {
    expect(preventionAdvice(server, en)).toEqual(server.prevention_advice);
    const items = preventionAdvice(server, ar);
    expect(items).toEqual(BACKEND_PREVENTION_CODES.map((c) => ar.result.genericPrevention[c as keyof typeof ar.result.genericPrevention]));
    items.forEach((item) => expect(item).toMatch(ARABIC));
  });

  it("keeps the server text for unknown codes and for older servers without codes", () => {
    expect(preventionAdvice({ prevention_advice: ["SYNTHETIC tip"], prevention_advice_codes: ["something_new"] }, ar)).toEqual(["SYNTHETIC tip"]);
    expect(preventionAdvice({ prevention_advice: ["SYNTHETIC tip"], prevention_advice_codes: ["toString"] }, ar)).toEqual(["SYNTHETIC tip"]);
    expect(preventionAdvice({ prevention_advice: ["SYNTHETIC tip"] }, ar)).toEqual(["SYNTHETIC tip"]);
  });
});

describe("dictionaries", () => {
  it("translate every new diagnosis text into Arabic", () => {
    for (const key of ["notInKnowledgeBase", "authorityReferral", "notFound", "reportNotAvailable", "reportDownloadFailed"] as const) {
      expect(ar.result[key]).toMatch(ARABIC);
      expect(ar.result[key]).not.toBe(en.result[key]);
    }
    expect(Object.keys(en.result.genericPrevention).sort()).toEqual([...BACKEND_PREVENTION_CODES].sort());
    expect(Object.keys(ar.result.genericPrevention).sort()).toEqual([...BACKEND_PREVENTION_CODES].sort());
  });
});

describe("textDirection", () => {
  it("is right to left for Arabic and left to right for English", () => {
    expect(textDirection("ar")).toBe("rtl");
    expect(textDirection("en")).toBe("ltr");
  });
});

describe("diagnosis page errors", () => {
  it("are translated for Arabic readers, never the server's English message", () => {
    expect(diagnosisLoadError(apiError(404, "Diagnosis not found."), ar, "ar")).toBe(ar.result.notFound);
    expect(diagnosisLoadError(apiError(403, "Forbidden"), ar, "ar")).toBe(ar.result.noAccess);
    expect(diagnosisLoadError(apiError(500, "Internal error"), ar, "ar")).toBe(ar.common.unknownError);
    expect(diagnosisLoadError(new Error("Failed to fetch"), ar, "ar")).toBe(ar.common.unknownError);
    expect(reportDownloadError(apiError(404, "No completed report exists for this diagnosis."), ar, "ar")).toBe(ar.result.reportNotAvailable);
    expect(reportDownloadError(apiError(500, "Internal error"), ar, "ar")).toBe(ar.result.reportDownloadFailed);
  });

  it("keep the server's specific message for English readers", () => {
    expect(diagnosisLoadError(apiError(404, "Diagnosis not found."), en, "en")).toBe(en.result.notFound);
    expect(diagnosisLoadError(apiError(429, "Too many requests."), en, "en")).toBe("Too many requests.");
    expect(reportDownloadError(apiError(500, "Storage unavailable."), en, "en")).toBe("Storage unavailable.");
  });
});
