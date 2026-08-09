/**
 * ProgressRing — the app's signature diagnostic motif (see frontend/DESIGN.md):
 * a radial "scan ring" gauge, reused for confidence % (Dashboard, Diagnosis Result)
 * and as the loading indicator during AI analysis. Functional, not decorative — the
 * fill percentage and color always map to real diagnosis data (confidence score or
 * severity band).
 */
interface ProgressRingProps {
  /** 0-100 */
  value: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  trackColor?: string;
  label?: string;
  valueLabel?: string;
}

export function ProgressRing({
  value,
  size = 120,
  strokeWidth = 10,
  color = "#2F6B4F",
  trackColor = "#D8DCC9",
  label,
  valueLabel,
}: ProgressRingProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (clamped / 100) * circumference;

  return (
    <div className="inline-flex flex-col items-center" role="img" aria-label={`${label ?? "Value"}: ${Math.round(clamped)}%`}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} stroke={trackColor} strokeWidth={strokeWidth} fill="none" />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={color}
            strokeWidth={strokeWidth}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-[stroke-dashoffset] duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-data text-2xl font-semibold tabular-nums text-ink">
            {valueLabel ?? `${Math.round(clamped)}%`}
          </span>
        </div>
      </div>
      {label && <span className="mt-1.5 text-xs font-medium uppercase tracking-wide text-muted">{label}</span>}
    </div>
  );
}
