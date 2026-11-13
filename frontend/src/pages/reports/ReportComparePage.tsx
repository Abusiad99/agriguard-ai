import { Link, useSearchParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { useAsync } from "@/hooks/useAsync";
import { reportsApi } from "@/lib/endpoints/reports";
import { formatTemplate } from "@/lib/aiFeatureUi";
import { factDelta } from "@/lib/reportUi";
import { PageHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageLoader } from "@/components/ui/PageLoader";
import type { Report, ReportFact } from "@/types/reports";
import { apiErrorText } from "@/lib/apiErrorText";

function allFacts(report: Report): Record<string, ReportFact> {
  const out: Record<string, ReportFact> = {};
  for (const f of report.content.key_facts) out[f.key] = f;
  for (const s of report.content.sections) for (const f of s.facts) out[f.key] ??= f;
  return out;
}

/** Two reports side by side: each value as stored in its report, and the numeric change
 * only where both values exist with the same unit. */
export default function ReportComparePage() {
  const [params] = useSearchParams();
  const { t, locale } = useLocale();
  const c = t.reports.comparePage;
  const a = params.get("a");
  const b = params.get("b");
  const both = useAsync(() => Promise.all([reportsApi.get(a!), reportsApi.get(b!)]), [a, b]);

  if (!a || !b) return <ErrorState message={t.reports.selectTwo} />;
  if (both.status === "loading") return <PageLoader label={t.common.loading} />;
  if (both.status === "error") return <ErrorState message={apiErrorText(both.error, t, locale)} onRetry={both.refetch} />;

  const [ra, rb] = both.data;
  const fa = allFacts(ra);
  const fb = allFacts(rb);
  const keys = [...new Set([...Object.keys(fa), ...Object.keys(fb)])].filter((k) => !k.startsWith("meta."));
  const recA = new Set(ra.content.recommendations.map((r) => r.rule));
  const recB = new Set(rb.content.recommendations.map((r) => r.rule));
  const head = (r: Report) => (
    <Link to={`/reports/${r.id}`} className="font-medium text-primary hover:underline">
      <span dir="ltr" className="font-data">{r.reference}</span>
    </Link>
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title={c.title} />
      {ra.type !== rb.type && <p className="text-sm text-severity-mild">{c.differentTypes}</p>}
      <p className="text-sm text-muted">{ra.data_hash === rb.data_hash ? c.sameData : c.differentData}</p>
      <div className="glass overflow-x-auto rounded-panel p-4">
        <table className="w-full min-w-[36rem] text-sm">
          <thead>
            <tr className="border-b border-ink/10 text-xs text-muted">
              <th className="py-2 pe-3 text-start font-medium">{c.item}</th>
              <th className="py-2 pe-3 text-start font-medium">A · {head(ra)} <span className="block">{ra.generated_display}</span></th>
              <th className="py-2 pe-3 text-start font-medium">B · {head(rb)} <span className="block">{rb.generated_display}</span></th>
              <th className="py-2 text-start font-medium">{c.change}</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-ink/[0.06]">
              <td className="py-2 pe-3 text-muted">{c.statusRow}</td>
              <td className="py-2 pe-3 font-medium text-ink">{ra.content.status.label}</td>
              <td className="py-2 pe-3 font-medium text-ink">{rb.content.status.label}</td>
              <td className="py-2 text-muted">{ra.content.status.code === rb.content.status.code ? c.same : "≠"}</td>
            </tr>
            {keys.map((k) => {
              const x = fa[k];
              const y = fb[k];
              const delta = factDelta(x, y);
              return (
                <tr key={k} className="border-b border-ink/[0.06] align-top">
                  <td className="py-2 pe-3 text-muted">{(x ?? y)!.label}</td>
                  <td className={`py-2 pe-3 ${x?.available ? "text-ink" : "text-muted"}`}>{x ? x.display : formatTemplate(c.onlyIn, { which: "B" })}</td>
                  <td className={`py-2 pe-3 ${y?.available ? "text-ink" : "text-muted"}`}>{y ? y.display : formatTemplate(c.onlyIn, { which: "A" })}</td>
                  <td className="py-2 font-data text-ink">
                    {delta === 0 || (delta == null && x && y && x.display === y.display) ? c.same
                      : delta != null ? `${delta > 0 ? "+" : ""}${delta}${x?.unit ? ` ${x.unit}` : ""}` : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="glass rounded-panel p-4">
        <h2 className="mb-2 font-semibold text-ink">{c.recommendations}</h2>
        <ul className="grid gap-1 text-sm sm:grid-cols-2">
          {[...new Set([...recA, ...recB])].map((rule) => {
            const rec = ra.content.recommendations.find((r) => r.rule === rule) ?? rb.content.recommendations.find((r) => r.rule === rule)!;
            const where = recA.has(rule) && recB.has(rule) ? c.same : formatTemplate(c.onlyIn, { which: recA.has(rule) ? "A" : "B" });
            return <li key={rule} className="flex justify-between gap-3"><span className="text-ink">{rec.title}</span><span className="text-muted">{where}</span></li>;
          })}
        </ul>
      </div>
    </div>
  );
}
