import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync } from "@/hooks/useAsync";
import { reportsApi } from "@/lib/endpoints/reports";
import { formatTemplate } from "@/lib/aiFeatureUi";
import { PageHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageLoader } from "@/components/ui/PageLoader";
import { Pagination } from "@/components/ui/Pagination";
import { formatDate } from "@/utils/format";
import type { ReportType } from "@/types/reports";
import { apiErrorText } from "@/lib/apiErrorText";

const PAGE_SIZE = 12;

/** Archive of generated reports: search, filter by type and date, open, compare two. */
export default function ReportsPage() {
  const { t, locale } = useLocale();
  const navigate = useNavigate();
  const r = t.reports;
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [type, setType] = useState<ReportType | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const list = useAsync(() => reportsApi.list({ q: query || undefined, type: type || undefined, dateFrom: dateFrom || undefined,
                                                dateTo: dateTo || undefined, page, pageSize: PAGE_SIZE }),
                        [query, type, dateFrom, dateTo, page]);

  const toggle = (id: string) => setSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id)
    : [...prev.slice(-1), id]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={r.title} subtitle={r.subtitle}
                  actions={selected.length === 2 ? (
                    <Button icon="chart" onClick={() => navigate(`/reports/compare?a=${selected[0]}&b=${selected[1]}`)}>{r.compareSelected}</Button>
                  ) : undefined} />

      <form className="glass grid gap-3 rounded-panel p-4 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr]"
            onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); setPage(1); }}>
        <Input name="report-search" label={r.search} value={q} icon="search" maxLength={100} onChange={(e) => setQ(e.target.value)}
               onBlur={() => { setQuery(q.trim()); setPage(1); }} />
        <Select name="report-type" label={r.allTypes} value={type} onChange={(e) => { setType(e.target.value as ReportType | ""); setPage(1); }}>
          <option value="">{r.allTypes}</option>
          {(["diagnosis", "plant_progress", "outbreak_area"] as const).map((k) => <option key={k} value={k}>{r.types[k]}</option>)}
        </Select>
        <Input name="report-from" label={r.from} type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} />
        <Input name="report-to" label={r.to} type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }} />
      </form>

      {selected.length === 1 && <p className="text-sm text-muted">{r.selectTwo}</p>}

      {list.status === "loading" && <PageLoader label={t.common.loading} />}
      {list.status === "error" && <ErrorState message={apiErrorText(list.error, t, locale)} onRetry={list.refetch} />}
      {list.status === "success" && list.data.items.length === 0 && (
        <EmptyState iconName="document" title={r.emptyTitle} body={r.emptyBody} />
      )}
      {list.status === "success" && list.data.items.length > 0 && (
        <>
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {list.data.items.map((item) => (
              <li key={item.id} className={`glass flex flex-col gap-3 rounded-panel p-5 ring-2 transition ${selected.includes(item.id) ? "ring-primary" : "ring-transparent"}`}>
                <div className="flex items-start justify-between gap-2">
                  <Badge tone="primary">{r.types[item.type]}</Badge>
                  <label className="inline-flex items-center gap-1.5 text-xs text-muted">
                    <input type="checkbox" checked={selected.includes(item.id)} onChange={() => toggle(item.id)} />
                    {r.compare}
                  </label>
                </div>
                <Link to={`/reports/${item.id}`} dir={item.locale === "ar" ? "rtl" : "ltr"}
                      className="line-clamp-3 font-display text-base font-semibold text-ink hover:text-primary">{item.title}</Link>
                <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                  <span dir="ltr" className="font-data">{item.reference}</span>
                  <span>{formatTemplate(r.versionN, { n: item.version })}</span>
                  <span>{item.locale === "ar" ? r.arabic : r.english}</span>
                  {item.created_at && <span>{formatDate(item.created_at, locale)}</span>}
                </div>
                {item.synthetic && <p className="text-xs font-medium text-severity-mild">{r.synthetic}</p>}
              </li>
            ))}
          </ul>
          {list.data.total > PAGE_SIZE && (
            <Pagination page={page} totalPages={Math.ceil(list.data.total / PAGE_SIZE)} onChange={setPage} />
          )}
        </>
      )}
    </div>
  );
}
