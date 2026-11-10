import { describe, expect, it } from "vitest";
import en from "@/i18n/en";
import ar from "@/i18n/ar";
import { formatMeasurement, itemRefNumbers, localized, VERDICT_TONE } from "@/lib/weatherGuidanceUi";
import type { WeatherGuidance } from "@/types/api";

const labelsEn = en.result.weatherGuidance;
const labelsAr = ar.result.weatherGuidance;

describe("formatMeasurement", () => {
  it("formats valid values with units in each language", () => {
    expect(formatMeasurement("wind_speed_kmh", { state: "ok", value: 12.874752 }, "en", labelsEn).text).toBe("12.9 km/h");
    expect(formatMeasurement("rain_probability_pct", { state: "ok", value: 60 }, "en", labelsEn).text).toBe("60%");
    expect(formatMeasurement("temperature_c", { state: "ok", value: 22.8 }, "ar", labelsAr).text).toBe("٢٢٫٨ °م");
    expect(formatMeasurement("rain_probability_pct", { state: "ok", value: 60 }, "ar", labelsAr).text).toBe("٦٠٪");
    // matches the server texts ("21.0 km/h"), so the grid and the guidance never disagree
    expect(formatMeasurement("wind_speed_kmh", { state: "ok", value: 21 }, "en", labelsEn).text).toBe("21.0 km/h");
    expect(formatMeasurement("temperature_c", { state: "ok", value: 27 }, "ar", labelsAr).text).toBe("٢٧٫٠ °م");
  });
  it("never shows a value for missing or invalid readings", () => {
    expect(formatMeasurement("humidity_pct", { state: "missing", value: null }, "en", labelsEn))
      .toEqual({ text: "Not recorded", state: "missing" });
    // the server sends invalid readings with value null: they must still read as invalid, not "not recorded"
    expect(formatMeasurement("wind_speed_kmh", { state: "invalid", value: null }, "en", labelsEn))
      .toEqual({ text: labelsEn.invalid, state: "invalid" });
    expect(formatMeasurement("humidity_pct", { state: "invalid", value: null }, "ar", labelsAr))
      .toEqual({ text: labelsAr.invalid, state: "invalid" });
    expect(formatMeasurement("wind_speed_kmh", { state: "invalid", value: -5 }, "ar", labelsAr).text).toBe(labelsAr.invalid);
    expect(formatMeasurement("uv_index", undefined, "en", labelsEn).state).toBe("missing");
  });
});

describe("server text and citations", () => {
  const guidance = {
    verdict: "wait", measurements: {}, summary: { en: "Wait.", ar: "انتظر." },
    items: [{ code: "rain", status: "caution", basis: "reference", refs: ["ref-rainfast", "ref-unknown"], text: { en: "e", ar: "ع" } }],
    references: [{ id: "ref-spray-wind", n: 1, title: "t", url: "https://x", claims: {} },
                 { id: "ref-rainfast", n: 2, title: "t", url: "https://y", claims: {} }],
  } as unknown as WeatherGuidance;

  it("shows the reader's language and drops unknown references", () => {
    expect(localized(guidance.summary, "ar")).toBe("انتظر.");
    expect(itemRefNumbers(guidance.items[0], guidance)).toEqual([2]);
  });
  it("has a tone for every verdict, and translations for every label", () => {
    expect(Object.keys(VERDICT_TONE).sort()).toEqual(Object.keys(labelsEn.verdicts).sort());
    expect(Object.keys(labelsAr).sort()).toEqual(Object.keys(labelsEn).sort());
    expect(Object.keys(labelsAr.verdicts).sort()).toEqual(Object.keys(labelsEn.verdicts).sort());
    expect(Object.keys(labelsAr.basis).sort()).toEqual(Object.keys(labelsEn.basis).sort());
    expect(ar.result.aiWeatherAdviceRemoved).toBeTruthy();
  });
});
