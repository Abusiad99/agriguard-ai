import { useLocale } from "@/context/LocaleContext";
import { Icon } from "@/components/ui/Icon";

/**
 * Hero illustration for the sign-in screen: a tomato leaf with early-blight
 * lesions (brown target rings with a yellow halo) under a camera viewfinder, a
 * scan line passing over it, detection boxes locked on each lesion, and the
 * result chips the app would produce. Labeled as an example in the UI.
 */
const LESIONS: Array<[number, number, number]> = [
  [206, 150, 15],
  [118, 214, 19],
  [196, 252, 11],
];

const VEIN_YS = [78, 112, 146, 180, 214, 248, 282];

export function ScanIllustration() {
  const { t } = useLocale();

  return (
    <div className="relative mx-auto aspect-[320/360] w-full max-w-[19rem]">
      {/* Viewfinder */}
      <svg viewBox="0 0 320 360" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
        <defs>
          <linearGradient id="hero-leaf" x1="0.3" y1="0" x2="0.7" y2="1">
            <stop offset="0%" stopColor="#7fd35c" />
            <stop offset="55%" stopColor="#3a9a45" />
            <stop offset="100%" stopColor="#1b6634" />
          </linearGradient>
          <radialGradient id="hero-leaf-hi" cx="0.38" cy="0.28" r="0.55">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="hero-halo">
            <stop offset="0%" stopColor="#e9dc6c" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#e9dc6c" stopOpacity="0" />
          </radialGradient>
        </defs>

        <g className="animate-float [animation-duration:8s]">
          <path
            d="M160 22C250 72 292 170 252 262C226 316 190 336 160 346C130 336 94 316 68 262C28 170 70 72 160 22Z"
            fill="url(#hero-leaf)"
          />
          <path
            d="M160 22C250 72 292 170 252 262C226 316 190 336 160 346C130 336 94 316 68 262C28 170 70 72 160 22Z"
            fill="url(#hero-leaf-hi)"
          />
          <path d="M160 34Q157 190 160 352" stroke="#e3f9cf" strokeOpacity="0.7" strokeWidth="3" fill="none" strokeLinecap="round" />
          {VEIN_YS.map((y) => (
            <g key={y} stroke="#e3f9cf" strokeOpacity="0.38" strokeWidth="1.6" fill="none" strokeLinecap="round">
              <path d={`M160 ${y + 12}Q${200} ${y} ${238 - Math.abs(y - 180) * 0.25} ${y - 30}`} />
              <path d={`M160 ${y + 12}Q${120} ${y} ${82 + Math.abs(y - 180) * 0.25} ${y - 30}`} />
            </g>
          ))}
          {LESIONS.map(([cx, cy, r]) => (
            <g key={`${cx}-${cy}`}>
              <circle cx={cx} cy={cy} r={r * 1.9} fill="url(#hero-halo)" />
              <circle cx={cx} cy={cy} r={r} fill="#7a4b1c" />
              <circle cx={cx} cy={cy} r={r * 0.72} fill="none" stroke="#4f2f10" strokeWidth="1.6" />
              <circle cx={cx} cy={cy} r={r * 0.42} fill="none" stroke="#4f2f10" strokeWidth="1.4" />
              <circle cx={cx} cy={cy} r={r * 0.15} fill="#3b220a" />
            </g>
          ))}
        </g>

        {/* Detection boxes locked onto each lesion */}
        {LESIONS.map(([cx, cy, r], i) => {
          const s = r * 2.6;
          return (
            <g key={`box-${i}`} className="animate-pop-in" style={{ animationDelay: `${0.9 + i * 0.35}s`, transformOrigin: `${cx}px ${cy}px` }}>
              <rect
                x={cx - s / 2}
                y={cy - s / 2}
                width={s}
                height={s}
                rx="8"
                fill="rgb(140 230 100 / 0.08)"
                stroke="#a6f08a"
                strokeWidth="1.6"
                strokeDasharray="6 6"
                className="animate-dash-march"
              />
            </g>
          );
        })}

        {/* Corner brackets */}
        <g fill="none" stroke="white" strokeOpacity="0.75" strokeWidth="3" strokeLinecap="round">
          <path d="M6 46V22A16 16 0 0122 6h24M274 6h24a16 16 0 0116 16v24M314 314v24a16 16 0 01-16 16h-24M46 354H22A16 16 0 016 338v-24" />
        </g>
      </svg>

      {/* Scan line */}
      <div
        className="pointer-events-none absolute inset-x-[4%] top-[6%] animate-scan-line [mask-image:linear-gradient(90deg,transparent,black_18%,black_82%,transparent)]"
        aria-hidden="true"
      >
        <div className="h-16 -translate-y-full bg-gradient-to-t from-sprout/25 to-transparent" />
        <div className="h-[2px] -translate-y-16 rounded-full bg-[#b9f59c] shadow-[0_0_18px_4px_rgb(140_230_100/0.65)]" />
      </div>

      {/* Result chips */}
      <div className="absolute -end-[38%] -top-[3%] animate-pop-in [animation-delay:1.6s]">
        <div className="animate-float rounded-2xl border border-white/15 bg-[#0b2f22]/85 shadow-[0_18px_40px_-12px_rgb(0_0_0/0.6)] backdrop-blur-xl px-3.5 py-2.5">
          <p className="text-[11px] text-white/60">{t.auth.exampleScan}</p>
          <p className="flex items-center gap-1.5 text-sm font-semibold text-white">
            <Icon name="leaf" className="h-4 w-4 text-sprout" />
            {t.auth.examplePlant}
          </p>
        </div>
      </div>

      <div className="absolute -start-[42%] top-[44%] animate-pop-in [animation-delay:2s]">
        <div className="animate-float rounded-2xl border border-white/15 bg-[#0b2f22]/85 shadow-[0_18px_40px_-12px_rgb(0_0_0/0.6)] backdrop-blur-xl px-3.5 py-2.5 [animation-delay:-2s]">
          <span className="mb-1 inline-flex items-center gap-1.5 rounded-full bg-[#f29a4c]/20 px-2 py-0.5 text-[11px] font-semibold text-[#ffc08a]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#f29a4c]" />
            {t.result.severityModerate}
          </span>
          <p className="text-sm font-semibold text-white">{t.auth.exampleDisease}</p>
        </div>
      </div>

      <div className="absolute -bottom-[6%] -end-[34%] animate-pop-in [animation-delay:2.4s]">
        <div className="flex animate-float items-center gap-3 rounded-2xl border border-white/15 bg-[#0b2f22]/85 shadow-[0_18px_40px_-12px_rgb(0_0_0/0.6)] backdrop-blur-xl py-2.5 pe-4 ps-2.5 [animation-delay:-4s]">
          <MiniRing value={94} />
          <div>
            <p className="font-data text-lg font-semibold leading-none text-white">94%</p>
            <p className="mt-1 text-[11px] text-white/60">{t.result.confidence}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function MiniRing({ value }: { value: number }) {
  const r = 15;
  const c = 2 * Math.PI * r;
  return (
    <svg viewBox="0 0 40 40" className="h-10 w-10 -rotate-90" aria-hidden="true">
      <circle cx="20" cy="20" r={r} stroke="white" strokeOpacity="0.15" strokeWidth="4" fill="none" />
      <circle
        cx="20"
        cy="20"
        r={r}
        stroke="#a6f08a"
        strokeWidth="4"
        fill="none"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c - (value / 100) * c}
      />
    </svg>
  );
}
