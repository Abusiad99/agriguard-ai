import { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ReadinessBadge } from "@/components/ai/ReadinessBadge";
import { useLocale } from "@/context/LocaleContext";
import { scansApi } from "@/lib/endpoints/scans";
import { filterOverlayPixels, humanizeLabel, segmentationNotice } from "@/lib/aiFeatureUi";
import type { Segmentation } from "@/types/aiFeatures";

type View = "overlay" | "original" | "mask" | "contours";
type Artifacts = { overlay: string; mask: string; contours: string };

/** Load the owner-only segmentation PNGs as object URLs (revoked on unmount). */
function useArtifacts(segmentation: Segmentation | null | undefined) {
  const [urls, setUrls] = useState<Artifacts | null>(null);
  const [failed, setFailed] = useState(false);
  const artifacts = segmentation?.artifacts;
  useEffect(() => {
    if (!artifacts) return;
    let cancelled = false;
    const created: string[] = [];
    Promise.all((["overlay", "mask", "contours"] as const).map((k) => scansApi.getSegmentationArtifact(artifacts[k])))
      .then((blobs) => {
        if (cancelled) return;
        const [overlay, mask, contours] = blobs.map((b) => {
          const url = URL.createObjectURL(b);
          created.push(url);
          return url;
        });
        setUrls({ overlay, mask, contours });
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      created.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [artifacts]);
  return { urls, failed };
}

export function SegmentationPanel({ segmentation, originalUrl }: { segmentation?: Segmentation | null; originalUrl?: string | null }) {
  const { t } = useLocale();
  const ready = segmentation?.status === "ok";
  const { urls, failed } = useArtifacts(ready ? segmentation : null);
  const [view, setView] = useState<View>("overlay");
  const [opacity, setOpacity] = useState(65);
  const [zoom, setZoom] = useState(1);
  const diseaseClasses = useMemo(() => (segmentation?.classes ?? []).filter((c) => c.kind === "disease"), [segmentation]);
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Recolor the overlay client-side when classes are toggled (no extra requests).
  useEffect(() => {
    if (!urls || !canvasRef.current) return;
    const img = new Image();
    img.onload = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(img, 0, 0);
      if (hidden.size) {
        const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
        filterOverlayPixels(data.data, diseaseClasses.filter((c) => !hidden.has(c.id)).map((c) => c.color));
        ctx.putImageData(data, 0, 0);
      }
    };
    img.src = view === "contours" ? urls.contours : urls.overlay;
  }, [urls, hidden, diseaseClasses, view]);

  if (!ready) {
    const notice = segmentationNotice(segmentation?.status);
    return (
      <Card>
        <CardHeader>
          <CardTitle icon="target">{t.localization.title}</CardTitle>
          {segmentation && <ReadinessBadge readiness={segmentation.status} />}
        </CardHeader>
        <p className="text-sm leading-relaxed text-muted">{t.localization.notAvailable[notice]}</p>
      </Card>
    );
  }

  const s = segmentation!;
  const reason = s.area_unavailable_reason as keyof typeof t.localization.areaUnavailable | null | undefined;
  const views: View[] = ["overlay", "original", "mask", "contours"];

  return (
    <Card>
      <CardHeader>
        <CardTitle icon="target">{t.localization.title}</CardTitle>
        <ReadinessBadge readiness="ok" />
      </CardHeader>
      <p className="mb-4 text-sm leading-relaxed text-muted">{t.localization.explanation}</p>

      <div className="mb-3 flex flex-wrap items-center gap-2" role="group" aria-label={t.localization.title}>
        {views.map((v) => (
          <Button key={v} size="sm" variant={view === v ? "primary" : "secondary"} onClick={() => setView(v)} aria-pressed={view === v}>
            {t.localization.views[v]}
          </Button>
        ))}
        <span className="mx-1 h-6 w-px bg-ink/10" aria-hidden="true" />
        <Button size="sm" variant="ghost" icon="plus" onClick={() => setZoom((z) => Math.min(4, z * 2))} aria-label={t.localization.zoomIn} />
        <Button size="sm" variant="ghost" onClick={() => setZoom((z) => Math.max(1, z / 2))} aria-label={t.localization.zoomOut}>
          −
        </Button>
        {zoom > 1 && (
          <Button size="sm" variant="ghost" onClick={() => setZoom(1)}>
            {t.localization.zoomReset}
          </Button>
        )}
      </div>

      {(view === "overlay" || view === "contours") && (
        <label className="mb-3 flex items-center gap-3 text-sm text-muted">
          {t.localization.opacity}
          <input type="range" min={0} max={100} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))}
                 className="w-40 accent-[rgb(var(--c-primary))]" />
          <span className="font-data tabular-nums">{opacity}%</span>
        </label>
      )}

      {failed ? (
        <Alert tone="error">{t.localization.loadError}</Alert>
      ) : !urls ? (
        <div className="flex h-48 items-center justify-center"><Spinner /></div>
      ) : (
        <div className="max-h-[32rem] overflow-auto rounded-2xl bg-ink/[0.04] ring-1 ring-inset ring-ink/10">
          <div className="relative" style={{ width: `${zoom * 100}%` }}>
            {view === "mask" ? (
              <img src={urls.mask} alt={t.localization.views.mask} className="block w-full [image-rendering:pixelated]" />
            ) : (
              <>
                {originalUrl && <img src={originalUrl} alt={t.localization.views.original} className="block w-full" />}
                {view !== "original" && (
                  <canvas ref={canvasRef} aria-label={t.localization.views[view]}
                          className="absolute inset-0 h-full w-full [image-rendering:pixelated]"
                          style={{ opacity: opacity / 100 }} />
                )}
              </>
            )}
          </div>
        </div>
      )}

      {diseaseClasses.length > 0 && (
        <fieldset className="mt-4">
          <legend className="mb-2 text-sm font-semibold text-ink">{t.localization.legend}</legend>
          <div className="flex flex-wrap gap-3">
            {diseaseClasses.map((c) => (
              <label key={c.id} className="inline-flex cursor-pointer items-center gap-2 text-sm text-ink">
                <input type="checkbox" checked={!hidden.has(c.id)} onChange={() => setHidden((prev) => {
                  const next = new Set(prev);
                  if (next.has(c.id)) next.delete(c.id); else next.add(c.id);
                  return next;
                })} />
                <span className="inline-block h-3 w-3 rounded-sm ring-1 ring-ink/20" style={{ background: `rgb(${c.color.join(",")})` }} />
                {humanizeLabel(c.name)}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <dl className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl bg-ink/[0.035] p-4 sm:col-span-3">
          <dt className="text-xs text-muted">{t.localization.affectedArea}</dt>
          {s.affected_area_pct != null ? (
            <dd className="font-display text-2xl font-semibold text-ink">
              {s.affected_area_pct.toFixed(1)}% <span className="text-sm font-normal text-muted">{t.localization.ofPlantTissue}</span>
            </dd>
          ) : (
            <dd className="text-sm text-ink">{t.localization.areaUnavailable[reason ?? "generic"] ?? t.localization.areaUnavailable.generic}</dd>
          )}
        </div>
        {[
          [t.localization.affectedPixels, s.affected_pixels?.toLocaleString()],
          [t.localization.plantPixels, s.plant_pixels != null ? s.plant_pixels.toLocaleString() : "—"],
          [t.localization.meanConfidence, s.mean_confidence != null ? `${(s.mean_confidence * 100).toFixed(0)}%` : "—"],
          [t.localization.uncertainty, s.mean_uncertainty != null ? s.mean_uncertainty.toFixed(2) : "—"],
          [t.localization.model, s.model_version ?? "—"],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl bg-ink/[0.035] p-3">
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="truncate font-data text-sm font-semibold text-ink" title={String(value ?? "")}>{value ?? "—"}</dd>
          </div>
        ))}
      </dl>

      <h3 className="mb-2 mt-5 text-sm font-semibold text-ink">{t.localization.regions}</h3>
      {s.regions.length === 0 ? (
        <p className="text-sm text-muted">{t.localization.noRegions}</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-start text-xs text-muted">
              <th className="py-1 text-start font-medium">{t.localization.region}</th>
              <th className="py-1 text-end font-medium">{t.localization.size}</th>
              <th className="py-1 text-end font-medium">{t.localization.confidence}</th>
            </tr>
          </thead>
          <tbody>
            {s.regions.slice(0, 10).map((r, i) => (
              <tr key={i} className="border-t border-ink/[0.06]">
                <td className="py-1.5">{humanizeLabel(r.label)}</td>
                <td className="py-1.5 text-end font-data tabular-nums">{r.pixels.toLocaleString()}</td>
                <td className="py-1.5 text-end font-data tabular-nums">
                  {r.mean_confidence != null ? `${(r.mean_confidence * 100).toFixed(0)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
