import { useParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync } from "@/hooks/useAsync";
import { reportsApi, saveBlob } from "@/lib/endpoints/reports";
import { formatTemplate } from "@/lib/aiFeatureUi";
import { ReportDocument } from "@/components/reports/ReportDocument";
import { Button } from "@/components/ui/Button";
import { LogoMark } from "@/components/ui/Logo";
import { PageLoader } from "@/components/ui/PageLoader";
import { formatDate } from "@/utils/format";

/** Public, read-only view of a shared report (no login). */
export default function SharedReportPage() {
  const { token } = useParams<{ token: string }>();
  const { t, locale } = useLocale();
  const report = useAsync(() => reportsApi.shared(token!), [token]);
  const s = t.reports.shared;

  return (
    <div className="min-h-screen px-4 py-6 sm:px-6">
      <div className="mx-auto flex max-w-5xl flex-col gap-5">
        <header className="flex flex-wrap items-center justify-between gap-3 print:hidden">
          <div className="flex items-center gap-2.5">
            <LogoMark className="h-9 w-9" />
            <div>
              <p className="font-display font-semibold text-ink">{s.title}</p>
              <p className="text-xs text-muted">{s.readOnly}</p>
            </div>
          </div>
          {report.status === "success" && (
            <div className="flex gap-2">
              <Button size="sm" icon="download"
                      onClick={() => void reportsApi.sharedPdf(token!).then((b) => saveBlob(b, `${report.data.reference}.pdf`))}>
                {t.reports.actions.pdf}
              </Button>
              <Button size="sm" variant="secondary" icon="document" onClick={() => window.print()}>{t.reports.actions.print}</Button>
            </div>
          )}
        </header>
        {report.status === "loading" && <PageLoader label={t.common.loading} />}
        {report.status === "error" && (
          <div className="glass rounded-panel p-8 text-center text-ink">{s.invalid}</div>
        )}
        {report.status === "success" && (
          <>
            {report.data.share_expires_at && (
              <p className="text-xs text-muted print:hidden">{formatTemplate(s.expires, { date: formatDate(report.data.share_expires_at, locale) })}</p>
            )}
            <ReportDocument report={report.data} mode="shared"
                            mapImage={report.data.content.map
                              ? () => void reportsApi.sharedMapImage(token!).then((b) => saveBlob(b, `${report.data.reference}-map.png`))
                              : undefined} />
          </>
        )}
      </div>
    </div>
  );
}
