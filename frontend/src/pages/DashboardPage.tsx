import { useAuth } from "@/context/AuthContext";
import { useLocale } from "@/context/LocaleContext";
import { useAsync, errorMessage } from "@/hooks/useAsync";
import { dashboardApi } from "@/lib/endpoints/dashboard";
import { PageHeader } from "@/components/ui/Card";
import { PageLoader } from "@/components/ui/PageLoader";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { ButtonLink } from "@/components/ui/Button";
import { DashboardOverview } from "@/components/dashboard/DashboardOverview";

export default function DashboardPage() {
  const { t } = useLocale();
  const { user } = useAuth();
  const dashboard = useAsync(() => dashboardApi.getMyDashboard(), []);

  if (dashboard.status === "loading") return <PageLoader label={t.common.loading} />;
  if (dashboard.status === "error") {
    return <ErrorState message={errorMessage(dashboard.error)} onRetry={dashboard.refetch} />;
  }

  const data = dashboard.data;
  const firstName = user?.full_name?.split(/\s+/)[0] ?? "";
  const scanButton = (
    <ButtonLink to="/scan" size="lg" icon="camera" className="hidden sm:inline-flex">
      {t.dashboard.scanNow}
    </ButtonLink>
  );

  if (data.total_scans === 0) {
    return (
      <div className="flex flex-col gap-8 stagger">
        <PageHeader title={t.dashboard.welcome.replace("{name}", firstName)} subtitle={t.dashboard.subtitle} />
        <EmptyState
          iconName="camera"
          title={t.dashboard.noScansYet}
          body={t.dashboard.noScansYetBody}
          action={
            <ButtonLink to="/scan" size="lg" icon="camera">
              {t.dashboard.scanNow}
            </ButtonLink>
          }
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 stagger sm:gap-6">
      <div className="mb-2">
        <PageHeader title={t.dashboard.welcome.replace("{name}", firstName)} subtitle={t.dashboard.subtitle} actions={scanButton} />
      </div>
      <DashboardOverview data={data} />
    </div>
  );
}
