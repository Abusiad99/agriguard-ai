import { useEffect, useId, useState } from "react";
import { useCountUp } from "@/hooks/useCountUp";

/**
 * ProgressRing — the app's signature diagnostic motif (see frontend/DESIGN.md):
 * a radial "scan ring" gauge for confidence % and severity. On first paint the arc
 * sweeps from zero while the number counts up, like an instrument settling on a
 * reading. Fill and color always map to real diagnosis data.
 */
interface ProgressRingProps {
  /** 0-100 */
  value: number;
  size?: number;
  strokeWidth?: number;
  /** Any CSS color, e.g. "rgb(var(--c-primary))". Defaults to the brand gradient. */
  color?: string;
  trackColor?: string;
  label?: string;
  valueLabel?: string;
  /** Smaller text under the main value inside the ring. */
  sublabel?: string;
}

export function ProgressRing({
  value,
  size = 128,
  strokeWidth = 10,
  color,
  trackColor = "rgb(var(--c-ink) / 0.08)",
  label,
  valueLabel,
  sublabel,
}: ProgressRingProps) {
  const id = useId().replace(/:/g, "");
  const clamped = Math.max(0, Math.min(100, value));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  // Start empty, then let CSS transition the arc to the real value.
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setShown(clamped));
    return () => cancelAnimationFrame(frame);
  }, [clamped]);
  const offset = circumference - (shown / 100) * circumference;
  const counted = useCountUp(clamped, 1400);

  const gradientId = `ring-${id}`;
  const stroke = color ?? `url(#${gradientId})`;
  const glow = color ?? "rgb(var(--c-primary))";

  return (
    <div className="inline-flex flex-col items-center" role="img" aria-label={`${label ?? "Value"}: ${valueLabel ?? `${Math.round(clamped)}%`}`}>
      <div className="relative" style={{ width: size, height: size }}>
        {/* Soft halo in the ring's color */}
        <div
          className="absolute inset-[14%] rounded-full opacity-30 blur-2xl"
          style={{ background: glow }}
          aria-hidden="true"
        />
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="relative -rotate-90" aria-hidden="true">
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" style={{ stopColor: "rgb(var(--c-sprout))" }} />
              <stop offset="100%" style={{ stopColor: "rgb(var(--c-primary))" }} />
            </linearGradient>
          </defs>
          <circle cx={size / 2} cy={size / 2} r={radius} style={{ stroke: trackColor }} strokeWidth={strokeWidth} fill="none" />
          {/* Tick marks every 10% — the instrument dial */}
          {Array.from({ length: 20 }, (_, i) => {
            const a = (i / 20) * Math.PI * 2;
            const r1 = radius - strokeWidth / 2 - 4;
            const r2 = r1 - (i % 5 === 0 ? 5 : 2.5);
            return (
              <line
                key={i}
                x1={size / 2 + Math.cos(a) * r1}
                y1={size / 2 + Math.sin(a) * r1}
                x2={size / 2 + Math.cos(a) * r2}
                y2={size / 2 + Math.sin(a) * r2}
                style={{ stroke: "rgb(var(--c-muted) / 0.35)" }}
                strokeWidth={1}
              />
            );
          })}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={stroke}
            style={color ? { stroke: color } : undefined}
            strokeWidth={strokeWidth}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-[stroke-dashoffset] duration-[1400ms] ease-out-expo"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="max-w-[78%] truncate px-1 font-data font-semibold leading-tight tabular-nums text-ink"
            style={{ fontSize: valueLabel && valueLabel.length > 4 ? Math.max(13, size * 0.12) : size * 0.2 }}
          >
            {valueLabel ?? `${Math.round(counted)}%`}
          </span>
          {sublabel && <span className="mt-1 text-[11px] font-medium text-muted">{sublabel}</span>}
        </div>
      </div>
      {label && <span className="mt-3 text-sm font-medium text-muted">{label}</span>}
    </div>
  );
}
