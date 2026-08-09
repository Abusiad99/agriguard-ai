import { Spinner } from "./Spinner";

export function PageLoader({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3">
      <Spinner className="h-8 w-8 text-primary" />
      <p className="text-sm text-muted">{label}</p>
    </div>
  );
}
