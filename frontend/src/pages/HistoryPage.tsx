import { useState } from "react";
import { Link } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { scansApi } from "@/lib/endpoints/scans";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { DiagnosisCard } from "@/components/diagnosis/DiagnosisCard";

const PAGE_SIZE = 10;

export default function HistoryPage() {
  const { t } = useLocale();
  const [plant, setPlant] = useState("");
  const [disease, setDisease] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const history = useAsync(
    () =>
      scansApi.listDiagnoses({
        plant: plant || undefined,
        disease: disease || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    [plant, disease, dateFrom, dateTo, page]
  );

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-semibold text-ink">{t.history.title}</h1>
        <p className="mt-1 text-sm text-muted">{t.history.subtitle}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Input placeholder={t.history.searchPlant} value={plant} onChange={(e) => { setPlant(e.target.value); setPage(1); }} />
        <Input placeholder={t.history.searchDisease} value={disease} onChange={(e) => { setDisease(e.target.value); setPage(1); }} />
        <Input type="date" aria-label={t.history.dateFrom} value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} />
        <Input type="date" aria-label={t.history.dateTo} value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }} />
      </div>

      {history.status === "loading" && <PageLoader label={t.common.loading} />}
      {history.status === "error" && <ErrorState message={errorMessage(history.error)} onRetry={history.refetch} />}

      {history.status === "success" && history.data.items.length === 0 && (
        <EmptyState
          title={t.history.empty}
          body={t.history.emptyBody}
          action={
            <Link to="/scan">
              <Button>{t.dashboard.scanNow}</Button>
            </Link>
          }
        />
      )}

      {history.status === "success" && history.data.items.length > 0 && (
        <>
          <div className="flex flex-col gap-3">
            {history.data.items.map((item) => (
              <DiagnosisCard key={item.id} diagnosis={item} />
            ))}
          </div>

          {history.data.total_pages > 1 && (
            <div className="flex items-center justify-center gap-3">
              <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                {t.common.back}
              </Button>
              <span className="text-sm text-muted">
                {t.common.page} {history.data.page} {t.common.of} {history.data.total_pages}
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={page >= history.data.total_pages}
                onClick={() => setPage((p) => p + 1)}
              >
                {t.common.next}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
