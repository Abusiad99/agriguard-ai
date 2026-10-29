import { useState } from "react";
import type { DashboardResponse } from "@/types/api";
import { useLocale } from "@/context/LocaleContext";
import { labelDisplay } from "@/utils/labels";
import { Card, CardHeader, CardTitle, IconTile, type TileTone } from "@/components/ui/Card";
import { CountUp } from "@/components/ui/CountUp";
import { Icon, type IconName } from "@/components/ui/Icon";
import { ProgressRing } from "@/components/ui/ProgressRing";
import { ContourField } from "@/components/layout/AmbientBackground";
import { formatMonth } from "@/utils/format";

/** Shared overview used by the farmer dashboard and the admin system overview. */
export function DashboardOverview({ data }: { data: DashboardResponse }) {
  const { t } = useLocale();
  const total = Math.max(0, data.total_scans);

  return (
    <>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div className="col-span-2 sm:col-span-1">
          <StatTile icon="scan" tone="primary" label={t.dashboard.totalScans} value={data.total_scans} trend={data.monthly_trend.map((m) => m.scan_count)} />
        </div>
        <StatTile icon="bug" tone="severe" label={t.dashboard.diseased} value={data.diseased_count} share={total ? data.diseased_count / total : 0} />
        <StatTile icon="question" tone="moderate" label={t.dashboard.uncertain} value={data.uncertain_count ?? 0} share={total ? (data.uncertain_count ?? 0) / total : 0} />
      </div>

      <div className="grid gap-4 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <HealthCard confident={data.confident_count ?? 0} healthy={data.healthy_count} diseased={data.diseased_count}
            uncertain={data.uncertain_count ?? 0} total={total} />
        </div>
        <div className="lg:col-span-7">
          <TrendCard trend={data.monthly_trend} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-12">
        <div className={data.palm_disease_stats.total_palm_scans > 0 ? "lg:col-span-7" : "lg:col-span-12"}>
          <DiseaseRankingCard diseases={data.most_common_diseases} />
        </div>
        {data.palm_disease_stats.total_palm_scans > 0 && (
          <div className="lg:col-span-5">
            <PalmPanel palmScans={data.palm_disease_stats.total_palm_scans} weevil={data.palm_disease_stats.red_palm_weevil_incidents} />
          </div>
        )}
      </div>
    </>
  );
}

function StatTile({
  icon,
  tone,
  label,
  value,
  share,
  trend,
}: {
  icon: IconName;
  tone: TileTone;
  label: string;
  value: number;
  /** 0-1 share of all scans, drawn as a thin meter. */
  share?: number;
  /** Optional monthly series, drawn as a sparkline. */
  trend?: number[];
}) {
  const valueColor = tone === "severe" ? "text-severity-severe" : "text-ink";
  return (
    <Card className="flex h-full flex-col justify-between gap-5 !p-5">
      <div className="flex items-start justify-between gap-3">
        <IconTile name={icon} tone={tone} />
        {trend && trend.length > 1 && <Sparkline values={trend.slice(-8)} />}
        {share !== undefined && (
          <span className="font-data text-sm font-medium tabular-nums text-muted">
            <CountUp value={share * 100} suffix="%" />
          </span>
        )}
      </div>
      <div>
        <p className={`font-data text-[2.4rem] font-semibold leading-none tabular-nums ${valueColor}`}>
          <CountUp value={value} />
        </p>
        <p className="mt-2 text-sm text-muted">{label}</p>
        {share !== undefined && (
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-ink/[0.06]">
            <div
              className={`h-full origin-start animate-grow-x rounded-full [animation-delay:300ms] ${tone === "severe" ? "bg-severity-severe" : "bg-brand"}`}
              style={{ width: `${Math.round(share * 100)}%` }}
            />
          </div>
        )}
      </div>
    </Card>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const w = 96;
  const h = 36;
  const max = Math.max(1, ...values);
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - 3 - (v / max) * (h - 6)] as const);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join("");
  const area = `${line}L${w} ${h}L0 ${h}Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="flip-rtl h-9 w-24 overflow-visible" aria-hidden="true">
      <defs>
        <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" style={{ stopColor: "rgb(var(--c-primary))", stopOpacity: 0.3 }} />
          <stop offset="100%" style={{ stopColor: "rgb(var(--c-primary))", stopOpacity: 0 }} />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#spark-fill)" />
      <path
        d={line}
        fill="none"
        style={{ stroke: "rgb(var(--c-primary))" }}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength={1}
        strokeDasharray={1}
        className="animate-draw"
      />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="3" style={{ fill: "rgb(var(--c-primary))" }} />
    </svg>
  );
}

/** Share of scans whose model result was confident. (The current model has no
 * healthy class, so a "healthy rate" would always read 0% and mislead.) */
function HealthCard({ confident, healthy, diseased, uncertain, total }: {
  confident: number; healthy: number; diseased: number; uncertain: number; total: number;
}) {
  const { t } = useLocale();
  const rate = total ? (confident / total) * 100 : 0;
  const body = t.dashboard.healthRateBody.replace("{healthy}", String(confident)).replace("{total}", String(total));
  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle icon="heart">{t.dashboard.healthRate}</CardTitle>
      </CardHeader>
      <div className="flex flex-1 flex-col items-center gap-6 sm:flex-row lg:flex-col xl:flex-row">
        <ProgressRing value={rate} size={150} strokeWidth={12} />
        <div className="w-full flex-1">
          <p className="text-sm leading-relaxed text-muted">{body}</p>
          <dl className="mt-5 flex flex-col gap-3">
            {healthy > 0 && <LegendRow color="bg-primary" label={t.dashboard.healthy} value={healthy} />}
            <LegendRow color="bg-severity-severe" label={t.dashboard.diseased} value={diseased} />
            <LegendRow color="bg-severity-moderate" label={t.dashboard.uncertain} value={uncertain} />
          </dl>
        </div>
      </div>
    </Card>
  );
}

function LegendRow({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-ink/[0.03] px-3.5 py-2.5">
      <dt className="flex items-center gap-2.5 text-sm text-ink">
        <span className={`h-2.5 w-2.5 rounded-full ${color}`} />
        {label}
      </dt>
      <dd className="font-data text-sm font-semibold tabular-nums text-ink">{value}</dd>
    </div>
  );
}

function TrendCard({ trend }: { trend: DashboardResponse["monthly_trend"] }) {
  const { t, locale } = useLocale();
  const [hovered, setHovered] = useState<number | null>(null);
  const points = trend.slice(-8);
  const max = Math.max(1, ...points.map((m) => m.scan_count));
  // Round the axis to a friendly number so gridlines read 0 / ¼ / ½ / ¾ / max.
  const niceMax = Math.max(4, Math.ceil(max / 4) * 4);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle icon="chart">{t.dashboard.monthlyTrend}</CardTitle>
      </CardHeader>
      {points.length === 0 ? (
        <p className="text-sm text-muted">—</p>
      ) : (
        <div className="flex flex-1 gap-3">
          {/* Y axis */}
          <div className="relative h-52 w-7 shrink-0 font-data text-[11px] tabular-nums text-muted">
            {[niceMax, (niceMax * 3) / 4, niceMax / 2, niceMax / 4, 0].map((v, i) => (
              <span key={v} className="absolute end-0 -translate-y-1/2 leading-none" style={{ top: `${i * 25}%` }}>
                {v}
              </span>
            ))}
          </div>
          <div className="flex-1">
            <div className="relative h-52">
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} className="absolute inset-x-0 border-t border-dashed border-ink/[0.08]" style={{ top: `${i * 25}%` }} />
              ))}
              <div className="absolute inset-0 flex items-stretch gap-2 sm:gap-3">
                {points.map((m, i) => {
                  const pct = (m.scan_count / niceMax) * 100;
                  const isHovered = hovered === i;
                  const isLatest = i === points.length - 1;
                  return (
                    <div
                      key={m.month}
                      className="group relative flex flex-1 flex-col justify-end"
                      onMouseEnter={() => setHovered(i)}
                      onMouseLeave={() => setHovered(null)}
                      tabIndex={0}
                      onFocus={() => setHovered(i)}
                      onBlur={() => setHovered(null)}
                      aria-label={`${formatMonth(m.month, locale)}: ${m.scan_count}`}
                    >
                      <div
                        className={`relative w-full origin-bottom animate-grow-y rounded-t-lg transition-[filter,opacity] duration-300
                          ${isLatest ? "bg-brand shadow-glow" : "bg-primary/35 dark:bg-primary/40"}
                          ${hovered !== null && !isHovered ? "opacity-50" : "opacity-100"}`}
                        style={{ height: `${Math.max(3, pct)}%`, animationDelay: `${120 + i * 70}ms` }}
                      >
                        {(isHovered || (hovered === null && isLatest)) && (
                          <span className="absolute -top-9 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-ink px-2 py-1 font-data text-xs font-semibold text-canvas shadow-soft animate-scale-in">
                            {m.scan_count}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="mt-2.5 flex gap-2 sm:gap-3">
              {points.map((m, i) => (
                <span
                  key={m.month}
                  className={`flex-1 truncate text-center text-[11px] ${hovered === i ? "font-semibold text-ink" : "text-muted"}`}
                >
                  {formatMonth(m.month, locale, "short")}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function DiseaseRankingCard({ diseases }: { diseases: DashboardResponse["most_common_diseases"] }) {
  const { t } = useLocale();
  const top = diseases.slice(0, 6);
  const max = Math.max(1, ...top.map((d) => d.count));
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle icon="target">{t.dashboard.commonDiseases}</CardTitle>
      </CardHeader>
      {top.length === 0 ? (
        <p className="text-sm text-muted">—</p>
      ) : (
        <ol className="flex flex-col gap-4">
          {top.map((d, i) => (
            <li key={d.name} className="grid grid-cols-[1.75rem_1fr_auto] items-center gap-x-3 gap-y-1.5">
              <span
                className={`row-span-2 flex h-7 w-7 items-center justify-center rounded-lg font-data text-xs font-semibold
                  ${i === 0 ? "bg-brand text-white shadow-glow" : "bg-ink/[0.05] text-muted"}`}
              >
                {i + 1}
              </span>
              <span dir="auto" className="truncate text-sm font-medium text-ink">{d.name.includes("___") ? labelDisplay(d.name, t) : d.name}</span>
              <span className="font-data text-sm font-semibold tabular-nums text-ink">{d.count}</span>
              <div className="col-span-2 h-2 overflow-hidden rounded-full bg-ink/[0.06]">
                <div
                  className={`h-full origin-start animate-grow-x rounded-full ${i === 0 ? "bg-brand" : "bg-primary/45"}`}
                  style={{ width: `${(d.count / max) * 100}%`, animationDelay: `${200 + i * 80}ms` }}
                />
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

/** Date palms get their own panel: the Red Palm Weevil is the region's most
 * destructive palm pest, so incidents are surfaced on their own. */
function PalmPanel({ palmScans, weevil }: { palmScans: number; weevil: number }) {
  const { t } = useLocale();
  const share = palmScans ? Math.min(1, weevil / palmScans) : 0;
  return (
    <div className="relative h-full overflow-hidden rounded-panel bg-grove-deep p-6 text-white shadow-elevate">
      <div className="absolute inset-0 text-sprout/[0.14]" aria-hidden="true">
        <ContourField variant="hero" />
      </div>
      <div className="relative flex h-full flex-col gap-6">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/10 text-sprout ring-1 ring-inset ring-white/15">
            <Icon name="palm" className="h-6 w-6" />
          </span>
          <h3 className="font-display text-lg font-semibold">{t.dashboard.palmScans}</h3>
        </div>
        <p className="font-data text-5xl font-semibold leading-none tabular-nums">
          <CountUp value={palmScans} />
        </p>
        <div className="mt-auto rounded-2xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur-md">
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-sm text-white/80">
              <Icon name="bug" className="h-4 w-4 text-[#f5735e]" />
              {t.dashboard.weevilIncidents}
            </span>
            <span className="font-data text-xl font-semibold tabular-nums text-[#ff9a8a]">
              <CountUp value={weevil} />
            </span>
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full origin-start animate-grow-x rounded-full bg-gradient-to-r from-[#f5735e] to-[#e9b752] [animation-delay:400ms]"
              style={{ width: `${Math.max(2, share * 100)}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
