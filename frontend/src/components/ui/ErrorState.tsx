import { useLocale } from "@/context/LocaleContext";
import { Button } from "./Button";
import { Icon } from "./Icon";

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useLocale();
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center rounded-panel border border-severity-severe/25 bg-severity-severe-bg/70 px-6 py-14 text-center backdrop-blur-sm animate-scale-in"
    >
      <span className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-severity-severe/10 text-severity-severe ring-1 ring-inset ring-severity-severe/20">
        <Icon name="error" className="h-7 w-7" />
      </span>
      <p className="max-w-md font-display text-lg font-semibold text-severity-severe">{message}</p>
      {onRetry && (
        <Button variant="danger" size="sm" icon="refresh" className="mt-5" onClick={onRetry}>
          {t.common.retry}
        </Button>
      )}
    </div>
  );
}
