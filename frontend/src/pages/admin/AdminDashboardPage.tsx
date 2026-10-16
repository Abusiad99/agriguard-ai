import { useState } from "react";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { dashboardApi } from "@/lib/endpoints/dashboard";
import { adminApi } from "@/lib/endpoints/admin";
import { PageHeader } from "@/components/ui/Card";
import { DashboardOverview } from "@/components/dashboard/DashboardOverview";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
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

  return (
    <div className="flex flex-col gap-5 stagger sm:gap-6">
      <div className="mb-2 flex flex-col gap-4">
        <PageHeader
          title={t.admin.dashboardTitle}
          actions={
            <Button variant="glass" icon="download" isLoading={isExporting} onClick={() => void handleExport()}>
              {t.admin.exportReports}
            </Button>
          }
        />
        {exportError && <Alert tone="error">{exportError}</Alert>}
      </div>
      <DashboardOverview data={data} />
    </div>
  );
}
