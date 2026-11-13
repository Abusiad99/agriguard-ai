import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync } from "@/hooks/useAsync";
import { plantsApi } from "@/lib/endpoints/aiFeatures";
import { recoveryTone } from "@/lib/aiFeatureUi";
import { PageHeader, Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Switch } from "@/components/ui/Switch";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageLoader } from "@/components/ui/PageLoader";
import { Pagination } from "@/components/ui/Pagination";
import { Icon } from "@/components/ui/Icon";
import { PlantForm } from "@/components/plants/PlantForm";
import { formatDate } from "@/utils/format";
import { apiErrorText } from "@/lib/apiErrorText";

const PAGE_SIZE = 12;

export default function PlantsPage() {
  const { t, locale } = useLocale();
  const navigate = useNavigate();
  const [showArchived, setShowArchived] = useState(false);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const plants = useAsync(
    () => plantsApi.list({ status: showArchived ? "archived" : "active", page, pageSize: PAGE_SIZE }),
    [showArchived, page],
  );
  const reminders = useAsync(() => plantsApi.myReminders("open"), []);
  const p = t.plants;

  return (
    <div className="flex flex-col gap-6 stagger">
      <PageHeader
        title={p.title}
        subtitle={p.subtitle}
        actions={<Button icon="plus" onClick={() => setCreating(true)}>{p.newPlant}</Button>}
      />

      {reminders.status === "success" && reminders.data.items.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle icon="calendar">{p.detail.followUps}</CardTitle>
          </CardHeader>
          <ul className="flex flex-col divide-y divide-ink/[0.06]">
            {reminders.data.items.slice(0, 6).map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                <Link to={`/plants/${r.tracked_plant_id}`} className="font-medium text-ink hover:text-primary">
                  {r.plant_name} · {p.reminders[r.kind]}
                </Link>
                <Badge tone={r.state === "overdue" ? "severe" : "neutral"}>
                  {r.state === "overdue" ? p.reminders.overdue : p.reminders.due} {r.due_on}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="flex justify-end">
        <Switch checked={showArchived} onChange={(v) => { setShowArchived(v); setPage(1); }} label={p.showArchived} />
      </div>

      {plants.status === "loading" ? (
        <PageLoader label={t.common.loading} />
      ) : plants.status === "error" ? (
        <ErrorState message={apiErrorText(plants.error, t, locale)} onRetry={plants.refetch} />
      ) : plants.data.items.length === 0 ? (
        <EmptyState iconName="sprout" title={p.emptyTitle} body={p.emptyBody}
                    action={<Button icon="plus" onClick={() => setCreating(true)}>{p.newPlant}</Button>} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {plants.data.items.map((plant) => (
              <Link key={plant.id} to={`/plants/${plant.id}`}
                    className="glass group flex flex-col gap-3 rounded-panel p-5 transition-transform duration-300 ease-spring hover:-translate-y-0.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-display text-lg font-semibold text-ink group-hover:text-primary">{plant.name}</p>
                    {(plant.crop || plant.species) && (
                      <p className="truncate text-sm text-muted">{[plant.crop, plant.species].filter(Boolean).join(" · ")}</p>
                    )}
                  </div>
                  {plant.status === "archived" ? (
                    <Badge tone="neutral">{p.archived}</Badge>
                  ) : (
                    <Badge tone={recoveryTone(plant.latest_status)}>{p.status[plant.latest_status ?? "insufficient_data"]}</Badge>
                  )}
                </div>
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <dt className="text-xs text-muted">{p.detail.scans}</dt>
                    <dd className="font-data font-semibold text-ink">{plant.scan_count}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">{p.lastScan}</dt>
                    <dd className="text-ink">{plant.last_scan_at ? formatDate(plant.last_scan_at, locale) : p.noScansYet}</dd>
                  </div>
                  {plant.next_reminder_on && (
                    <div className="col-span-2 flex items-center gap-1.5 text-muted">
                      <Icon name="calendar" className="h-4 w-4" />
                      {p.nextFollowUp}: <span className="text-ink">{plant.next_reminder_on}</span>
                    </div>
                  )}
                </dl>
              </Link>
            ))}
          </div>
          {plants.data.total > PAGE_SIZE && (
            <Pagination page={page} totalPages={Math.ceil(plants.data.total / PAGE_SIZE)} onChange={setPage} />
          )}
        </>
      )}

      <Modal isOpen={creating} onClose={() => setCreating(false)} title={p.newPlant}>
        <PlantForm
          onCancel={() => setCreating(false)}
          onSubmit={async (body) => {
            const created = await plantsApi.create(body);
            setCreating(false);
            navigate(`/plants/${created.id}`);
          }}
        />
      </Modal>
    </div>
  );
}
