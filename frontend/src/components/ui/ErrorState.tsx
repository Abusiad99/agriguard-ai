import { Button } from "./Button";

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center justify-center rounded-card border border-severity-severe/30 bg-severity-severe-bg px-6 py-12 text-center">
      <svg className="mb-3 h-9 w-9 text-severity-severe" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v3.75m0 3.75h.008v.008H12v-.008zM21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <p className="font-display text-lg font-semibold text-severity-severe">{message}</p>
      {onRetry && (
        <Button variant="danger" size="sm" className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
