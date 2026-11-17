/**
 * Photos are made smaller in the browser before upload when they are large. Vercel, which hosts
 * the free public demo, rejects requests over 4.5 MB, and phone photos are often bigger. The
 * classifier looks at 224 px images, so a 2560 px photo loses nothing it uses.
 *
 * Photos up to UPLOAD_TARGET_BYTES, and anything the browser cannot decode, are sent unchanged.
 * Re-encoding also drops the photo's metadata (EXIF, including any GPS position); the image is
 * turned upright first, as the server would do.
 */
export const UPLOAD_TARGET_BYTES = 3_500_000;
export const MAX_UPLOAD_SIDE = 2560;

/** Width and height scaled down (never up) so that the longer side is at most `maxSide`. */
export function scaledSize(width: number, height: number, maxSide: number): { width: number; height: number } {
  const longer = Math.max(width, height);
  if (longer <= maxSide) return { width, height };
  const factor = maxSide / longer;
  return { width: Math.max(1, Math.round(width * factor)), height: Math.max(1, Math.round(height * factor)) };
}

function jpegName(name: string): string {
  const dot = name.lastIndexOf(".");
  return (dot > 0 ? name.slice(0, dot) : name || "photo") + ".jpg";
}

export async function shrinkForUpload(file: File): Promise<File> {
  if (file.size <= UPLOAD_TARGET_BYTES) return file;
  if (typeof createImageBitmap !== "function" || typeof document === "undefined") return file;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    try {
      let maxSide = MAX_UPLOAD_SIDE;
      let quality = 0.9;
      for (let attempt = 0; attempt < 4; attempt++) {
        const { width, height } = scaledSize(bitmap.width, bitmap.height, maxSide);
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext("2d");
        if (!context) return file;
        context.drawImage(bitmap, 0, 0, width, height);
        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
        if (blob && blob.size <= UPLOAD_TARGET_BYTES) {
          return new File([blob], jpegName(file.name), { type: "image/jpeg", lastModified: file.lastModified });
        }
        maxSide = Math.round(maxSide * 0.75);
        quality = Math.max(0.75, quality - 0.05);
      }
    } finally {
      bitmap.close();
    }
  } catch {
    // The browser could not decode the photo: send it as it is and let the server decide.
  }
  return file;
}
