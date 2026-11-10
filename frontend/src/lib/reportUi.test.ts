import { describe, expect, it } from "vitest";
import { factDelta, featuresFor, groupByHorizon, localDigits, refNumbers, reportDict } from "@/lib/reportUi";
import type { ReportFact, ReportRecommendation, ReportReference } from "@/types/reports";

const f = (value: unknown, extra: Partial<ReportFact> = {}): ReportFact => ({
  key: "k", label: "k", value, display: String(value), available: true, provenance: { kind: "model" }, ...extra,
});

describe("factDelta", () => {
  it("is the numeric change between two available facts with the same unit", () => {
    expect(factDelta(f(12.5, { unit: "%" }), f(8, { unit: "%" }))).toBe(-4.5);
  });
  it("is null when a value is missing, non-numeric or in another unit", () => {
    expect(factDelta(f(1), f(2, { available: false }))).toBeNull();
    expect(factDelta(f("early_blight"), f("late_blight"))).toBeNull();
    expect(factDelta(f(1, { unit: "%" }), f(2, { unit: "px" }))).toBeNull();
    expect(factDelta(undefined, f(2))).toBeNull();
  });
});

describe("report language", () => {
  it("uses the report's own language, not the app's", () => {
    expect(reportDict("ar").doc.executiveSummary).toBe("الملخص التنفيذي");
    expect(reportDict("en").doc.executiveSummary).toBe("Executive summary");
    expect(Object.keys(featuresFor("ar").reports.doc.provenance)).toEqual(Object.keys(featuresFor("en").reports.doc.provenance));
    expect(Object.keys(featuresFor("ar").reports.doc.statementKinds)).toEqual(Object.keys(featuresFor("en").reports.doc.statementKinds));
  });
  it("writes citation numbers in the report's digits", () => {
    expect(localDigits(12, "ar")).toBe("١٢");
    expect(localDigits(12, "en")).toBe("12");
  });
});

const rec = (id: string, horizon: ReportRecommendation["horizon"]): ReportRecommendation => ({
  id, rule: id, category: "monitoring", category_label: "", horizon, horizon_label: `${horizon} label`, priority: "low",
  priority_label: "", title: id, reason: "r", objective: "o", timing: "t", evidence: [], warnings: [], provenance: { kind: "rule" },
});

describe("groupByHorizon", () => {
  it("orders immediate, short-term, long-term and drops empty groups", () => {
    const groups = groupByHorizon([rec("a", "long_term"), rec("b", "immediate"), rec("c", "long_term")]);
    expect(groups.map((g) => g.horizon)).toEqual(["immediate", "long_term"]);
    expect(groups[1].items.map((r) => r.id)).toEqual(["a", "c"]);
    expect(groups[0].label).toBe("immediate label");
  });
});

describe("refNumbers", () => {
  const refs = [{ id: "ref-a", n: 2 }, { id: "ref-b", n: 1 }] as ReportReference[];
  it("maps ids to sorted, unique citation numbers and ignores unknown ids", () => {
    expect(refNumbers(["ref-a", "ref-b", "ref-a", "nope"], refs)).toEqual([1, 2]);
    expect(refNumbers(undefined, refs)).toEqual([]);
    expect(refNumbers(["ref-a"], undefined)).toEqual([]);
  });
});
