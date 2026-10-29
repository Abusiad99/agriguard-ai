import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Card, PageHeader } from "@/components/ui/Card";
import { Icon, type IconName } from "@/components/ui/Icon";
import { ScanRing } from "@/components/ui/Spinner";
import { Switch } from "@/components/ui/Switch";
import { Input, Textarea } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { QualityIssueList } from "@/components/diagnosis/ReliabilityPanels";
import { useAsync } from "@/hooks/useAsync";
import { scansApi } from "@/lib/endpoints/scans";
import { plantsApi } from "@/lib/endpoints/plants";
import { ApiError, isQualityRejected, isUnrecognizedPlant, type ImageQuality } from "@/types/api";
import { ALLOWED_IMAGE_TYPES, MAX_UPLOAD_SIZE_BYTES } from "@/utils/validators";

type Stage = "idle" | "preview" | "analyzing" | "unrecognized" | "rejected";
type PlantMode = "none" | "existing" | "new";

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
  const [isDragging, setIsDragging] = useState(false);
  const [searchParams] = useSearchParams();
  const presetPlant = searchParams.get("plant");
  const [plantMode, setPlantMode] = useState<PlantMode>(presetPlant ? "existing" : "none");
  const [plantId, setPlantId] = useState<string>(presetPlant ?? "");
  const [newPlantName, setNewPlantName] = useState("");
  const [note, setNote] = useState("");
  const [rejection, setRejection] = useState<ImageQuality | null>(null);
  const plants = useAsync(() => plantsApi.list({ page_size: 100 }), []);

  const resetToIdle = () => {
    setStage("idle");
    setFile(null);
    setPreviewUrl(null);
    setError(null);
    setRejection(null);
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

  const onDragOver = (e: DragEvent) => {
    e.preventDefault();
    if (!isDragging) setIsDragging(true);
  };
  const onDragLeave = (e: DragEvent) => {
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
    setIsDragging(false);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileSelected(e.dataTransfer.files?.[0]);
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
        plantProfileId: plantMode === "existing" && plantId ? plantId : undefined,
        newPlantName: plantMode === "new" && newPlantName.trim() ? newPlantName.trim() : undefined,
        note: note.trim() || undefined,
      });

      if (isQualityRejected(result)) {
        setRejection(result.quality);
        setStage("rejected");
        return;
      }
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
        else if (err.code === "UNSUPPORTED_MEDIA_TYPE") setError(t.scan.unsupportedFormat);
        else setError(err.message);
      } else {
        setError(t.common.unknownError);
      }
    }
  };

  const tips: { icon: IconName; text: string }[] = [
    { icon: "scan", text: t.scan.tip1 },
    { icon: "sun", text: t.scan.tip2 },
    { icon: "target", text: t.scan.tip3 },
    { icon: "leaf", text: t.scan.tip4 },
  ];

  const canSubmit = plantMode !== "existing" || Boolean(plantId);

  return (
    <div className="flex flex-col gap-8 stagger">
      <PageHeader title={t.scan.title} subtitle={t.scan.subtitle} />

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-5 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <Card className="!p-3 sm:!p-4">
          {stage === "idle" && (
            <div
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              className={`relative flex min-h-[24rem] flex-col items-center justify-center gap-6 overflow-hidden rounded-[1.25rem] border-2 border-dashed px-6 py-10 text-center transition-all duration-300 sm:min-h-[28rem]
                ${isDragging ? "scale-[0.99] border-primary bg-primary/[0.07]" : "border-primary/20 bg-primary/[0.025]"}`}
            >
              <Viewfinder tight={isDragging} />

              <div className="relative flex h-24 w-24 items-center justify-center">
                <span className="absolute inset-0 animate-pulse-ring rounded-full bg-primary/15" />
                <span className="absolute inset-0 animate-pulse-ring rounded-full bg-primary/10 [animation-delay:1.2s]" />
                <span
                  className={`relative flex h-20 w-20 items-center justify-center rounded-full bg-brand text-white shadow-glow-lg transition-transform duration-500 ease-spring ${isDragging ? "scale-110" : ""}`}
                >
                  <Icon name={isDragging ? "download" : "upload"} className="h-9 w-9" />
                </span>
              </div>

              <div className="relative">
                <p className="font-display text-xl font-semibold text-ink">{isDragging ? t.scan.dropHere : t.scan.uploadPrompt}</p>
                <p className="mt-1.5 text-sm text-muted">{t.scan.formats}</p>
              </div>

              {error && (
                <div className="relative w-full max-w-md">
                  <Alert tone="error">{error}</Alert>
                </div>
              )}

              <div className="relative flex w-full max-w-md flex-col gap-3 sm:flex-row">
                <Button variant="glass" size="lg" fullWidth icon="camera" onClick={() => cameraInputRef.current?.click()}>
                  {t.scan.useCamera}
                </Button>
                <Button size="lg" fullWidth icon="photo" onClick={() => fileInputRef.current?.click()}>
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
            <div className="flex flex-col gap-4 animate-fade-in">
              <div className="relative overflow-hidden rounded-[1.25rem] bg-grove">
                <img
                  src={previewUrl}
                  alt="Selected plant"
                  className={`max-h-[28rem] w-full object-cover transition-all duration-700 ${stage === "analyzing" ? "scale-[1.03] brightness-[0.7] saturate-[1.15]" : ""}`}
                />
                {stage === "analyzing" && <AnalyzingOverlay />}
                {stage === "preview" && (
                  <Viewfinder className="text-white/80" />
                )}
              </div>

              {stage === "analyzing" ? (
                <div className="flex flex-col items-center gap-4 py-6 text-center animate-fade-in" role="status" aria-live="polite">
                  <ScanRing size={76} />
                  <div>
                    <p className="font-display text-lg font-semibold text-ink">{t.scan.analyzing}</p>
                    <p className="mx-auto mt-1.5 max-w-sm text-sm leading-relaxed text-muted">{t.scan.analyzingBody}</p>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-4 px-1 pb-1">
                  {error && <Alert tone="error">{error}</Alert>}
                  <fieldset className="flex flex-col gap-3 rounded-2xl border border-line/80 p-4">
                    <legend className="px-1 text-sm font-semibold text-ink">{t.scan.plantSection}</legend>
                    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t.scan.plantSection}>
                      {(["none", "existing", "new"] as PlantMode[]).map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          role="radio"
                          aria-checked={plantMode === mode}
                          onClick={() => setPlantMode(mode)}
                          className={`rounded-full px-3.5 py-1.5 text-sm ring-1 ring-inset transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary
                            ${plantMode === mode ? "bg-primary text-white ring-primary" : "bg-surface/60 text-ink ring-line hover:ring-primary/40"}`}
                        >
                          {mode === "none" ? t.scan.plantNone : mode === "existing" ? t.scan.plantExisting : t.scan.plantNew}
                        </button>
                      ))}
                    </div>
                    {plantMode === "existing" && (
                      <Select compact aria-label={t.scan.plantChoose} value={plantId} onChange={(e) => setPlantId(e.target.value)}>
                        <option value="">{t.scan.plantChoose}</option>
                        {plants.status === "success" &&
                          plants.data.items.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                      </Select>
                    )}
                    {plantMode === "new" && (
                      <Input
                        icon="leaf"
                        maxLength={100}
                        aria-label={t.scan.plantNewName}
                        placeholder={t.scan.plantNewName}
                        value={newPlantName}
                        onChange={(e) => setNewPlantName(e.target.value)}
                      />
                    )}
                  </fieldset>
                  <Textarea
                    rows={2}
                    maxLength={4000}
                    label={t.scan.noteLabel}
                    placeholder={t.scan.notePlaceholder}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                  <Switch
                    checked={attachLocation}
                    onChange={setAttachLocation}
                    label={t.scan.attachLocation}
                    icon={<Icon name="pin" className="h-5 w-5" />}
                  />
                  <div className="flex w-full flex-col-reverse gap-3 sm:flex-row">
                    <Button variant="glass" size="lg" icon="refresh" onClick={resetToIdle}>
                      {t.scan.retake}
                    </Button>
                    <Button size="lg" fullWidth icon="sparkles" disabled={!canSubmit} onClick={() => void handleSubmit()}>
                      {t.scan.submit}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {stage === "rejected" && rejection && (
            <div className="flex min-h-[22rem] flex-col items-center justify-center gap-4 px-6 py-10 text-center animate-scale-in">
              <span className="flex h-20 w-20 items-center justify-center rounded-3xl bg-severity-mild-bg text-severity-mild ring-1 ring-inset ring-severity-mild/20">
                <Icon name="photo" className="h-9 w-9" />
              </span>
              <p className="font-display text-xl font-semibold text-ink">{t.scan.qualityRejectedTitle}</p>
              <p className="max-w-md text-sm leading-relaxed text-muted">{t.scan.qualityRejectedBody}</p>
              <div className="w-full max-w-md rounded-2xl bg-ink/[0.035] p-4 text-start">
                <QualityIssueList quality={rejection} />
              </div>
              <Button size="lg" icon="camera" className="mt-2" onClick={resetToIdle}>
                {t.scan.tryAgain}
              </Button>
            </div>
          )}

          {stage === "unrecognized" && (
            <div className="flex min-h-[22rem] flex-col items-center justify-center gap-4 px-6 py-10 text-center animate-scale-in">
              <span className="flex h-20 w-20 items-center justify-center rounded-3xl bg-severity-moderate-bg text-severity-moderate ring-1 ring-inset ring-severity-moderate/20">
                <Icon name="search" className="h-9 w-9" />
              </span>
              <p className="font-display text-xl font-semibold text-ink">{t.scan.unrecognized}</p>
              <p className="max-w-sm text-sm leading-relaxed text-muted">{t.scan.unrecognizedBody}</p>
              <Button size="lg" icon="camera" className="mt-2" onClick={resetToIdle}>
                {t.scan.tryAgain}
              </Button>
            </div>
          )}
        </Card>

        <Card>
          <p className="mb-5 flex items-center gap-2.5 font-display text-base font-semibold text-ink">
            <Icon name="lightning" className="h-5 w-5 text-accent" />
            {t.scan.tipsTitle}
          </p>
          <ul className="flex flex-col gap-4">
            {tips.map((tip) => (
              <Tip key={tip.text} icon={tip.icon}>
                {tip.text}
              </Tip>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

function Tip({ icon, children }: { icon: IconName; children: ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Icon name={icon} className="h-[18px] w-[18px]" />
      </span>
      <span className="pt-2 text-sm leading-snug text-ink">{children}</span>
    </li>
  );
}

/** Camera-viewfinder corner brackets; they pull inward while a file is dragged over. */
function Viewfinder({ tight = false, className = "text-primary/50" }: { tight?: boolean; className?: string }) {
  const inset = tight ? "1.75rem" : "1rem";
  const corner = "absolute h-10 w-10 border-current transition-all duration-500 ease-spring";
  return (
    <div className={`pointer-events-none absolute inset-0 ${className}`} aria-hidden="true">
      <span className={`${corner} rounded-ss-2xl border-s-[3px] border-t-[3px]`} style={{ top: inset, insetInlineStart: inset }} />
      <span className={`${corner} rounded-se-2xl border-e-[3px] border-t-[3px]`} style={{ top: inset, insetInlineEnd: inset }} />
      <span className={`${corner} rounded-es-2xl border-b-[3px] border-s-[3px]`} style={{ bottom: inset, insetInlineStart: inset }} />
      <span className={`${corner} rounded-ee-2xl border-b-[3px] border-e-[3px]`} style={{ bottom: inset, insetInlineEnd: inset }} />
    </div>
  );
}

/** Scanner overlay while the AI works: measurement grid, a sweeping scan line and
 * glowing corner brackets over the photo. */
function AnalyzingOverlay() {
  return (
    <div className="pointer-events-none absolute inset-0 animate-fade-in" aria-hidden="true">
      <div
        className="absolute inset-0 opacity-30"
        style={{
          backgroundImage:
            "linear-gradient(rgb(166 240 138 / 0.35) 1px, transparent 1px), linear-gradient(90deg, rgb(166 240 138 / 0.35) 1px, transparent 1px)",
          backgroundSize: "36px 36px",
        }}
      />
      <div className="absolute inset-x-0 top-[6%] animate-scan-line">
        <div className="h-24 -translate-y-full bg-gradient-to-t from-sprout/30 to-transparent" />
        <div className="h-[2px] -translate-y-24 bg-[#b9f59c] shadow-[0_0_20px_5px_rgb(140_230_100/0.7)]" />
      </div>
      <div className="absolute inset-0 text-[#b9f59c] drop-shadow-[0_0_8px_rgb(140_230_100/0.8)]">
        <span className="absolute start-4 top-4 h-10 w-10 rounded-ss-2xl border-s-[3px] border-t-[3px] border-current" />
        <span className="absolute end-4 top-4 h-10 w-10 rounded-se-2xl border-e-[3px] border-t-[3px] border-current" />
        <span className="absolute bottom-4 start-4 h-10 w-10 rounded-es-2xl border-b-[3px] border-s-[3px] border-current" />
        <span className="absolute bottom-4 end-4 h-10 w-10 rounded-ee-2xl border-b-[3px] border-e-[3px] border-current" />
      </div>
    </div>
  );
}
