import { useLocale } from "@/context/LocaleContext";
import { Icon } from "./Icon";

export function Pagination({ page, totalPages, onChange }: { page: number; totalPages: number; onChange: (page: number) => void }) {
  const { t } = useLocale();
  if (totalPages <= 1) return null;

  const btn =
    "inline-flex h-10 items-center gap-1.5 rounded-xl px-3.5 text-sm font-medium text-ink transition-all duration-300 ease-spring " +
    "hover:-translate-y-0.5 hover:bg-ink/[0.06] active:scale-95 disabled:pointer-events-none disabled:opacity-40";

  return (
    <nav className="glass mx-auto flex w-fit items-center gap-1 rounded-2xl p-1" aria-label="Pagination">
      <button type="button" className={btn} disabled={page <= 1} onClick={() => onChange(page - 1)}>
        <span className="flip-rtl inline-flex">
          <Icon name="chevronLeft" className="h-4 w-4" strokeWidth={2} />
        </span>
        {t.common.back}
      </button>
      <span className="px-3 text-sm text-muted">
        {t.common.page} <span className="font-data font-semibold tabular-nums text-ink">{page}</span> {t.common.of}{" "}
        <span className="font-data font-semibold tabular-nums text-ink">{totalPages}</span>
      </span>
      <button type="button" className={btn} disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        {t.common.next}
        <span className="flip-rtl inline-flex">
          <Icon name="chevronRight" className="h-4 w-4" strokeWidth={2} />
        </span>
      </button>
    </nav>
  );
}
