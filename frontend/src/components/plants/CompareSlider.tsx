import { useState } from "react";

/** Before/after slider: the later photo is revealed over the earlier one. Purely a
 * visual aid — differences in pixels are not used as a measurement. */
export function CompareSlider({ before, after, beforeLabel, afterLabel }: {
  before: string;
  after: string;
  beforeLabel: string;
  afterLabel: string;
}) {
  const [position, setPosition] = useState(50);
  return (
    <div>
      <div className="relative overflow-hidden rounded-2xl bg-ink/[0.05] ring-1 ring-inset ring-ink/10">
        <img src={before} alt={beforeLabel} className="block w-full" />
        <img src={after} alt={afterLabel} className="absolute inset-0 h-full w-full object-cover"
             style={{ clipPath: `inset(0 0 0 ${position}%)` }} />
        <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white shadow" style={{ left: `${position}%` }} aria-hidden="true" />
        <span className="absolute start-2 top-2 rounded-full bg-black/55 px-2 py-0.5 text-xs text-white">{beforeLabel}</span>
        <span className="absolute end-2 top-2 rounded-full bg-black/55 px-2 py-0.5 text-xs text-white">{afterLabel}</span>
      </div>
      <input type="range" min={0} max={100} value={position} onChange={(e) => setPosition(Number(e.target.value))}
             className="mt-2 w-full accent-[rgb(var(--c-primary))]" aria-label={`${beforeLabel} / ${afterLabel}`} />
    </div>
  );
}
