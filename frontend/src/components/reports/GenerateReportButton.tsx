import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { useLocale } from "@/context/LocaleContext";
import { reportsApi, type ReportRequest } from "@/lib/endpoints/reports";
import { ApiError } from "@/types/api";

/** "Full report" entry point: picks the report language (defaults to the app's) and
 * opens the generated report. */
export function GenerateReportButton({ request, label, variant = "secondary", fullWidth }: {
  request: Omit<ReportRequest, "locale">;
  label?: string;
  variant?: "primary" | "secondary" | "ghost";
  fullWidth?: boolean;
}) {
  const { t, locale } = useLocale();
  const navigate = useNavigate();
  const [lang, setLang] = useState<"en" | "ar">(locale === "ar" ? "ar" : "en");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      const report = await reportsApi.create({ ...request, locale: lang });
      navigate(`/reports/${report.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.unknownError);
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-stretch gap-2">
        <select aria-label={t.reports.language} value={lang} onChange={(e) => setLang(e.target.value as "en" | "ar")}
                className="rounded-xl bg-surface px-2 text-sm text-ink ring-1 ring-inset ring-ink/15">
          <option value="en">{t.reports.english}</option>
          <option value="ar">{t.reports.arabic}</option>
        </select>
        <Button variant={variant} icon="document" isLoading={busy} fullWidth={fullWidth} onClick={() => void generate()}>
          {busy ? t.reports.generating : label ?? t.reports.generate}
        </Button>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
    </div>
  );
}
