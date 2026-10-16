/** Brand mark: a leaf caught inside a camera viewfinder, with the date-gold
 * "scan point" where the AI locks on. */
export function LogoMark({ className = "h-10 w-10", animated = false }: { className?: string; animated?: boolean }) {
  return (
    <span className={`relative inline-flex shrink-0 items-center justify-center rounded-[30%] bg-brand shadow-glow ${className}`}>
      <svg viewBox="0 0 40 40" className="h-full w-full" aria-hidden="true">
        <g fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeOpacity="0.6">
          <path d="M9 14V11a2 2 0 012-2h3M26 9h3a2 2 0 012 2v3M31 26v3a2 2 0 01-2 2h-3M14 31h-3a2 2 0 01-2-2v-3" />
        </g>
        <path d="M13 27c0-7.5 4.6-12.6 14-13.4-.7 8.9-6 13.4-14 13.4z" fill="white" />
        <path d="M13.6 26.4l7.2-7.2" stroke="#0a5a3b" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="23.5" cy="18" r="2" fill="#E9B752" className={animated ? "animate-pulse" : ""} />
      </svg>
    </span>
  );
}

export function Logo({ name, className = "", tone = "default" }: { name: string; className?: string; tone?: "default" | "light" }) {
  return (
    <span className={`inline-flex items-center gap-3 ${className}`}>
      <LogoMark />
      <span className={`font-display text-lg font-semibold tracking-tight ${tone === "light" ? "text-white" : "text-ink"}`}>{name}</span>
    </span>
  );
}
