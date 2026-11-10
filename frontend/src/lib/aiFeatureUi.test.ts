import { describe, expect, it } from "vitest";
import en from "@/i18n/en";
import ar from "@/i18n/ar";
import {
  filterOverlayPixels,
  formatTemplate,
  humanizeLabel,
  linePoints,
  positiveRateColor,
  readinessTone,
  recoveryTone,
  segmentationNotice,
} from "./aiFeatureUi";

describe("formatTemplate", () => {
  it("fills placeholders and leaves unknown ones", () => {
    expect(formatTemplate("{n} area(s) hidden; {x}", { n: 3 })).toBe("3 area(s) hidden; {x}");
  });
});

describe("filterOverlayPixels", () => {
  it("keeps only the selected class colors", () => {
    const red = [220, 38, 38];
    const orange = [230, 120, 30];
    const data = new Uint8ClampedArray([...red, 255, ...orange, 255, 0, 0, 0, 0]);
    filterOverlayPixels(data, [red]);
    expect(Array.from(data)).toEqual([...red, 255, ...orange, 0, 0, 0, 0, 0]);
  });
});

describe("status helpers", () => {
  it("never shows improvement colors for unmeasured states", () => {
    expect(recoveryTone("improving")).toBe("primary");
    expect(recoveryTone("worsening")).toBe("severe");
    expect(recoveryTone("inconclusive")).toBe("neutral");
    expect(recoveryTone("insufficient_data")).toBe("neutral");
  });

  it("maps segmentation states to messages", () => {
    expect(segmentationNotice(null)).toBe("older");
    expect(segmentationNotice("not_trained")).toBe("waiting");
    expect(segmentationNotice("dataset_unavailable")).toBe("waiting");
    expect(segmentationNotice("failed")).toBe("failed");
    expect(segmentationNotice("unavailable")).toBe("unavailable");
    expect(readinessTone("ready")).toBe("primary");
    expect(readinessTone("not_trained")).toBe("neutral");
  });

  it("uses grey for missing rates", () => {
    expect(positiveRateColor(null)).toBe("#9ca3af");
    expect(positiveRateColor(0.05)).not.toBe(positiveRateColor(0.7));
  });
});

describe("misc", () => {
  it("humanizes model labels", () => {
    expect(humanizeLabel("late_blight")).toBe("Late blight");
    expect(humanizeLabel(null)).toBe("");
  });

  it("maps values into the chart box", () => {
    expect(linePoints([0, 10], 100, 50, 0, 10)).toBe("0.0,50.0 100.0,0.0");
    expect(linePoints([], 100, 50)).toBe("");
  });
});

describe("translations", () => {
  const keysOf = (obj: unknown, prefix = ""): string[] =>
    typeof obj === "object" && obj !== null
      ? Object.entries(obj).flatMap(([k, v]) => keysOf(v, prefix ? `${prefix}.${k}` : k))
      : [prefix];

  it("Arabic has every English key for the new features", () => {
    for (const section of ["models", "localization", "gradcam", "quality", "track", "plants", "outbreak"] as const) {
      expect(keysOf(ar[section]).sort()).toEqual(keysOf(en[section]).sort());
    }
  });

  it("explains the privacy limitation the outbreak API adds when history is withheld", () => {
    // backend/app/application/services/outbreak_service.py, HISTORY_WITHHELD
    expect(en.outbreak.limitation.history_withheld_for_privacy).toMatch(/privacy/i);
    expect(ar.outbreak.limitation.history_withheld_for_privacy).toMatch(/[؀-ۿ]/);
  });

  it("keeps placeholders in translated templates", () => {
    expect(ar.outbreak.privacyNote).toContain("{res}");
    expect(ar.outbreak.privacyNote).toContain("{k}");
    expect(ar.outbreak.hiddenForPrivacy).toContain("{n}");
  });
});
