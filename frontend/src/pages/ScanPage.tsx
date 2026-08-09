import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Card } from "@/components/ui/Card";
import { ProgressRing } from "@/components/ui/ProgressRing";
import { scansApi } from "@/lib/endpoints/scans";
import { ApiError, isUnrecognizedPlant } from "@/types/api";
import { ALLOWED_IMAGE_TYPES, MAX_UPLOAD_SIZE_BYTES } from "@/utils/validators";

type Stage = "idle" | "preview" | "analyzing" | "unrecognized";

export default function ScanPage() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const [stage, setStage] = useState<Stage>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [attachLocation, setAttachLocation] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetToIdle = () => {
    setStage("idle");
    setFile(null);
    setPreviewUrl(null);
    setError(null);
  };

  const handleFileSelected = (selected: File | undefined) => {
    setError(null);
    if (!selected) return;

    if (!ALLOWED_IMAGE_TYPES.includes(selected.type)) {
      setError(t.scan.invalidImage);
      return;
    }
    if (selected.size > MAX_UPLOAD_SIZE_BYTES) {
      setError(t.scan.fileTooLarge);
      return;
    }

    setFile(selected);
    setPreviewUrl(URL.createObjectURL(selected));
    setStage("preview");
  };

  const getLocationIfNeeded = (): Promise<GeolocationPosition | null> => {
    if (!attachLocation || !navigator.geolocation) return Promise.resolve(null);
    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve(pos),
        () => resolve(null),
        { timeout: 5000 }
      );
    });
  };

  const handleSubmit = async () => {
    if (!file) return;
    setError(null);
    setStage("analyzing");

    try {
      const position = await getLocationIfNeeded();
      const result = await scansApi.createScan({
        image: file,
        latitude: position?.coords.latitude,
        longitude: position?.coords.longitude,
        attachLocation,
      });

      if (isUnrecognizedPlant(result)) {
        setStage("unrecognized");
        return;
      }

      navigate(`/diagnoses/${result.diagnosis_id}`, { replace: true });
    } catch (err) {
      setStage("preview");
      if (err instanceof ApiError) {
        if (err.code === "INVALID_IMAGE") setError(t.scan.invalidImage);
        else if (err.code === "FILE_TOO_LARGE") setError(t.scan.fileTooLarge);
        else setError(err.message);
      } else {
        setError(t.common.unknownError);
      }
    }
  };

  return (
    <div className="mx-auto max-w-xl animate-fade-in">
      <h1 className="font-display text-2xl font-semibold text-ink">{t.scan.title}</h1>
      <p className="mt-1.5 text-sm text-muted">{t.scan.subtitle}</p>

      <Card className="mt-6">
        {stage === "idle" && (
          <div className="flex flex-col items-center gap-4 py-6 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary-light text-primary">
              <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-sm text-muted">{t.scan.uploadPrompt}</p>

            {error && <Alert tone="error">{error}</Alert>}

            <div className="flex w-full flex-col gap-2.5 sm:flex-row">
              <Button variant="secondary" fullWidth onClick={() => cameraInputRef.current?.click()}>
                {t.scan.useCamera}
              </Button>
              <Button fullWidth onClick={() => fileInputRef.current?.click()}>
                {t.scan.chooseFile}
              </Button>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => handleFileSelected(e.target.files?.[0])}
            />
            <input
              ref={cameraInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => handleFileSelected(e.target.files?.[0])}
            />
          </div>
        )}

        {(stage === "preview" || stage === "analyzing") && previewUrl && (
          <div className="flex flex-col items-center gap-4">
            <div className="relative w-full overflow-hidden rounded-card">
              <img src={previewUrl} alt="Selected plant" className="max-h-80 w-full object-cover" />
              {stage === "analyzing" && (
                <div className="absolute inset-0 overflow-hidden bg-ink/30">
                  <div className="absolute inset-x-0 top-0 h-1/3 bg-gradient-to-b from-primary-light/70 to-transparent animate-scan-sweep" />
                </div>
              )}
            </div>

            {stage === "analyzing" ? (
              <div className="flex flex-col items-center gap-2 py-2 text-center">
                <ProgressRing value={70} size={72} strokeWidth={6} label="" valueLabel="" />
                <p className="font-display font-semibold text-ink">{t.scan.analyzing}</p>
                <p className="max-w-xs text-sm text-muted">{t.scan.analyzingBody}</p>
              </div>
            ) : (
              <>
                {error && <Alert tone="error">{error}</Alert>}
                <label className="flex items-center gap-2 self-start text-sm text-muted">
                  <input
                    type="checkbox"
                    checked={attachLocation}
                    onChange={(e) => setAttachLocation(e.target.checked)}
                    className="h-4 w-4 rounded border-line text-primary focus:ring-primary"
                  />
                  {t.scan.attachLocation}
                </label>
                <div className="flex w-full gap-2.5">
                  <Button variant="ghost" onClick={resetToIdle}>
                    {t.scan.retake}
                  </Button>
                  <Button fullWidth onClick={() => void handleSubmit()}>
                    {t.scan.submit}
                  </Button>
                </div>
              </>
            )}
          </div>
        )}

        {stage === "unrecognized" && (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-severity-moderate-bg text-severity-moderate">
              <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.803.394-1.451 1.088-1.451 1.996v.5m0 4.5h.008M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="font-display text-lg font-semibold text-ink">{t.scan.unrecognized}</p>
            <p className="max-w-xs text-sm text-muted">{t.scan.unrecognizedBody}</p>
            <Button className="mt-2" onClick={resetToIdle}>
              {t.scan.tryAgain}
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
