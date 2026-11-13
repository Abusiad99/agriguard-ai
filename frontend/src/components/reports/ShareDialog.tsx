import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { useLocale } from "@/context/LocaleContext";
import { useAsync } from "@/hooks/useAsync";
import { formatTemplate } from "@/lib/aiFeatureUi";
import { reportsApi } from "@/lib/endpoints/reports";
import { formatDate } from "@/utils/format";
import { apiErrorText } from "@/lib/apiErrorText";

/** Create, copy and revoke expiring read-only links to a report. The full link is
 * only shown right after creation (the server keeps just a hash of it). */
export function ShareDialog({ reportId, isOpen, onClose }: { reportId: string; isOpen: boolean; onClose: () => void }) {
  const { t, locale } = useLocale();
  const s = t.reports.share;
  const [days, setDays] = useState(7);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const shares = useAsync(() => (isOpen ? reportsApi.shares(reportId) : Promise.resolve([])), [reportId, isOpen]);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const share = await reportsApi.share(reportId, days);
      setCreated(`${window.location.origin}${share.path}`);
      setCopied(false);
      shares.refetch();
    } catch (err) {
      setError(apiErrorText(err, t, locale));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (shareId: string) => {
    try {
      await reportsApi.revokeShare(reportId, shareId);
      shares.refetch();
    } catch (err) {
      setError(apiErrorText(err, t, locale));
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={s.title}>
      <div className="flex flex-col gap-4">
        <p className="text-sm leading-relaxed text-muted">{s.note}</p>
        {error && <Alert tone="error">{error}</Alert>}
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[10rem] flex-1">
            <Select name="share-expiry" label={s.expiresIn} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[1, 7, 30].map((n) => <option key={n} value={n}>{formatTemplate(s.days, { n })}</option>)}
            </Select>
          </div>
          <Button icon="plus" isLoading={busy} onClick={() => void create()}>{s.create}</Button>
        </div>
        {created && (
          <div className="flex flex-col gap-2 rounded-2xl bg-primary-light/60 p-3">
            <input readOnly value={created} dir="ltr" aria-label={s.copy}
                   className="w-full rounded-xl bg-surface px-3 py-2 font-data text-xs text-ink ring-1 ring-ink/10"
                   onFocus={(e) => e.currentTarget.select()} />
            <Button size="sm" variant="secondary" icon={copied ? "check" : "document"}
                    onClick={() => void navigator.clipboard?.writeText(created).then(() => setCopied(true))}>
              {copied ? s.copied : s.copy}
            </Button>
          </div>
        )}
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink">{s.existing}</h3>
          {shares.status === "success" && shares.data.length === 0 && <p className="text-sm text-muted">{s.none}</p>}
          {shares.status === "success" && shares.data.length > 0 && (
            <ul className="flex flex-col divide-y divide-ink/[0.06]">
              {shares.data.map((sh) => (
                <li key={sh.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                  <div className="flex flex-col">
                    <span className="text-ink">{formatTemplate(s.expires, { date: formatDate(sh.expires_at, locale) })}</span>
                    <span className="text-xs text-muted">{formatTemplate(s.views, { n: sh.access_count })}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={sh.state === "active" ? "primary" : "neutral"}>{s.states[sh.state]}</Badge>
                    {sh.state === "active" && <Button size="sm" variant="ghost" onClick={() => void revoke(sh.id)}>{s.revoke}</Button>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  );
}
