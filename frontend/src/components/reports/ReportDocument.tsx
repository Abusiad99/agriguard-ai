import { lazy, Suspense, useState, type ReactNode } from "react";
import { LogoMark } from "@/components/ui/Logo";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { ReportChartView } from "@/components/reports/ReportChartView";
import { featuresFor, groupByHorizon, localDigits, PROVENANCE_COLORS, refNumbers, reportDict, STATEMENT_COLORS } from "@/lib/reportUi";
import type {
  ProvenanceKind, Report, ReportFact, ReportItem, ReportMedia, ReportRecommendation, ReportReference, ReportSection,
  ReportStatement,
} from "@/types/reports";

const ReportRegionMap = lazy(() => import("@/components/reports/ReportRegionMap"));

const PRIORITY_STYLE: Record<string, string> = {
  high: "bg-severity-severe-bg text-severity-severe ring-severity-severe/25",
  medium: "bg-severity-mild-bg text-severity-mild ring-severity-mild/25",
  low: "bg-ink/[0.05] text-muted ring-ink/10",
};
const HORIZON_BAR: Record<string, string> = { immediate: "#b91c1c", short_term: "#b45309", long_term: "#2D6A4F" };

type Dict = ReturnType<typeof reportDict>;

function ProvChip({ kind, title, label }: { kind: ProvenanceKind; title?: string; label: string }) {
  const color = PROVENANCE_COLORS[kind] ?? "#6b7280";
  return (
    <span title={title} className="inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-medium ring-1 ring-inset"
          style={{ color, backgroundColor: `${color}12`, borderColor: color }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

/** Superscript citation numbers linking to the References chapter. */
function Refs({ refs, references, locale }: { refs?: string[]; references?: ReportReference[]; locale: "en" | "ar" }) {
  const ns = refNumbers(refs, references);
  if (!ns.length) return null;
  return (
    <sup className="ms-0.5 whitespace-nowrap text-[0.68em] font-semibold text-primary-dark">
      [{ns.map((n, i) => (
        <span key={n}>{i > 0 && (locale === "ar" ? "، " : ", ")}
          <a href={`#ref-${n}`} className="hover:underline">{localDigits(n, locale)}</a>
        </span>
      ))}]
    </sup>
  );
}

function Block({ title, children, className = "", warning = false }: { title?: string; children: ReactNode; className?: string; warning?: boolean }) {
  return (
    <section className={`glass break-inside-avoid rounded-panel p-5 sm:p-6 print:rounded-none print:border-0 print:bg-white print:p-0 print:py-3 print:shadow-none ${warning ? "ring-1 ring-severity-mild/40" : ""} ${className}`}>
      {title && <h3 className="mb-3 font-display text-lg font-semibold text-ink">{title}</h3>}
      {children}
    </section>
  );
}

function Value({ fact }: { fact: ReportFact }) {
  const text = fact.display || "—";
  if (fact.lang && fact.lang !== "ar") {
    return <span dir="ltr" lang={fact.lang} className="block text-start">{text}</span>;
  }
  return <span>{text}</span>;
}

function FactRow({ fact, prov, refs }: { fact: ReportFact; prov: (k: ProvenanceKind) => string; refs: (r?: string[]) => ReactNode }) {
  return (
    <div className="grid gap-1 border-b border-ink/[0.06] py-2.5 last:border-0 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)_auto] sm:gap-4">
      <dt className="text-sm font-medium text-muted">{fact.label}</dt>
      <dd className={`min-w-0 text-sm ${fact.available ? "text-ink" : "italic text-muted"}`}>
        <Value fact={fact} />{refs(fact.refs)}
        {fact.note && <span className="mt-0.5 block text-xs text-muted">{fact.note}</span>}
      </dd>
      <div><ProvChip kind={fact.provenance.kind} label={prov(fact.provenance.kind)}
                     title={[fact.provenance.source, fact.provenance.citation].filter(Boolean).join(" · ") || undefined} /></div>
    </div>
  );
}

function Statements({ items, d, refs }: { items: ReportStatement[]; d: Dict["doc"]; refs: (r?: string[]) => ReactNode }) {
  return (
    <ul className="mb-3 flex flex-col gap-2">
      {items.map((st, i) => {
        const color = STATEMENT_COLORS[st.kind] ?? "#475569";
        return (
          <li key={i} className="grid gap-1 rounded-xl bg-ink/[0.025] p-3 text-sm sm:grid-cols-[7.5rem_1fr] sm:gap-3">
            <span className="inline-flex h-fit w-fit items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  style={{ color, backgroundColor: `${color}14` }}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
              {d.statementKinds[st.kind] ?? st.kind}
            </span>
            <span className="text-ink">{st.text}{refs(st.refs)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Items({ items, refs }: { items: ReportItem[]; refs: (r?: string[]) => ReactNode }) {
  return (
    <ul className="flex flex-col gap-2">
      {items.map((it, i) => (
        <li key={i} className="flex gap-3 rounded-xl bg-ink/[0.025] p-3 text-sm">
          <span aria-hidden="true" className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${it.kind === "gap" ? "bg-severity-mild" : "bg-primary"}`} />
          <span className="min-w-0 flex-1 text-ink">
            {it.text}{refs(it.refs)}
            {it.when && <span className="ms-2 inline-block rounded-md bg-surface px-1.5 py-0.5 text-xs font-medium text-primary-dark ring-1 ring-ink/10">{it.when}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** v2 visual results: one panel per image, overlays composed on their photo, each explained. */
function VisualPanels({ media, ids, downloadLabel, refs }: {
  media: ReportMedia[]; ids: string[]; downloadLabel: string; refs: (r?: string[]) => ReactNode;
}) {
  const byId = Object.fromEntries(media.map((m) => [m.id, m]));
  const panels = ids.map((id) => byId[id]).filter((m): m is ReportMedia => !!m && !!m.url && m.kind !== "region_map");
  if (!panels.length) return null;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {panels.map((m) => {
        const base = m.overlay_of ? byId[m.overlay_of] : undefined;
        return (
          <figure key={m.id} className="break-inside-avoid">
            {m.title && <p className="mb-1.5 text-sm font-semibold text-ink">{m.title}</p>}
            <div className={`relative overflow-hidden rounded-2xl ring-1 ring-inset ring-ink/10 ${m.kind === "segmentation_mask" ? "bg-black" : "bg-ink/[0.04]"}`}>
              {base?.url ? (
                <>
                  <img src={base.url} alt={base.title ?? ""} className="block w-full" />
                  <img src={m.url!} alt={m.title ?? m.kind} className="absolute inset-0 h-full w-full opacity-75 [image-rendering:pixelated]" />
                </>
              ) : (
                <img src={m.url!} alt={m.title ?? m.kind} className={`block w-full ${m.kind === "segmentation_mask" ? "[image-rendering:pixelated]" : ""}`} />
              )}
            </div>
            <figcaption className="mt-1.5 text-xs text-muted">
              {m.caption && <span dir="auto" className="block font-medium text-ink/80">{m.caption}</span>}
              {m.explanation && <span className="mt-0.5 block">{m.explanation}{refs(m.refs)}</span>}
              <a href={m.url!} download className="mt-1 inline-block font-medium text-primary hover:underline print:hidden">{downloadLabel}</a>
            </figcaption>
          </figure>
        );
      })}
    </div>
  );
}

/** v1 gallery (photos with a segmentation overlay toggle). */
function MediaGallery({ media, ids, overlayLabel, downloadLabel }: {
  media: ReportMedia[]; ids: string[]; overlayLabel: string; downloadLabel: string;
}) {
  const [showOverlay, setShowOverlay] = useState(true);
  const byId = Object.fromEntries(media.map((m) => [m.id, m]));
  const items = ids.map((id) => byId[id]).filter((m): m is ReportMedia => !!m && !m.overlay_of && !!m.url);
  const overlays = media.filter((m) => m.overlay_of && m.kind === "segmentation_overlay" && m.url);
  if (!items.length) return null;
  return (
    <div>
      {overlays.length > 0 && (
        <label className="mb-3 inline-flex items-center gap-2 text-sm text-ink print:hidden">
          <input type="checkbox" checked={showOverlay} onChange={(e) => setShowOverlay(e.target.checked)} />
          {overlayLabel}
        </label>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {items.map((m) => {
          const overlay = overlays.find((o) => o.overlay_of === m.id);
          return (
            <figure key={m.id} className="break-inside-avoid">
              <div className="relative overflow-hidden rounded-2xl bg-ink/[0.04] ring-1 ring-inset ring-ink/10">
                <img src={m.url!} alt={m.caption ?? m.kind} className="block w-full" />
                {overlay && showOverlay && (
                  <img src={overlay.url!} alt="" className="absolute inset-0 h-full w-full opacity-70 [image-rendering:pixelated]" />
                )}
              </div>
              <figcaption className="mt-1.5 flex items-start justify-between gap-2 text-xs text-muted">
                <span>{m.caption}</span>
                <a href={m.url!} download className="shrink-0 font-medium text-primary hover:underline print:hidden">{downloadLabel}</a>
              </figcaption>
            </figure>
          );
        })}
      </div>
    </div>
  );
}

function Recommendation({ r, d, prov, note, refs }: {
  r: ReportRecommendation; d: Dict["doc"]; prov: (k: ProvenanceKind) => string; note?: string; refs: (r?: string[]) => ReactNode;
}) {
  return (
    <li className="break-inside-avoid rounded-2xl bg-ink/[0.03] p-4 ring-1 ring-inset ring-ink/[0.06]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h4 className="font-semibold text-ink">{r.title}</h4>
        <span className="flex flex-wrap gap-1.5">
          {r.horizon && <span className="rounded-full bg-surface px-2.5 py-0.5 text-xs font-medium text-ink ring-1 ring-inset ring-ink/10">{r.category_label}</span>}
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${PRIORITY_STYLE[r.priority]}`}>{r.priority_label}</span>
        </span>
      </div>
      {note && <p className="mt-1 text-sm text-ink">{note}</p>}
      <dl className="mt-2 grid gap-1.5 text-sm sm:grid-cols-[6rem_1fr]">
        <dt className="text-muted">{d.why}</dt><dd className="text-ink">{r.reason}</dd>
        <dt className="text-muted">{d.when}</dt><dd className="text-ink">{r.timing}</dd>
        <dt className="text-muted">{d.goal}</dt><dd className="text-ink">{r.objective}</dd>
        {r.evidence.length > 0 && (<>
          <dt className="text-muted">{d.evidence}</dt>
          <dd className="flex flex-wrap gap-1.5">
            {r.evidence.filter((e) => e.label).map((e, i) => (
              <span key={i} className="rounded-lg bg-surface px-2 py-0.5 text-xs text-ink ring-1 ring-ink/10">{e.label}: {e.display}</span>
            ))}
          </dd>
        </>)}
      </dl>
      {r.details?.text && (
        <div className="mt-3 rounded-xl bg-surface/80 p-3 text-sm ring-1 ring-ink/10">
          {r.details.verbatim_from_knowledge_base && <p className="mb-1 text-xs font-medium text-primary-dark">{d.fromKb}</p>}
          <p dir={r.details.lang && r.details.lang !== "ar" ? "ltr" : undefined} lang={r.details.lang} className="text-start text-ink">{r.details.text}</p>
          {r.details.citation && <p dir="ltr" className="mt-1 text-start text-xs text-muted">{r.details.citation}</p>}
        </div>
      )}
      {r.details?.items && r.details.items.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5 text-sm">
          {r.details.items.map((it, i) => (
            <li key={i} className="flex gap-2 text-ink"><span aria-hidden="true" className="text-primary">•</span><span>{it.text}{refs(it.refs)}</span></li>
          ))}
        </ul>
      )}
      {r.warnings.length > 0 && (
        <ul className="mt-3 list-disc space-y-0.5 ps-5 text-sm text-severity-mild">
          {r.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
        <ProvChip kind={r.provenance.kind} label={prov(r.provenance.kind)}
                  title={[r.provenance.source, r.provenance.citation].filter(Boolean).join(" · ") || undefined} />
        {r.basis_label && <span>{d.basis}: <span className="font-medium text-ink">{r.basis_label}</span>{refs(r.refs)}</span>}
        {r.general_practice && <span className="rounded-full bg-ink/[0.05] px-2 py-0.5">{d.generalPractice}</span>}
      </div>
    </li>
  );
}

function ReferenceList({ references, d, locale }: { references: ReportReference[]; d: Dict["doc"]; locale: "en" | "ar" }) {
  if (!references.length) return <p className="text-sm text-muted">{d.noReferences}</p>;
  return (
    <>
      <p className="mb-3 text-xs text-muted">{d.referencesNote}</p>
      <ol className="flex flex-col gap-3">
        {references.map((r) => (
          <li key={r.id} id={`ref-${r.n}`} className="scroll-mt-24 break-inside-avoid rounded-xl bg-ink/[0.025] p-3 text-sm">
            <div className="flex gap-3">
              <span className="font-data font-semibold text-primary-dark">[{localDigits(r.n, locale)}]</span>
              <div className="min-w-0 flex-1">
                <p dir="ltr" lang={r.language ?? "en"} className="text-start text-ink">
                  {r.authors && <span>{r.authors.replace(/[.\s]+$/, "")}. </span>}<span className="font-semibold">{r.title}</span>.
                  {r.organization && <span> {r.organization.replace(/[.\s]+$/, "")}.</span>}{r.publication_date && <span> {r.publication_date}.</span>}
                </p>
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                  <span className="rounded-full bg-surface px-2 py-0.5 ring-1 ring-ink/10">{r.source_type_label}</span>
                  <span>{r.origin === "catalog" ? d.fromCatalog : d.fromKbRef}</span>
                  {r.verified_on && <span>{d.checked}: <span dir="ltr">{r.verified_on}</span></span>}
                  <a dir="ltr" href={r.url} target="_blank" rel="noopener noreferrer" className="break-all font-medium text-primary hover:underline">{r.url}</a>
                  {r.doi && <span dir="ltr">doi:{r.doi}</span>}
                </p>
                <ul className="mt-2 flex flex-col gap-1 text-xs text-ink">
                  {r.claims.map((cl, i) => <li key={i}><span className="text-muted">{d.citedFor}: </span>{cl}</li>)}
                </ul>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}

/** A generated report as a document. `mode` "shared" hides owner-only details. */
export function ReportDocument({ report, mode, mapImage }: { report: Report; mode: "owner" | "shared"; mapImage?: () => void }) {
  const c = report.content;
  const locale = report.locale;
  const dict = reportDict(locale);
  const d = dict.doc;
  const dir = locale === "ar" ? "rtl" : "ltr";
  const prov = (k: ProvenanceKind) => (d.provenance as Record<string, string>)[k] ?? k;
  const refs = (r?: string[]) => <Refs refs={r} references={c.references} locale={locale} />;
  const charts = Object.fromEntries(c.charts.map((ch) => [ch.id, ch]));
  const notes = Object.fromEntries(c.narrative.recommendation_notes.map((n) => [n.recommendation_id, n.text]));
  const v2 = !!c.chapters?.length;
  const technical = c.sections.filter((s) => s.id === "technical").flatMap((s) => s.facts);

  const section = (s: ReportSection) => (
    <Block key={s.id} title={s.title} warning={s.warning}>
      {s.note && <p className="mb-3 text-xs text-muted">{s.note}</p>}
      {s.text && <p className="mb-3 text-sm leading-relaxed text-ink">{s.text}{refs(s.refs)}</p>}
      {s.statements && s.statements.length > 0 && <Statements items={s.statements} d={d} refs={refs} />}
      {s.facts.length > 0 && <dl>{s.facts.map((f) => <FactRow key={f.key} fact={f} prov={prov} refs={refs} />)}</dl>}
      {s.rows && s.rows.length > 0 && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[32rem] text-sm">
            <thead>
              <tr className="border-b border-ink/10 text-xs text-muted">
                {s.rows[0].cells.map((cell) => <th key={cell.key} className="py-2 pe-3 text-start font-medium">{cell.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {s.rows.map((row) => (
                <tr key={row.id} className="border-b border-ink/[0.06] align-top">
                  {row.cells.map((cell) => (
                    <td key={cell.key} className={`py-2 pe-3 ${cell.available ? "text-ink" : "text-muted"}`}
                        title={prov(cell.provenance.kind)}><Value fact={cell} /></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(s.chart_ids ?? []).map((id) => charts[id] && (
        <div key={id} className="mt-3">
          <p className="mb-1 text-sm font-medium text-ink">{charts[id].title}</p>
          <ReportChartView chart={charts[id]} exportLabel={dict.actions.exportChart} dir={dir} />
          <ProvChip kind={charts[id].provenance.kind} label={prov(charts[id].provenance.kind)} />
        </div>
      ))}
      {s.media_ids && s.media_ids.length > 0 && (
        <div className="mt-3">
          {v2 ? <VisualPanels media={c.media} ids={s.media_ids} downloadLabel={dict.actions.downloadImage} refs={refs} />
            : <MediaGallery media={c.media} ids={s.media_ids} overlayLabel={d.overlay} downloadLabel={dict.actions.downloadImage} />}
        </div>
      )}
      {s.map && c.map && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium text-muted">{d.interactiveMap}</p>
          <Suspense fallback={<div className="flex h-40 items-center justify-center"><Spinner /></div>}>
            <ReportRegionMap map={c.map} labels={{
              inspections: featuresFor(locale).outbreak.area.inspections,
              positives: featuresFor(locale).outbreak.area.positives,
              noEstimate: featuresFor(locale).outbreak.noPrediction,
              risk: (l) => (featuresFor(locale).outbreak.risk as Record<string, string>)[l] ?? l,
            }} />
          </Suspense>
          {c.media.find((m) => m.kind === "region_map")?.explanation && (
            <p className="mt-2 text-xs text-muted">{c.media.find((m) => m.kind === "region_map")!.explanation}</p>
          )}
          <p className="mt-2 text-xs text-muted">{d.predictionNotObservation}</p>
          {mapImage && <Button className="mt-2 print:hidden" size="sm" variant="ghost" icon="download" onClick={mapImage}>{dict.actions.exportMap}</Button>}
        </div>
      )}
      {s.items && s.items.length > 0 && <Items items={s.items} refs={refs} />}
      {s.events && s.events.length > 0 && (
        <ol className="relative mt-1 flex flex-col gap-2 border-s border-ink/10 ps-4">
          {s.events.map((e, i) => (
            <li key={i} className="text-sm">
              <span className="font-medium text-ink">{e.label ?? (d.events as Record<string, string>)[e.event] ?? e.event}</span>
              <span className="ms-2 text-xs text-muted">{e.display_date}</span>
            </li>
          ))}
        </ol>
      )}
      {s.hypotheses && s.hypotheses.length > 0 && (
        <ul className="mt-1 flex flex-col gap-2">
          {s.hypotheses.map((h, i) => (
            <li key={i} className="rounded-xl bg-severity-mild-bg/60 p-3 text-sm text-ink">
              <span className="mb-1 block text-xs font-semibold text-severity-mild">{d.hypothesis}</span>{h.text}
            </li>
          ))}
        </ul>
      )}
    </Block>
  );

  const narrativeNote = c.narrative.source === "llm" ? d.narrativeLlm
    : c.narrative.validation?.llm_attempted ? d.narrativeRejected : d.narrativeTemplate;

  const summary = (
    <>
      <Block title={v2 ? undefined : d.executiveSummary}>
        <div className="flex flex-col gap-2 text-[0.98rem] leading-relaxed text-ink">
          {c.narrative.executive_summary.map((s, i) => <p key={i}>{s.text}</p>)}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
          <ProvChip kind={c.narrative.source === "llm" ? "llm_summary" : "rule"} label={prov(c.narrative.source === "llm" ? "llm_summary" : "rule")} />
          <span>{narrativeNote}</span>
        </div>
      </Block>
      <Block title={d.keyFacts}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {c.key_facts.map((f) => (
            <div key={f.key} className="break-inside-avoid rounded-2xl bg-ink/[0.035] p-4">
              <p className="text-xs text-muted">{f.label}</p>
              <p className={`mt-1 font-display text-lg font-semibold ${f.available ? "text-ink" : "text-base italic text-muted"}`}><Value fact={f} />{refs(f.refs)}</p>
              {f.note && <p className="mt-1 text-xs text-muted">{f.note}</p>}
              <div className="mt-2"><ProvChip kind={f.provenance.kind} label={prov(f.provenance.kind)} title={f.provenance.source} /></div>
            </div>
          ))}
        </div>
      </Block>
    </>
  );

  const recommendations = v2 ? (
    <div className="flex flex-col gap-5">
      {groupByHorizon(c.recommendations).map((g) => (
        <Block key={g.horizon} title={g.label}>
          <span aria-hidden="true" className="-mt-2 mb-3 block h-1 w-12 rounded-full" style={{ backgroundColor: HORIZON_BAR[g.horizon] }} />
          <ul className="flex flex-col gap-3">
            {g.items.map((r) => <Recommendation key={r.id} r={r} d={d} prov={prov} note={notes[r.id]} refs={refs} />)}
          </ul>
        </Block>
      ))}
    </div>
  ) : (
    <Block title={d.recommendations} className="print:break-before-page">
      <div className="flex flex-col gap-5">
        {Object.entries(c.recommendations.reduce<Record<string, ReportRecommendation[]>>((acc, r) => {
          (acc[r.category] ||= []).push(r);
          return acc;
        }, {})).map(([cat, recs]) => (
          <div key={cat}>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-primary-dark">{recs[0].category_label}</h3>
            <ul className="flex flex-col gap-3">
              {recs.map((r) => <Recommendation key={r.id} r={r} d={d} prov={prov} note={notes[r.id]} refs={refs} />)}
            </ul>
          </div>
        ))}
      </div>
    </Block>
  );

  const limitations = (
    <>
      {v2 && c.missing && c.missing.length > 0 && (
        <Block title={d.missingInformation}>
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[minmax(0,14rem)_1fr]">
            {c.missing.map((m) => (
              <div key={m.key} className="contents">
                <dt className="font-medium text-muted">{m.label}</dt>
                <dd className="text-ink">{m.reason}</dd>
              </div>
            ))}
          </dl>
        </Block>
      )}
      <Block title={d.limitations}>
        <ul className="list-disc space-y-1 ps-5 text-sm text-ink">{c.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
      </Block>
    </>
  );

  const technicalBlock = (
    <Block title={d.technical}>
      {technical.length > 0 && <dl className="mb-3">{technical.map((f) => <FactRow key={f.key} fact={f} prov={prov} refs={refs} />)}</dl>}
      <h4 className="mb-2 mt-1 text-sm font-semibold text-ink">{d.methods}</h4>
      <ul className="mb-3 flex flex-col gap-1.5 text-sm">
        {c.methods.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink">{m.name}</span>
            <ProvChip kind={m.kind} label={prov(m.kind)} />
            {m.version && <span dir="ltr" className="font-data text-xs text-muted">{m.version}</span>}
          </li>
        ))}
      </ul>
      <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
        <dt className="text-muted">{d.dataHash}</dt><dd dir="ltr" className="break-all font-data text-ink">{report.data_hash}</dd>
        <dt className="text-muted">{d.generator}</dt><dd dir="ltr" className="font-data text-ink">{report.generator_version} · {report.schema_version}</dd>
      </dl>
      {mode === "owner" && report.sources && report.sources.length > 0 && (
        <>
          <h4 className="mb-1 mt-3 text-sm font-semibold text-ink">{d.sources}</h4>
          <ul dir="ltr" className="max-h-40 overflow-auto text-start font-data text-[11px] text-muted print:max-h-none">
            {report.sources.map((s, i) => <li key={i}>{s.kind}: {s.table}/{s.id}{s.version ? ` v${s.version}` : ""}</li>)}
          </ul>
        </>
      )}
    </Block>
  );

  return (
    <article dir={dir} lang={locale} className="report-doc flex flex-col gap-5 print:gap-2">
      {/* cover */}
      <Block className="relative overflow-hidden">
        <div className="pointer-events-none absolute -end-20 -top-20 h-64 w-64 rounded-full bg-primary/15 blur-3xl print:hidden" aria-hidden="true" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <LogoMark className="h-11 w-11" />
            <div>
              <p className="font-display text-sm font-semibold text-primary-dark">AgriGuard AI</p>
              <p className="text-xs text-muted">{dict.types[c.type]}</p>
            </div>
          </div>
          <dl className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 text-xs">
            <dt className="text-muted">{d.reference}</dt><dd dir="ltr" className="font-data text-ink">{report.reference}</dd>
            <dt className="text-muted">{d.version}</dt><dd className="font-data text-ink">{report.version}</dd>
            <dt className="text-muted">{d.generated}</dt><dd className="text-ink">{report.generated_display}</dd>
          </dl>
        </div>
        <h1 className="relative mt-5 text-balance font-display text-2xl font-semibold leading-tight text-ink sm:text-3xl">{c.title}</h1>
        <p className="relative mt-3 inline-flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-primary-light px-3 py-1 text-sm font-semibold text-primary-dark ring-1 ring-inset ring-primary/20">{c.status.label}</span>
          <ProvChip kind={c.status.provenance.kind} label={prov(c.status.provenance.kind)} />
        </p>
        {c.status.qualifier && <p className="relative mt-2 text-sm text-muted">{c.status.qualifier}</p>}
        {report.synthetic && (
          <p className="relative mt-4 rounded-xl bg-severity-mild-bg px-3 py-2 text-sm font-semibold text-severity-mild">{dict.synthetic}</p>
        )}
        <p className="relative mt-4 text-xs leading-relaxed text-muted">{d.disclaimer}</p>
        {v2 && (
          <nav className="relative mt-4 flex flex-wrap gap-1.5 print:hidden" aria-label={c.title}>
            {c.chapters!.map((ch, i) => (
              <a key={ch.id} href={`#ch-${ch.id}`} className="rounded-full bg-ink/[0.05] px-2.5 py-1 text-xs font-medium text-ink hover:bg-primary-light">
                {localDigits(i + 1, locale)}. {ch.title}
              </a>
            ))}
          </nav>
        )}
      </Block>

      {v2 ? c.chapters!.map((ch, i) => (
        <div key={ch.id} id={`ch-${ch.id}`} className="flex scroll-mt-20 flex-col gap-4">
          <h2 className="mt-2 flex items-center gap-3 font-display text-xl font-semibold text-ink print:mt-4">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm text-white">{localDigits(i + 1, locale)}</span>
            {ch.title}
          </h2>
          {ch.id === "summary" && summary}
          {c.sections.filter((s) => s.chapter === ch.id && s.id !== "technical").map(section)}
          {ch.id === "actions" && recommendations}
          {ch.id === "limitations" && limitations}
          {ch.id === "references" && (<>
            <Block title={d.references}><ReferenceList references={c.references ?? []} d={d} locale={locale} /></Block>
            {technicalBlock}
          </>)}
        </div>
      )) : (<>
        {summary}
        {c.sections.filter((s) => s.id !== "technical").map(section)}
        {recommendations}
        {limitations}
        {technicalBlock}
      </>)}
    </article>
  );
}
