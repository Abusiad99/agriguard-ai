import { Badge } from "@/components/ui/Badge";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useLocale } from "@/context/LocaleContext";
import { formatDate } from "@/utils/format";
import {
  formatMeasurement, formatNumber, itemRefNumbers, localized, MEASUREMENT_ORDER, VERDICT_TONE, type UiLocale,
} from "@/lib/weatherGuidanceUi";
import type { WeatherGuidance, WeatherGuidanceItem, WeatherMeasurementKey } from "@/types/api";

const MEASUREMENT_ICON: Record<WeatherMeasurementKey, IconName> = {
  wind_speed_kmh: "wind", rain_probability_pct: "rain", temperature_c: "thermometer", humidity_pct: "droplet", uv_index: "sun",
};
const ITEM_ICON: Record<WeatherGuidanceItem["status"], { icon: IconName; className: string }> = {
  ok: { icon: "check", className: "bg-primary/10 text-primary" },
  caution: { icon: "warning", className: "bg-severity-moderate-bg text-severity-moderate" },
  unavailable: { icon: "info", className: "bg-ink/[0.06] text-muted" },
  info: { icon: "info", className: "bg-accent/15 text-accent-dark dark:text-accent" },
};

/**
 * Weather and spraying conditions for one diagnosis, exactly as the server assessed them
 * (backend/app/application/reporting/weather_guidance.py): the verdict, the measurements
 * with their state, each explanation with its basis, and the sources. No rule or threshold
 * is applied here.
 */
export function WeatherGuidancePanel({ guidance }: { guidance: WeatherGuidance }) {
  const { t, locale } = useLocale();
  const w = t.result.weatherGuidance;
  const loc: UiLocale = locale === "ar" ? "ar" : "en";
  const labelFor: Record<WeatherMeasurementKey, string> = {
    wind_speed_kmh: w.wind, rain_probability_pct: w.rain, temperature_c: w.temperature, humidity_pct: w.humidity, uv_index: w.uv,
  };
  const assessed = guidance.verdict !== "not_assessed" && guidance.verdict !== "not_applicable";

  return (
    <div className="flex flex-col gap-4" data-testid="weather-guidance" data-verdict={guidance.verdict}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={VERDICT_TONE[guidance.verdict]}>{w.verdicts[guidance.verdict]}</Badge>
        {/* Only when weather was recorded: "not assessed" has no measurement time to show. */}
        {assessed && (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted">
            <Icon name="calendar" className="h-3.5 w-3.5" />
            {w.measuredAt}: {guidance.observed_at ? formatDate(guidance.observed_at, loc) : w.timeUnknown}
          </span>
        )}
      </div>

      <p className="text-sm leading-relaxed text-ink">{localized(guidance.summary, loc)}</p>

      {guidance.verdict !== "not_applicable" && guidance.verdict !== "not_assessed" && (
        <dl className="grid grid-cols-2 gap-2.5">
          {MEASUREMENT_ORDER.map((key) => {
            const m = formatMeasurement(key, guidance.measurements[key], loc, w);
            return (
              <div key={key} className={`flex items-center gap-3 rounded-2xl px-3.5 py-3 ${m.state === "invalid" ? "bg-severity-moderate-bg/60" : "bg-ink/[0.035]"}`}
                   data-measurement={key} data-state={m.state}>
                <Icon name={MEASUREMENT_ICON[key]} className="h-5 w-5 shrink-0 text-primary" />
                <div className="min-w-0">
                  <dt className="break-words text-xs leading-snug text-muted">{labelFor[key]}</dt>
                  <dd className={`font-data text-sm tabular-nums ${m.state === "ok" ? "font-semibold text-ink" : "italic text-muted"}`}>{m.text}</dd>
                </div>
              </div>
            );
          })}
        </dl>
      )}

      {assessed && guidance.items.length > 0 && (
        <ul className="flex flex-col gap-2.5">
          {guidance.items.map((item) => {
            const look = ITEM_ICON[item.status];
            const ns = itemRefNumbers(item, guidance);
            return (
              <li key={item.code} className="flex gap-3 rounded-2xl border border-line/80 bg-surface/50 p-3.5 dark:bg-surface/30" data-item={item.code}>
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${look.className}`}>
                  <Icon name={look.icon} className="h-4 w-4" />
                </span>
                <div className="min-w-0 text-sm">
                  <p className="leading-relaxed text-ink">{localized(item.text, loc)}</p>
                  <p className="mt-1 text-xs text-muted">
                    {w.basis[item.basis]}
                    {ns.length > 0 && (
                      <span> {ns.map((n) => (
                        <a key={n} href={`#wx-ref-${n}`} className="font-semibold text-primary hover:underline">[{formatNumber(n, loc, 0)}]</a>
                      ))}</span>
                    )}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {guidance.references.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">{w.sources}</p>
          <ol className="flex flex-col gap-2 text-xs">
            {guidance.references.map((r) => (
              <li key={r.id} id={`wx-ref-${r.n}`} className="flex gap-2">
                <span className="font-data font-semibold text-primary-dark">[{formatNumber(r.n, loc, 0)}]</span>
                <div className="min-w-0">
                  <a dir="ltr" href={r.url} target="_blank" rel="noopener noreferrer" className="font-medium text-primary hover:underline">
                    {r.title}
                  </a>
                  <span className="sr-only"> {w.opensInNewTab}</span>
                  <span dir="ltr" className="block text-muted">
                    {[r.organization, r.publication_date].filter(Boolean).join(" · ")}
                  </span>
                  {(r.claims[loc] ?? r.claims.en ?? []).map((claim, i) => (
                    <span key={i} className="mt-0.5 block text-ink"><span className="text-muted">{w.citedFor}: </span>{claim}</span>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
