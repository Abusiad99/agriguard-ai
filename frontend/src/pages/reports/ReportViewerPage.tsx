import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync } from "@/hooks/useAsync";
import { reportsApi, saveBlob } from "@/lib/endpoints/reports";
import { formatTemplate } from "@/lib/aiFeatureUi";
import { ReportDocument } from "@/components/reports/ReportDocument";
import { ShareDialog } from "@/components/reports/ShareDialog";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Icon } from "@/components/ui/Icon";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageLoader } from "@/components/ui/PageLoader";
import { ApiError } from "@/types/api";
import type { Report } from "@/types/reports";
import { apiErrorText } from "@/lib/apiErrorText";

export default function ReportViewerPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useLocale();
  const navigate = useNavigate();
  const report = useAsync(() => reportsApi.get(id!), [id]);
  const versions = useAsync(() => reportsApi.versions(id!), [id]);
  const [sharing, setSharing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useState<"en" | "ar">("en");
  const shown = useRef<Report | null>(null);
  if (report.status === "success") shown.current = report.data;
  const loadedId = report.status === "success" ? report.data.id : null;
  const loadedLocale = report.status === "success" ? report.data.locale : null;
  useEffect(() => {
    if (loadedLocale) setLang(loadedLocale);  // default the regenerate language once per loaded report
  }, [loadedId, loadedLocale]);

  const r = shown.current;
  if (report.status === "error" && !r) {
    const msg = report.error instanceof ApiError && report.error.status === 404 ? t.reports.loadError : apiErrorText(report.error, t, locale);
    return <ErrorState message={msg} onRetry={report.refetch} />;
  }
  if (!r) return <PageLoader label={t.common.loading} />;

  const act = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(apiErrorText(err, t, locale));
    } finally {
      setBusy(null);
    }
  };
  const a = t.reports.actions;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link to="/reports" className="group inline-flex items-center gap-2 text-sm font-medium text-muted hover:text-primary">
          <span className="flip-rtl inline-flex"><Icon name="arrowLeft" className="h-4 w-4" /></span>
          {a.back}
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" icon="download" isLoading={busy === "pdf"}
                  onClick={() => void act("pdf", async () => saveBlob(await reportsApi.pdf(r.id), `${r.reference}.pdf`))}>{a.pdf}</Button>
          <Button size="sm" variant="secondary" icon="document" onClick={() => window.print()}>{a.print}</Button>
          <Button size="sm" variant="secondary" icon="users" onClick={() => setSharing(true)}>{a.share}</Button>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2 rounded-2xl bg-ink/[0.035] p-3 print:hidden">
        <label className="flex flex-col gap-1 text-xs text-muted">
          {t.reports.language}
          <select value={lang} onChange={(e) => setLang(e.target.value as "en" | "ar")} aria-label={t.reports.language}
                  className="rounded-xl bg-surface px-2 py-1.5 text-sm text-ink ring-1 ring-inset ring-ink/15">
            <option value="en">{t.reports.english}</option>
            <option value="ar">{t.reports.arabic}</option>
          </select>
        </label>
        <Button size="sm" variant="ghost" icon="refresh" isLoading={busy === "regen"}
                onClick={() => void act("regen", async () => navigate(`/reports/${(await reportsApi.regenerate(r.id, lang)).id}`))}>
          {a.regenerate}
        </Button>
        {versions.status === "success" && versions.data.length > 1 && (
          <>
            <label className="flex flex-col gap-1 text-xs text-muted">
              {a.versions}
              <select value={r.id} onChange={(e) => navigate(`/reports/${e.target.value}`)} aria-label={a.versions}
                      className="rounded-xl bg-surface px-2 py-1.5 text-sm text-ink ring-1 ring-inset ring-ink/15">
                {versions.data.map((v) => (
                  <option key={v.id} value={v.id}>{formatTemplate(t.reports.versionN, { n: v.version })} · {v.locale.toUpperCase()}</option>
                ))}
              </select>
            </label>
            <Button size="sm" variant="ghost" icon="chart"
                    onClick={() => navigate(`/reports/compare?a=${versions.data.find((v) => v.id !== r.id)!.id}&b=${r.id}`)}>
              {a.compareVersions}
            </Button>
          </>
        )}
        <p className="basis-full text-xs text-muted">{a.regenerateHelp}</p>
      </div>
      {error && <Alert tone="error">{error}</Alert>}

      <ReportDocument report={r} mode="owner"
                      mapImage={r.content.map ? () => void act("map", async () => saveBlob(await reportsApi.mapImage(r.id), `${r.reference}-map.png`)) : undefined} />
      <ShareDialog reportId={r.id} isOpen={sharing} onClose={() => setSharing(false)} />
    </div>
  );
}
