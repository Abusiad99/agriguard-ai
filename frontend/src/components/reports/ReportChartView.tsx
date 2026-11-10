import { useRef } from "react";
import { Button } from "@/components/ui/Button";
import type { ReportChart } from "@/types/reports";

const PALETTE = ["#2D6A4F", "#c62828", "#2563eb", "#b45309"];
const MARKER = "#7c3aed";
const W = 640;
const H = 230;
const PAD = { left: 64, right: 16, top: 40, bottom: 46 };

/** Chart drawn from a report's stored series (no smoothing, gaps stay gaps). Markers
 * (recorded treatments) are drawn on the time axis; a "step" chart shows ordinal
 * levels (e.g. estimated severity) with their names on the y axis. */
export function ReportChartView({ chart, exportLabel, dir }: { chart: ReportChart; exportLabel: string; dir: "ltr" | "rtl" }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const series = chart.series.filter((s) => s.values.some((v) => v != null));
  const values = series.flatMap((s) => s.values.filter((v): v is number => v != null));
  const levels = chart.y_labels ? Object.keys(chart.y_labels).map(Number).sort((a, b) => a - b) : null;
  const max = levels ? levels[levels.length - 1] + 0.5 : Math.max(1, ...values) * 1.1;
  const min = levels ? levels[0] - 0.5 : Math.min(0, ...values);
  const n = chart.x.length;
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const xAt = (i: number) => PAD.left + (n > 1 ? (i * innerW) / (n - 1) : innerW / 2);
  const yAt = (v: number) => PAD.top + innerH - ((v - min) / (max - min)) * innerH;
  const labelEvery = Math.max(1, Math.ceil(n / 10));
  const ticks = levels ?? [0, 0.5, 1].map((f) => min + (max - min) * f);

  const exportPng = () => {
    const svg = svgRef.current;
    if (!svg) return;
    const xml = new XMLSerializer().serializeToString(svg);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = W * 2;
      canvas.height = H * 2;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const a = document.createElement("a");
      a.href = canvas.toDataURL("image/png");
      a.download = `${chart.id}.png`;
      a.click();
    };
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
  };

  const linePoints = (vals: (number | null)[], step: boolean): string[][] => {
    const segments: string[][] = [[]];
    vals.forEach((v, i) => {
      if (v == null) {
        segments.push([]);
        return;
      }
      const seg = segments[segments.length - 1];
      if (step && seg.length) {
        const prevY = seg[seg.length - 1].split(",")[1];
        seg.push(`${xAt(i).toFixed(1)},${prevY}`);
      }
      seg.push(`${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`);
    });
    return segments.filter((s) => s.length);
  };

  return (
    <figure className="break-inside-avoid">
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={chart.title}
           xmlns="http://www.w3.org/2000/svg" direction="ltr" fontFamily="system-ui, sans-serif">
        <rect x="0" y="0" width={W} height={H} fill="#ffffff" />
        {chart.forecast_from != null && chart.forecast_from >= 0 && (
          <rect x={xAt(chart.forecast_from)} y={PAD.top} width={Math.max(0, xAt(n - 1) - xAt(chart.forecast_from))} height={innerH}
                fill="#eef2ff" />
        )}
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={W - PAD.right} y1={yAt(v)} y2={yAt(v)} stroke="#e5e7eb" />
            <text x={PAD.left - 6} y={yAt(v) + 4} fontSize="11" textAnchor="end" fill="#6b7280" direction={dir}>
              {levels && chart.y_labels ? chart.y_labels[String(v)] : v.toFixed(v >= 10 ? 0 : 1)}
            </text>
          </g>
        ))}
        {(chart.markers ?? []).map((m, i) => (
          <g key={`m-${i}`}>
            <line x1={xAt(m.index)} x2={xAt(m.index)} y1={PAD.top - 4} y2={PAD.top + innerH} stroke={MARKER}
                  strokeWidth="1.2" strokeDasharray="4 3" />
            <text x={xAt(m.index) + 3} y={PAD.top - 6 - (i % 2) * 10} fontSize="9.5" fill={MARKER} direction={dir}>{m.label}</text>
          </g>
        ))}
        {chart.kind === "bar"
          ? series.map((s, si) => s.values.map((v, i) => {
              if (v == null) return null;
              const bw = Math.max(2, innerW / Math.max(1, n) / (series.length + 1));
              const x = PAD.left + (i * innerW) / Math.max(1, n) + si * bw;
              return <rect key={`${si}-${i}`} x={x} y={yAt(v)} width={bw - 1} height={yAt(min) - yAt(v)} fill={PALETTE[si % 4]} />;
            }))
          : series.map((s, si) => (
              <g key={s.key}>
                {linePoints(s.values, chart.kind === "step").map((seg, k) => (
                  <polyline key={k} points={seg.join(" ")} fill="none" stroke={PALETTE[si % 4]} strokeWidth="2.2"
                            strokeDasharray={chart.kind === "step" ? "5 3" : undefined} />
                ))}
                {s.values.map((v, i) => v != null && <circle key={i} cx={xAt(i)} cy={yAt(v)} r="3" fill={PALETTE[si % 4]} />)}
              </g>
            ))}
        {chart.x.map((x, i) => i % labelEvery === 0 && (
          <text key={i} x={xAt(i)} y={H - PAD.bottom + 16} fontSize="10" textAnchor="middle" fill="#4b5563"
                direction={dir}>{x}</text>
        ))}
        {series.map((s, si) => (
          <g key={s.key} transform={`translate(${PAD.left + si * 150}, 14)`}>
            <rect width="10" height="10" y="-8" fill={PALETTE[si % 4]} />
            <text x="14" fontSize="11" fill="#1f2937" direction={dir}>{s.label}{chart.unit && s.key === series[0].key ? ` (${chart.unit})` : ""}</text>
          </g>
        ))}
      </svg>
      {chart.note && <figcaption className="mt-1 text-xs text-muted">{chart.note}</figcaption>}
      <div className="mt-1 flex justify-end print:hidden">
        <Button size="sm" variant="ghost" icon="download" onClick={exportPng}>{exportLabel}</Button>
      </div>
    </figure>
  );
}
