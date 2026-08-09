import { useState } from "react";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { dashboardApi } from "@/lib/endpoints/dashboard";
import { adminApi } from "@/lib/endpoints/admin";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { formatMonth } from "@/utils/format";
import { ApiError } from "@/types/api";

export default function AdminDashboardPage() {
  const { t } = useLocale();
  const dashboard = useAsync(() => dashboardApi.getSystemDashboard(), []);
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExport = async () => {
    setExportError(null);
    setIsExporting(true);
    try {
      const blob = await adminApi.exportReportsCsv();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "agriguard-system-report.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : t.common.unknownError);
    } finally {
      setIsExporting(false);
    }
  };

  if (dashboard.status === "loading") return <PageLoader label={t.common.loading} />;
  if (dashboard.status === "error") {
    return <ErrorState message={errorMessage(dashboard.error)} onRetry={dashboard.refetch} />;
  }

  const data = dashboard.data;
  const maxTrend = Math.max(1, ...data.monthly_trend.map((m) => m.scan_count));
  const maxDisease = Math.max(1, ...data.most_common_diseases.map((d) => d.count));

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-2xl font-semibold text-ink">{t.admin.dashboardTitle}</h1>
        <Button variant="secondary" size="sm" isLoading={isExporting} onClick={() => void handleExport()}>
          {t.admin.exportReports}
        </Button>
      </div>
      {exportError && <Alert tone="error">{exportError}</Alert>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={t.dashboard.totalScans} value={data.total_scans} />
        <StatCard label={t.dashboard.healthy} value={data.healthy_count} tone="mild" />
        <StatCard label={t.dashboard.diseased} value={data.diseased_count} tone="severe" />
        <StatCard label={t.dashboard.weevilIncidents} value={data.palm_disease_stats.red_palm_weevil_incidents} tone="moderate" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t.dashboard.commonDiseases}</CardTitle>
          </CardHeader>
          {data.most_common_diseases.length === 0 ? (
            <p className="text-sm text-muted">—</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {data.most_common_diseases.slice(0, 8).map((d) => (
                <li key={d.name} className="flex items-center gap-3">
                  <span className="w-36 shrink-0 truncate text-sm text-ink">{d.name}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-line/50">
                    <div className="h-full rounded-full bg-primary" style={{ width: `${(d.count / maxDisease) * 100}%` }} />
                  </div>
                  <span className="font-data w-8 shrink-0 text-end text-sm text-muted">{d.count}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t.dashboard.monthlyTrend}</CardTitle>
          </CardHeader>
          {data.monthly_trend.length === 0 ? (
            <p className="text-sm text-muted">—</p>
          ) : (
            <div className="flex h-40 items-end gap-2">
              {data.monthly_trend.slice(-8).map((m) => (
                <div key={m.month} className="flex flex-1 flex-col items-center gap-1.5">
                  <div
                    className="w-full rounded-t bg-primary/80"
                    style={{ height: `${Math.max(4, (m.scan_count / maxTrend) * 100)}%` }}
                    title={`${m.scan_count} scans`}
                  />
                  <span className="text-[10px] text-muted">{formatMonth(m.month)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: number; tone?: "mild" | "moderate" | "severe" }) {
  const toneClass =
    tone === "mild" ? "text-severity-mild" : tone === "moderate" ? "text-severity-moderate" : tone === "severe" ? "text-severity-severe" : "text-primary";
  return (
    <Card className="p-4">
      <p className={`font-data text-3xl font-semibold ${toneClass}`}>{value}</p>
      <p className="mt-1 text-sm text-muted">{label}</p>
    </Card>
  );
}
