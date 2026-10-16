import { ScanRing } from "./Spinner";

export function PageLoader({ label = "Loading…", fullScreen = false }: { label?: string; fullScreen?: boolean }) {
  return (
    <div className={`flex ${fullScreen ? "min-h-screen" : "min-h-[40vh]"} flex-col items-center justify-center gap-5 animate-fade-in`} role="status" aria-live="polite">
      <ScanRing size={68} />
      <p className="text-sm font-medium text-muted">{label}</p>
    </div>
  );
}
