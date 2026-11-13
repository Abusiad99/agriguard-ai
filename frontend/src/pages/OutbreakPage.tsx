import { useMemo, useRef, useState } from "react";
import { useLocale } from "@/context/LocaleContext";
import { useAsync } from "@/hooks/useAsync";
import { outbreakApi } from "@/lib/endpoints/aiFeatures";
import { formatTemplate, humanizeLabel, POSITIVE_RATE_BANDS, RISK_COLORS } from "@/lib/aiFeatureUi";
import { Card, CardHeader, CardTitle, PageHeader } from "@/components/ui/Card";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Tabs } from "@/components/ui/Tabs";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageLoader } from "@/components/ui/PageLoader";
import { ReadinessBadge } from "@/components/ai/ReadinessBadge";
import { BarChart } from "@/components/charts/MiniCharts";
import { RiskMap, type MapLayerKind } from "@/components/outbreak/RiskMap";
import { GenerateReportButton } from "@/components/reports/GenerateReportButton";
import { formatDate } from "@/utils/format";
import type { GeoArea, MapCell, PredictionResult, PredictionSummary, RiskLevel } from "@/types/aiFeatures";
import { apiErrorText } from "@/lib/apiErrorText";

const WINDOWS = [30, 90, 365] as const;
const RISK_LEGEND: RiskLevel[] = ["low", "moderate", "high", "critical"];

/** A selected grid cell: from a map cell (has an area id) or a click on an empty spot. */
interface Selection {
  areaId: string | null;
  bounds: GeoArea["bounds"];
  center: { lat: number; lon: number };
}

/** "{n} days" — Arabic counts above ten take a different noun form. */
const daysLabel = (filters: { daysN: string; daysMany: string }, n: number) =>
  formatTemplate(n > 10 ? filters.daysMany : filters.daysN, { n });

const isoDaysAgo = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toLocaleDateString("en-CA");
};

export default function OutbreakPage() {
  const { t, locale } = useLocale();
  const o = t.outbreak;
  const readiness = useAsync(() => outbreakApi.readiness(), []);
  const filters = useAsync(() => outbreakApi.filters(), []);
  const [crop, setCrop] = useState("");
  const [disease, setDisease] = useState("");
  const [windowDays, setWindowDays] = useState<number>(90);
  const [horizon, setHorizon] = useState(7);
  const [layer, setLayer] = useState<MapLayerKind>("observed");
  const [selection, setSelection] = useState<Selection | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);

  const map = useAsync(
    () => outbreakApi.map({ crop: crop || undefined, disease: disease || undefined, dateFrom: isoDaysAgo(windowDays), horizonDays: horizon }),
    [crop, disease, windowDays, horizon],
  );
  // Keep drawing the previous cells while the layer reloads (e.g. after a new estimate),
  // so the map doesn't blank out and re-fit.
  const lastCells = useRef<MapCell[]>([]);
  if (map.status === "success") lastCells.current = map.data.cells;

  const filterData = filters.status === "success" ? filters.data : null;
  const crops = filterData?.crops ?? [];
  const diseases = useMemo(
    () => [...new Set((filterData?.pairs ?? []).filter((p) => !crop || p.crop === crop).map((p) => p.disease))],
    [filterData, crop],
  );
  const horizons = filterData?.horizons_days.length ? filterData.horizons_days : [7];

  const selectPoint = (lat: number, lon: number) => {
    setLookupError(null);
    outbreakApi
      .lookup(lat, lon)
      .then((r) => setSelection({ areaId: r.area_id, bounds: r.bounds, center: r.center }))
      .catch((err) => setLookupError(apiErrorText(err, t, locale)));
  };

  if (readiness.status === "error") return <ErrorState message={apiErrorText(readiness.error, t, locale)} onRetry={readiness.refetch} />;

  const privacy = readiness.status === "success" ? readiness.data.privacy : null;

  return (
    <div className="flex flex-col gap-5 stagger">
      <PageHeader
        title={o.title}
        subtitle={o.subtitle}
        actions={readiness.status === "success" ? <ReadinessBadge readiness={readiness.data.model.readiness} /> : undefined}
      />

      {readiness.status === "success" && !readiness.data.can_predict && <Alert tone="info">{o.modelNotReady}</Alert>}

      <Card className="!p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Select name="outbreak-crop" label={o.filters.crop} value={crop} onChange={(e) => { setCrop(e.target.value); setDisease(""); }}>
            <option value="">{o.filters.allCrops}</option>
            {crops.map((c) => <option key={c} value={c}>{humanizeLabel(c)}</option>)}
          </Select>
          <Select name="outbreak-disease" label={o.filters.disease} value={disease} onChange={(e) => setDisease(e.target.value)}>
            <option value="">{o.filters.allDiseases}</option>
            {diseases.map((d) => <option key={d} value={d}>{humanizeLabel(d)}</option>)}
          </Select>
          <Select name="outbreak-window" label={o.filters.window} value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value))}>
            {WINDOWS.map((w) => (
              <option key={w} value={w}>{w === 30 ? o.filters.days30 : w === 90 ? o.filters.days90 : o.filters.days365}</option>
            ))}
          </Select>
          <Select name="outbreak-horizon" label={o.filters.horizon} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
            {horizons.map((h) => <option key={h} value={h}>{daysLabel(o.filters, h)}</option>)}
          </Select>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div className="w-fit" aria-label={o.filters.layer}>
            <Tabs tabs={[{ key: "observed", label: o.filters.observed }, { key: "predicted", label: o.filters.predicted }]}
                  active={layer} onChange={(k) => setLayer(k as MapLayerKind)} />
          </div>
          <p className="text-xs text-muted">{o.clickHint}</p>
        </div>
      </Card>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="flex flex-col gap-3">
          <div className="relative isolate overflow-hidden rounded-2xl ring-1 ring-ink/10">
            <RiskMap
              cells={lastCells.current}
              layer={layer}
              selectedBounds={selection?.bounds}
              onSelectCell={(cell) => setSelection({ areaId: cell.area.id, bounds: cell.area.bounds, center: cell.area.center })}
              onSelectPoint={selectPoint}
              labels={{
                map: o.title,
                inspections: o.area.inspections,
                positives: o.area.positives,
                noPrediction: o.noPrediction,
                risk: (level) => o.risk[level as RiskLevel] ?? level,
              }}
            />
          </div>

          <MapLegend layer={layer} />

          {map.status === "error" && <Alert tone="error">{apiErrorText(map.error, t, locale)}</Alert>}
          {lookupError && <Alert tone="error">{lookupError}</Alert>}
          {map.status === "success" && map.data.cells.length === 0 && (
            <Alert tone="info" title={o.emptyTitle}>{o.emptyBody}</Alert>
          )}
          {map.status === "success" && map.data.hidden_for_privacy > 0 && (
            <p className="text-xs text-muted">{formatTemplate(o.hiddenForPrivacy, { n: map.data.hidden_for_privacy })}</p>
          )}
          {privacy && (
            <p className="text-xs leading-relaxed text-muted">
              {formatTemplate(o.privacyNote, { res: privacy.grid_resolution_deg, k: privacy.min_contributors })}
            </p>
          )}
        </div>

        {selection ? (
          <AreaPanel key={`${selection.areaId ?? selection.center.lat + "," + selection.center.lon}-${crop}-${disease}-${windowDays}`}
                     selection={selection} crop={crop} disease={disease} dateFrom={isoDaysAgo(windowDays)} horizon={horizon}
                     onPredicted={map.refetch} onClose={() => setSelection(null)} />
        ) : (
          <Card>
            <p className="text-sm text-muted">{o.clickHint}</p>
          </Card>
        )}
      </div>
    </div>
  );
}

function MapLegend({ layer }: { layer: MapLayerKind }) {
  const { t } = useLocale();
  const o = t.outbreak;
  const items = layer === "observed"
    ? POSITIVE_RATE_BANDS.map((b) => ({ label: b.label, color: b.color }))
    : [...RISK_LEGEND.map((r) => ({ label: o.risk[r], color: RISK_COLORS[r] })), { label: o.noPrediction, color: RISK_COLORS.unavailable }];
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted" aria-label={o.legend}>
      <span className="font-semibold text-ink">{layer === "observed" ? o.positiveRate : o.filters.predicted}:</span>
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-sm" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

function AreaPanel({ selection, crop, disease, dateFrom, horizon, onPredicted, onClose }: {
  selection: Selection;
  crop: string;
  disease: string;
  /** Same observation window as the map, so the panel matches the clicked cell. */
  dateFrom: string;
  horizon: number;
  onPredicted: () => void;
  onClose: () => void;
}) {
  const { t, locale } = useLocale();
  const a = t.outbreak.area;
  const detail = useAsync(
    () => (selection.areaId ? outbreakApi.area(selection.areaId, crop || undefined, disease || undefined, dateFrom) : Promise.resolve(null)),
    [selection.areaId, crop, disease, dateFrom],
  );
  const [estimating, setEstimating] = useState(false);
  const [estimate, setEstimate] = useState<PredictionResult | null>(null);
  const [estimateError, setEstimateError] = useState<string | null>(null);

  const runEstimate = async () => {
    setEstimating(true);
    setEstimateError(null);
    try {
      const res = await outbreakApi.predict({
        crop, disease, horizon_days: horizon,
        ...(selection.areaId ? { area_id: selection.areaId } : { latitude: selection.center.lat, longitude: selection.center.lon }),
      });
      setEstimate(res);
      if (res.persisted) onPredicted();
      if (selection.areaId) detail.refetch();
    } catch (err) {
      setEstimateError(apiErrorText(err, t, locale));
    } finally {
      setEstimating(false);
    }
  };

  const data = detail.status === "success" ? detail.data : null;
  const s = data?.summary;

  return (
    <Card className="flex flex-col gap-4">
      <CardHeader className="!mb-0">
        <CardTitle icon="pin">{a.title}</CardTitle>
        <Button size="sm" variant="ghost" icon="close" aria-label={a.close} onClick={onClose} />
      </CardHeader>
      <p className="font-data text-xs text-muted">
        {selection.bounds.south.toFixed(2)}…{selection.bounds.north.toFixed(2)}°, {selection.bounds.west.toFixed(2)}…{selection.bounds.east.toFixed(2)}°
      </p>

      {detail.status === "loading" && <PageLoader label={t.common.loading} />}
      {detail.status === "error" && <Alert tone="error">{apiErrorText(detail.error, t, locale)}</Alert>}

      {detail.status === "success" && (!s || s.inspections === 0) && <p className="text-sm text-muted">{a.noObservations}</p>}

      {s && s.inspections > 0 && (
        <dl className="grid grid-cols-2 gap-2">
          {[
            [a.inspections, String(s.inspections)],
            [a.positives, String(s.positives)],
            [a.positiveRate, s.positive_rate != null ? `${(s.positive_rate * 100).toFixed(0)}%` : "—"],
            [a.latest, s.latest_observation ? formatDate(s.latest_observation, locale) : "—"],
          ].map(([k, v]) => (
            <div key={k} className="rounded-2xl bg-ink/[0.035] p-3">
              <dt className="text-xs text-muted">{k}</dt>
              <dd className="font-data text-sm font-semibold text-ink">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {s?.app_counts_suppressed && <p className="text-xs text-muted">{a.suppressed}</p>}

      {data && data.trend.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-ink">{a.trend}</h3>
          <BarChart ariaLabel={a.trend}
                    bars={data.trend.map((w) => ({ label: w.week_start, total: w.inspections, highlighted: w.positives }))} />
        </section>
      )}

      {data && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-ink">{a.weather}</h3>
          {data.weather.days.length === 0 ? (
            <p className="text-xs text-muted">{a.weatherEmpty}</p>
          ) : (
            <div className="max-h-56 overflow-auto">
              <table className="w-full text-xs">
                <thead className="text-muted">
                  <tr>
                    <th className="py-1 text-start font-medium" />
                    <th className="py-1 text-end font-medium">{a.temp}</th>
                    <th className="py-1 text-end font-medium">{a.rh}</th>
                    <th className="py-1 text-end font-medium">{a.rh90}</th>
                    <th className="py-1 text-end font-medium">{a.rain}</th>
                  </tr>
                </thead>
                <tbody className="font-data tabular-nums">
                  {data.weather.days.slice(-14).map((w) => (
                    <tr key={`${w.day}-${w.kind}`} className="border-t border-ink/[0.06]">
                      <td className="py-1">{w.day.slice(5)} <span className="text-muted">{w.kind === "forecast" ? a.forecastDay : a.observedDay}</span></td>
                      <td className="py-1 text-end">{w.temperature_mean_c?.toFixed(1) ?? "—"}</td>
                      <td className="py-1 text-end">{w.relative_humidity_mean_pct?.toFixed(0) ?? "—"}</td>
                      <td className="py-1 text-end">{w.rh_hours_ge_90 ?? "—"}</td>
                      <td className="py-1 text-end">{w.precipitation_mm?.toFixed(1) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.weather.retrieved_at && (
            <p className="mt-1 text-[11px] text-muted">{a.retrieved}: {formatDate(data.weather.retrieved_at, locale)}</p>
          )}
        </section>
      )}

      {data && data.suitability.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-ink">{a.suitability}</h3>
          <ul className="flex flex-col gap-2">
            {data.suitability.map((r) => (
              <li key={r.profile_id} className="rounded-2xl bg-ink/[0.035] p-3 text-xs">
                <Badge tone={r.status === "met" ? "moderate" : "neutral"}>{a.suitabilityStatus[r.status]}</Badge>
                <p className="mt-1.5 text-ink">{r.description}</p>
                <p className="mt-1 text-muted">{a.source}: {r.source}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data && data.predictions.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-ink">{a.predictions}</h3>
          <ul className="flex flex-col gap-1.5">
            {data.predictions.slice(0, 5).map((p) => <PredictionRow key={p.prediction_id} p={p} />)}
          </ul>
        </section>
      )}

      <section className="border-t border-ink/[0.07] pt-4">
        {crop && disease ? (
          <Button fullWidth icon="chart" isLoading={estimating} onClick={() => void runEstimate()}>
            {estimating ? a.estimating : a.estimate}
          </Button>
        ) : (
          <p className="text-xs text-muted">{a.selectPair}</p>
        )}
        {estimateError && <div className="mt-3"><Alert tone="error">{estimateError}</Alert></div>}
        {estimate && <EstimateResult result={estimate} />}
        {crop && disease && (
          <div className="mt-3">
            <GenerateReportButton label={t.reports.areaReport} fullWidth request={{
              type: "outbreak_area", crop, disease, horizon_days: horizon, date_from: dateFrom,
              ...(selection.areaId ? { subject_id: selection.areaId } : { latitude: selection.center.lat, longitude: selection.center.lon }),
            }} />
          </div>
        )}
      </section>
    </Card>
  );
}

function RiskBadge({ level }: { level: RiskLevel }) {
  const { t } = useLocale();
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold text-white"
          style={{ background: RISK_COLORS[level] }}>
      {t.outbreak.risk[level]}
    </span>
  );
}

function PredictionRow({ p }: { p: PredictionSummary }) {
  const { t, locale } = useLocale();
  return (
    <li className="flex items-center justify-between gap-2 rounded-xl bg-ink/[0.035] px-3 py-2 text-xs">
      <RiskBadge level={p.risk_level} />
      <span className="text-muted">
        {daysLabel(t.outbreak.filters, p.horizon_days)} · {p.created_at ? formatDate(p.created_at, locale) : ""}
      </span>
    </li>
  );
}

function EstimateResult({ result }: { result: PredictionResult }) {
  const { t, locale } = useLocale();
  const r = t.outbreak.result;
  const limitation = (code: string) => (t.outbreak.limitation as Record<string, string>)[code] ?? humanizeLabel(code);

  if (result.status === "model_unavailable") {
    const reason = (result.reason ?? result.model.readiness) as keyof typeof r.unavailableReason;
    return (
      <div className="mt-4">
        <Alert tone="info" title={r.title}>{r.unavailableReason[reason] ?? result.model.message}</Alert>
      </div>
    );
  }

  return (
    <div className="mt-4 flex flex-col gap-3 rounded-2xl bg-ink/[0.035] p-4 text-sm" role="status">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-ink">{r.title}</span>
        <RiskBadge level={result.risk_level} />
      </div>
      {result.status === "insufficient_data" && <p className="text-muted">{r.insufficient}</p>}
      <dl className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <dt className="text-muted">{r.forecastPeriod}</dt>
          <dd className="font-data text-ink">{result.forecast_start} → {result.forecast_end}</dd>
        </div>
        {result.score != null && (
          <div>
            <dt className="text-muted">{r.score}</dt>
            <dd className="font-data text-ink">
              {result.score.toFixed(2)} <span className="text-muted">({result.score_kind === "calibrated_probability" ? r.calibrated : r.uncalibrated})</span>
            </dd>
          </div>
        )}
        {result.confidence_level && (
          <div>
            <dt className="text-muted">{r.confidence}</dt>
            <dd className="text-ink">{t.outbreak.confidence[result.confidence_level]}</dd>
          </div>
        )}
        <div>
          <dt className="text-muted">{r.completeness}</dt>
          <dd className="font-data text-ink">{(result.data_completeness * 100).toFixed(0)}%</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-muted">{r.model}</dt>
          <dd className="font-data text-ink">{result.model.name ?? "—"} {result.model.version ?? ""}</dd>
        </div>
        {result.created_at && (
          <div className="col-span-2">
            <dt className="text-muted">{r.madeAt}</dt>
            <dd className="text-ink">{formatDate(result.created_at, locale)}</dd>
          </div>
        )}
      </dl>
      {result.factors && result.factors.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold text-ink">{r.factors}</h4>
          <p className="mb-1.5 text-[11px] text-muted">{r.factorsNote}</p>
          <ul className="flex flex-col gap-1 text-xs">
            {result.factors.slice(0, 6).map((f) => (
              <li key={f.feature} className="flex justify-between gap-2">
                <span className="text-ink">{(t.outbreak.feature as Record<string, string>)[f.feature] ?? humanizeLabel(f.feature)}</span>
                <span className="text-muted">{f.value != null ? f.value.toFixed(1) : "—"} · {r.relation[f.relation]}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {result.limitations.length > 0 && (
        <section>
          <h4 className="mb-1 text-xs font-semibold text-ink">{r.limitations}</h4>
          <ul className="flex list-disc flex-col gap-0.5 ps-4 text-xs text-muted">
            {result.limitations.map((c) => <li key={c}>{limitation(c)}</li>)}
          </ul>
        </section>
      )}
    </div>
  );
}
