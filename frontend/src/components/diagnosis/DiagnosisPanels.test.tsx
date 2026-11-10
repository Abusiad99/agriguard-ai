/**
 * Renders the diagnosis components to HTML (react-dom/server, no browser) in English and
 * Arabic. The locale comes from the same storage key the app uses. Data is SYNTHETIC.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import en from "@/i18n/en";
import ar from "@/i18n/ar";
import { LocaleProvider } from "@/context/LocaleContext";
import { DiseaseDescription, TreatmentSection } from "@/components/diagnosis/DiagnosisPanels";
import type { DiseaseSchema } from "@/types/api";

function render(node: ReactNode, locale: "en" | "ar"): string {
  vi.stubGlobal("localStorage", { getItem: () => locale, setItem: () => undefined });
  return renderToStaticMarkup(<LocaleProvider>{node}</LocaleProvider>);
}

afterEach(() => vi.unstubAllGlobals());

const SERVER_NOTICE =
  "This condition is not yet in the AgriGuard knowledge base, so no verified description or treatment is available. Please consult your local agricultural authority.";
const unlisted: DiseaseSchema = {
  name: "Late blight", description: SERVER_NOTICE, symptoms: [], causes: [], knowledge_base_status: "not_listed",
};

describe("DiseaseDescription", () => {
  it("renders the English notice for a condition that is not in the knowledge base", () => {
    const html = render(<DiseaseDescription disease={unlisted} />, "en");
    expect(html).toContain(en.result.notInKnowledgeBase);
    expect(html).toContain('data-kb-status="not_listed"');
  });

  it("renders the Arabic notice, with no English left, and lets the browser lay it out right to left", () => {
    const html = render(<DiseaseDescription disease={unlisted} />, "ar");
    expect(html).toContain(ar.result.notInKnowledgeBase);
    expect(html).not.toContain("knowledge base");
    expect(html).toContain('dir="auto"'); // Arabic text resolves to RTL inside the RTL page
    expect(html).toContain('data-kb-status="not_listed"');
  });

  it("renders a knowledge-base description as written, in either language", () => {
    const listed: DiseaseSchema = { name: "Early blight", description: "SYNTHETIC: a fungal disease.", symptoms: [], causes: [] };
    for (const locale of ["en", "ar"] as const) {
      const html = render(<DiseaseDescription disease={listed} />, locale);
      expect(html).toContain("SYNTHETIC: a fungal disease.");
      expect(html).toContain('data-kb-status="listed"');
    }
  });
});

describe("TreatmentSection", () => {
  it("shows the withheld-dosage referral in Arabic and real instructions unchanged", () => {
    const html = render(
      <TreatmentSection treatment={{ chemical: { instructions: en.result.authorityReferral, instructions_withheld: true } }} />, "ar");
    expect(html).toContain(ar.result.authorityReferral);
    expect(html).not.toContain("agricultural authority");

    const organic = render(<TreatmentSection treatment={{ organic: { instructions: "SYNTHETIC: remove infected leaves." } }} />, "ar");
    expect(organic).toContain("SYNTHETIC: remove infected leaves.");
  });
});
