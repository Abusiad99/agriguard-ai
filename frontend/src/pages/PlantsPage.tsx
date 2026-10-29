import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { plantsApi } from "@/lib/endpoints/plants";
import { Card, PageHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Icon } from "@/components/ui/Icon";
import { Pagination } from "@/components/ui/Pagination";
import { Switch } from "@/components/ui/Switch";
import { StatusBadge } from "@/components/diagnosis/ReliabilityPanels";
import { PlantFormModal } from "@/components/plants/PlantFormModal";
import { formatDate } from "@/utils/format";
import { labelDisplay, plantName } from "@/utils/labels";

const PAGE_SIZE = 12;

export default function PlantsPage() {
  const { t, locale } = useLocale();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => setQuery(search), 350);
    return () => window.clearTimeout(id);
  }, [search]);

  const plants = useAsync(
    () => plantsApi.list({ search: query || undefined, include_archived: showArchived, page, page_size: PAGE_SIZE }),
    [query, showArchived, page]
  );

  return (
    <div className="flex flex-col gap-6 stagger">
      <PageHeader
        title={t.plants.title}
        subtitle={t.plants.subtitle}
        actions={
          <Button icon="plus" onClick={() => setCreating(true)}>
            {t.plants.add}
          </Button>
        }
      />

      <div className="glass flex flex-col gap-3 rounded-panel p-3 sm:flex-row sm:items-center sm:p-4">
        <div className="flex-1">
          <Input icon="search" placeholder={t.plants.search} aria-label={t.plants.search} value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        </div>
        <Switch checked={showArchived} onChange={(v) => { setShowArchived(v); setPage(1); }} label={t.plants.showArchived} />
      </div>

      {plants.status === "loading" && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" role="status" aria-label={t.common.loading}>
          {[0, 1, 2].map((i) => <div key={i} className="skeleton h-36 !rounded-panel" />)}
        </div>
      )}
      {plants.status === "error" && <ErrorState message={errorMessage(plants.error)} onRetry={plants.refetch} />}
      {plants.status === "success" && plants.data.items.length === 0 && (
        <EmptyState
          iconName="leaf"
          title={t.plants.empty}
          body={t.plants.emptyBody}
          action={<Button size="lg" icon="plus" onClick={() => setCreating(true)}>{t.plants.add}</Button>}
        />
      )}
      {plants.status === "success" && plants.data.items.length > 0 && (
        <div className="flex flex-col gap-6">
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">
            {plants.data.items.map((p) => (
              <li key={p.id}>
                <Link to={`/plants/${p.id}`} className="block h-full focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-panel">
                  <Card className="flex h-full flex-col gap-3 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-elevate">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p dir="auto" className="truncate text-start font-display text-lg font-semibold text-ink">{p.name}</p>
                        <p className="mt-0.5 text-sm text-muted">
                          {[p.crop_type ? plantName(p.crop_type, t) : null, p.variety].filter(Boolean).join(" · ") || "—"}
                        </p>
                      </div>
                      {p.archived ? (
                        <span className="rounded-full bg-ink/[0.06] px-2.5 py-1 text-xs text-muted">{t.plants.archived}</span>
                      ) : (
                        <Icon name="leaf" className="h-5 w-5 text-primary" />
                      )}
                    </div>
                    <div className="mt-auto flex flex-wrap items-center gap-2 text-sm text-muted">
                      <span className="font-data tabular-nums text-ink">{p.observation_count}</span> {t.plants.observations}
                      {p.last_decision_status && <StatusBadge status={p.last_decision_status} />}
                    </div>
                    <p className="text-xs text-muted">
                      {p.last_observed_at
                        ? `${t.plants.lastObserved}: ${formatDate(p.last_observed_at, locale)}`
                        : t.plants.neverObserved}
                      {p.last_predicted_label && p.last_decision_status !== "inconclusive" && (
                        <span dir="auto"> · {labelDisplay(p.last_predicted_label, t)}</span>
                      )}
                    </p>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
          <Pagination page={plants.data.page} totalPages={plants.data.total_pages} onChange={setPage} />
        </div>
      )}

      {creating && (
        <PlantFormModal
          onClose={() => setCreating(false)}
          onSaved={() => { setCreating(false); plants.refetch(); }}
        />
      )}
    </div>
  );
}
