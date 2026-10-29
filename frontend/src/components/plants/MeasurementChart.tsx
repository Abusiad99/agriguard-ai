import { Link } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import type { MeasurementPoint } from "@/types/api";
import { formatDate } from "@/utils/format";

/** Line chart of GENUINE segmentation measurements only (the API never sends
 * estimates in this series). Points from photos with quality warnings are drawn
 * hollow. Each point links to its observation; a visually hidden table gives
 * screen-reader users the same data. */
export function MeasurementChart({ points }: { points: MeasurementPoint[] }) {
  const { locale } = useLocale();
  const W = 640;
  const H = 220;
  const pad = { l: 40, r: 16, t: 14, b: 30 };
  const times = points.map((p) => new Date(p.diagnosed_at).getTime());
  const tMin = Math.min(...times);
  const tMax = Math.max(...times);
  const span = tMax - tMin || 1;
  const yMax = Math.min(100, Math.max(10, Math.ceil(Math.max(...points.map((p) => p.affected_area_pct)) / 10) * 10));
  const x = (t: number) => pad.l + (points.length === 1 ? (W - pad.l - pad.r) / 2 : ((t - tMin) / span) * (W - pad.l - pad.r));
  const y = (v: number) => pad.t + (1 - v / yMax) * (H - pad.t - pad.b);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(times[i]).toFixed(1)},${y(p.affected_area_pct).toFixed(1)}`).join(" ");
  const ticks = [0, yMax / 2, yMax];

  return (
    <div dir="ltr">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Measured affected area over time">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} style={{ stroke: "rgb(var(--c-ink) / 0.08)" }} />
            <text x={pad.l - 8} y={y(v) + 4} textAnchor="end" className="fill-muted text-[11px]">{v}%</text>
          </g>
        ))}
        <path d={path} fill="none" strokeWidth={2.5} strokeLinejoin="round" style={{ stroke: "rgb(var(--c-primary))" }} />
        {points.map((p, i) => {
          const warn = p.image_quality_status && p.image_quality_status !== "ok";
          return (
            <Link key={p.diagnosis_id} to={`/diagnoses/${p.diagnosis_id}`}>
              <circle
                cx={x(times[i])}
                cy={y(p.affected_area_pct)}
                r={5.5}
                strokeWidth={2.5}
                style={{ stroke: "rgb(var(--c-primary))", fill: warn ? "rgb(var(--c-surface))" : "rgb(var(--c-primary))" }}
              >
                <title>{`${formatDate(p.diagnosed_at, locale)} — ${p.affected_area_pct.toFixed(1)}%`}</title>
              </circle>
            </Link>
          );
        })}
        <text x={pad.l} y={H - 8} className="fill-muted text-[11px]">{formatDate(points[0].diagnosed_at, locale)}</text>
        {points.length > 1 && (
          <text x={W - pad.r} y={H - 8} textAnchor="end" className="fill-muted text-[11px]">
            {formatDate(points[points.length - 1].diagnosed_at, locale)}
          </text>
        )}
      </svg>
      <table className="sr-only">
        <tbody>
          {points.map((p) => (
            <tr key={p.diagnosis_id}>
              <td>{formatDate(p.diagnosed_at, locale)}</td>
              <td>{p.affected_area_pct.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
