import { useEffect, useState } from "react";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { scansApi } from "@/lib/endpoints/scans";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type { DecisionStatus } from "@/types/api";
import { ButtonLink } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/Card";
import { Pagination } from "@/components/ui/Pagination";
import { DiagnosisCard } from "@/components/diagnosis/DiagnosisCard";

const PAGE_SIZE = 10;

export default function HistoryPage() {
  const { t } = useLocale();
  const [plant, setPlant] = useState("");
  const [disease, setDisease] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [status, setStatus] = useState<DecisionStatus | "">("");
  const [page, setPage] = useState(1);
  // Typing in the text filters waits for a short pause before querying.
  const plantQuery = useDebounced(plant);
  const diseaseQuery = useDebounced(disease);

  const history = useAsync(
    () =>
      scansApi.listDiagnoses({
        plant: plantQuery || undefined,
        disease: diseaseQuery || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        decision_status: status || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    [plantQuery, diseaseQuery, dateFrom, dateTo, status, page]
  );

  return (
    <div className="flex flex-col gap-6 stagger">
      <PageHeader
        title={t.history.title}
        subtitle={t.history.subtitle}
        actions={
          <ButtonLink to="/scan" icon="camera" className="hidden sm:inline-flex">
            {t.dashboard.scanNow}
          </ButtonLink>
        }
      />

      <div className="glass grid grid-cols-2 gap-3 rounded-panel p-3 sm:p-4 lg:grid-cols-5">
        <Input icon="leaf" placeholder={t.history.searchPlant} aria-label={t.history.searchPlant} value={plant} onChange={(e) => { setPlant(e.target.value); setPage(1); }} />
        <Input icon="bug" placeholder={t.history.searchDisease} aria-label={t.history.searchDisease} value={disease} onChange={(e) => { setDisease(e.target.value); setPage(1); }} />
        <DateField label={t.history.dateFrom} value={dateFrom} onChange={(v) => { setDateFrom(v); setPage(1); }} />
        <DateField label={t.history.dateTo} value={dateTo} onChange={(v) => { setDateTo(v); setPage(1); }} />
        <Select aria-label={t.history.statusFilter} value={status} onChange={(e) => { setStatus(e.target.value as DecisionStatus | ""); setPage(1); }}>
          <option value="">{t.history.allStatuses}</option>
          <option value="confident">{t.status.confident}</option>
          <option value="uncertain">{t.status.uncertain}</option>
          <option value="inconclusive">{t.status.inconclusive}</option>
          <option value="legacy">{t.status.legacy}</option>
        </Select>
      </div>

      <div>
        {history.status === "loading" && (
          <div className="flex flex-col gap-3" role="status" aria-label={t.common.loading}>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="glass flex items-center gap-4 rounded-[1.25rem] p-3">
                <div className="skeleton h-[4.5rem] w-[4.5rem] !rounded-2xl" />
                <div className="flex flex-1 flex-col gap-2.5">
                  <div className="skeleton h-4 w-1/3" />
                  <div className="skeleton h-3 w-1/2" />
                </div>
              </div>
            ))}
          </div>
        )}

        {history.status === "error" && <ErrorState message={errorMessage(history.error)} onRetry={history.refetch} />}

        {history.status === "success" && history.data.items.length === 0 && (
          <EmptyState
            iconName="search"
            title={t.history.empty}
            body={t.history.emptyBody}
            action={
              <ButtonLink to="/scan" size="lg" icon="camera">
                {t.dashboard.scanNow}
              </ButtonLink>
            }
          />
        )}

        {history.status === "success" && history.data.items.length > 0 && (
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-3 stagger">
              {history.data.items.map((item) => (
                <DiagnosisCard key={item.id} diagnosis={item} />
              ))}
            </div>
            <Pagination page={history.data.page} totalPages={history.data.total_pages} onChange={setPage} />
          </div>
        )}
      </div>
    </div>
  );
}

/** Date input with a floating caption, so "From"/"To" stay visible once a date is set. */
function DateField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="relative block">
      <span className="pointer-events-none absolute -top-2 start-3 z-[1] rounded-md bg-surface px-1.5 text-[11px] font-medium text-muted dark:bg-[rgb(var(--c-surface))]">
        {label}
      </span>
      <Input type="date" aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function useDebounced(value: string, delay = 350): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);
  return debounced;
}
