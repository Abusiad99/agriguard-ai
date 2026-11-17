import { describe, expect, it } from "vitest";
import { MAX_UPLOAD_SIDE, UPLOAD_TARGET_BYTES, scaledSize, shrinkForUpload } from "@/lib/imageUpload";

describe("photo shrinking before upload", () => {
  it("scales the longer side down to the limit and keeps the aspect ratio", () => {
    expect(scaledSize(4032, 3024, MAX_UPLOAD_SIDE)).toEqual({ width: 2560, height: 1920 });
    expect(scaledSize(3024, 4032, MAX_UPLOAD_SIDE)).toEqual({ width: 1920, height: 2560 });
    expect(scaledSize(8000, 10, 2560)).toEqual({ width: 2560, height: 3 });
  });

  it("never enlarges a photo", () => {
    expect(scaledSize(1200, 800, MAX_UPLOAD_SIDE)).toEqual({ width: 1200, height: 800 });
    expect(scaledSize(2560, 2560, MAX_UPLOAD_SIDE)).toEqual({ width: 2560, height: 2560 });
  });

  it("stays well under Vercel's 4.5 MB request limit", () => {
    expect(UPLOAD_TARGET_BYTES).toBeLessThan(4_500_000 - 200_000); // room for the multipart form fields
  });

  it("sends small photos unchanged", async () => {
    const small = new File([new Uint8Array(1000)], "leaf.png", { type: "image/png" });
    expect(await shrinkForUpload(small)).toBe(small);
  });

  it("sends a large photo unchanged when the browser cannot decode images", async () => {
    // Vitest runs in Node: no createImageBitmap or canvas, like a browser that cannot decode the file.
    const large = new File([new Uint8Array(UPLOAD_TARGET_BYTES + 1)], "leaf.jpg", { type: "image/jpeg" });
    expect(await shrinkForUpload(large)).toBe(large);
  });
});
