import { linePoints } from "@/lib/aiFeatureUi";

/** Small dependency-free SVG charts for the feature dashboards. Every value shown
 * comes from the caller; nothing is interpolated or invented between points. */

export function LineChart({ points, maxValue, unit = "", ariaLabel }: {
  points: { label: string; value: number }[];
  maxValue?: number;
  unit?: string;
  ariaLabel: string;
}) {
  const width = 320;
  const height = 120;
  const values = points.map((p) => p.value);
  const coords = linePoints(values, width, height, 12, maxValue);
  return (
    <figure>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-32 w-full overflow-visible" role="img" aria-label={ariaLabel}>
        <line x1="12" x2={width - 12} y1={height - 12} y2={height - 12} stroke="currentColor" className="text-ink/15" />
        <polyline points={coords} fill="none" stroke="rgb(var(--c-primary))" strokeWidth="2.5" strokeLinejoin="round" />
        {coords.split(" ").map((c, i) => {
          const [x, y] = c.split(",").map(Number);
          return (
            <g key={i}>
              <circle cx={x} cy={y} r="4" fill="rgb(var(--c-primary))" />
              <text x={x} y={y - 9} textAnchor="middle" className="fill-current text-[10px] text-ink">
                {values[i].toFixed(1)}{unit}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-1 flex justify-between text-[11px] text-muted">
        {points.map((p, i) => <span key={i}>{p.label}</span>)}
      </figcaption>
    </figure>
  );
}

export function BarChart({ bars, ariaLabel }: {
  bars: { label: string; total: number; highlighted: number }[];
  ariaLabel: string;
}) {
  const max = Math.max(1, ...bars.map((b) => b.total));
  return (
    <div role="img" aria-label={ariaLabel} className="flex h-28 items-end gap-1">
      {bars.map((b, i) => (
        <div key={i} className="flex flex-1 flex-col items-center gap-1" title={`${b.label}: ${b.highlighted}/${b.total}`}>
          <div className="relative w-full rounded-t bg-ink/[0.12]" style={{ height: `${(b.total / max) * 96}px` }}>
            <div className="absolute inset-x-0 bottom-0 rounded-t bg-[#c62828]" style={{ height: b.total ? `${(b.highlighted / b.total) * 100}%` : 0 }} />
          </div>
        </div>
      ))}
    </div>
  );
}
