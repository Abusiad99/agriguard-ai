import { memo, useMemo } from "react";

/**
 * The app's backdrop: a topographic survey map of a field — procedurally generated
 * contour rings (every fifth one heavier, like the index contours on a real topo
 * sheet) that turn very slowly, over soft pools of chlorophyll and date-gold light,
 * with a fine film grain on top. Purely decorative: aria-hidden, pointer-events none,
 * and frozen under prefers-reduced-motion.
 */

type Variant = "app" | "hero";

function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Hill {
  cx: number;
  cy: number;
  rings: number;
  base: number;
  step: number;
  duration: number;
  reverse: boolean;
  paths: { d: string; index: boolean }[];
}

function buildHills(seed: number, layout: Array<[number, number, number, number, number]>): Hill[] {
  const rand = mulberry32(seed);
  return layout.map(([cx, cy, rings, base, step], hillIdx) => {
    const p = [rand() * Math.PI * 2, rand() * Math.PI * 2, rand() * Math.PI * 2, rand() * Math.PI * 2];
    const a = [0.08 + rand() * 0.06, 0.05 + rand() * 0.05, 0.025 + rand() * 0.03, 0.12 + rand() * 0.08];
    const paths: Hill["paths"] = [];
    for (let k = 0; k < rings; k++) {
      const r0 = base + k * step;
      const grow = 1 + k * 0.06; // outer rings wander more, like real terrain
      const n = 96;
      const pts: Array<[number, number]> = [];
      for (let i = 0; i < n; i++) {
        const th = (i / n) * Math.PI * 2;
        const wobble =
          1 +
          grow * (a[0] * Math.sin(2 * th + p[0] + k * 0.15) + a[1] * Math.sin(3 * th + p[1] - k * 0.1) + a[2] * Math.sin(5 * th + p[2]));
        const stretch = 1 + a[3] * Math.cos(th + p[3]);
        pts.push([cx + Math.cos(th) * r0 * wobble * stretch, cy + Math.sin(th) * r0 * wobble]);
      }
      // Smooth closed curve through midpoints (quadratic B-spline).
      const mid = (i: number) => {
        const [x1, y1] = pts[i % n];
        const [x2, y2] = pts[(i + 1) % n];
        return [(x1 + x2) / 2, (y1 + y2) / 2];
      };
      let d = `M${mid(0)[0].toFixed(1)} ${mid(0)[1].toFixed(1)}`;
      for (let i = 1; i <= n; i++) {
        const [px, py] = pts[i % n];
        const [mx, my] = mid(i);
        d += `Q${px.toFixed(1)} ${py.toFixed(1)} ${mx.toFixed(1)} ${my.toFixed(1)}`;
      }
      paths.push({ d: d + "Z", index: (k + 1) % 5 === 0 });
    }
    return {
      cx,
      cy,
      rings,
      base,
      step,
      duration: 160 + hillIdx * 45,
      reverse: hillIdx % 2 === 1,
      paths,
    };
  });
}

const APP_LAYOUT: Array<[number, number, number, number, number]> = [
  [1320, 120, 16, 26, 34],
  [180, 860, 14, 30, 36],
  [820, 1180, 10, 40, 40],
];

const HERO_LAYOUT: Array<[number, number, number, number, number]> = [
  [1250, 180, 18, 18, 30],
  [260, 900, 16, 22, 34],
];

export const ContourField = memo(function ContourField({
  variant = "app",
  className = "",
}: {
  variant?: Variant;
  className?: string;
}) {
  const hills = useMemo(
    () => (variant === "hero" ? buildHills(7, HERO_LAYOUT) : buildHills(23, APP_LAYOUT)),
    [variant]
  );

  return (
    <svg
      className={`absolute inset-0 h-full w-full ${className}`}
      viewBox="0 0 1600 1000"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      {hills.map((hill, i) => (
        <g
          key={i}
          style={{
            transformOrigin: `${hill.cx}px ${hill.cy}px`,
            animation: `agri-turn ${hill.duration}s linear infinite ${hill.reverse ? "reverse" : ""}`,
          }}
        >
          {hill.paths.map((p, j) => (
            <path
              key={j}
              d={p.d}
              fill="none"
              stroke="currentColor"
              strokeWidth={p.index ? 1.6 : 0.8}
              opacity={p.index ? 1 : 0.75}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </g>
      ))}
    </svg>
  );
});

export function AmbientBackground() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* Pools of light */}
      <div
        className="absolute -top-[18%] start-[-12%] h-[60vmax] w-[60vmax] animate-drift rounded-full bg-primary/[0.16] blur-[110px] will-change-transform dark:bg-primary/[0.14]"
      />
      <div
        className="absolute -bottom-[25%] end-[-15%] h-[65vmax] w-[65vmax] animate-drift rounded-full bg-sprout/[0.14] blur-[120px] will-change-transform [animation-delay:-14s] [animation-direction:reverse] dark:bg-sprout/[0.06]"
      />
      <div
        className="absolute top-[30%] start-[35%] h-[38vmax] w-[38vmax] animate-drift rounded-full bg-accent/[0.12] blur-[120px] will-change-transform [animation-delay:-26s] dark:bg-accent/[0.06]"
      />

      {/* Topographic survey lines */}
      <div className="absolute inset-0 text-[color:var(--contour)] [mask-image:radial-gradient(ellipse_at_center,transparent_15%,black_70%)]">
        <ContourField variant="app" />
      </div>

      {/* Film grain */}
      <div className="grain absolute inset-0" />
    </div>
  );
}
