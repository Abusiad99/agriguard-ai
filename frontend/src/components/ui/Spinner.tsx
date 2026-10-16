import { useId } from "react";

export function Spinner({ className = "h-6 w-6 text-primary" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" role="status" aria-label="Loading">
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
    </svg>
  );
}

/**
 * The signature "scan ring": a sweeping gradient arc around a leaf, with a soft
 * pulse radiating out. Used wherever the app is waiting on the AI or the server.
 */
export function ScanRing({ size = 72, className = "" }: { size?: number; className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <div className={`relative inline-flex items-center justify-center ${className}`} style={{ width: size, height: size }}>
      <span className="absolute inset-0 animate-pulse-ring rounded-full border border-primary/40" />
      <span className="absolute inset-0 animate-pulse-ring rounded-full border border-primary/30 [animation-delay:1.2s]" />
      <svg viewBox="0 0 64 64" className="absolute inset-0 h-full w-full animate-spin [animation-duration:1.4s]" aria-hidden="true">
        <defs>
          <linearGradient id={`arc-${id}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" style={{ stopColor: "rgb(var(--c-sprout))" }} />
            <stop offset="100%" style={{ stopColor: "rgb(var(--c-primary))", stopOpacity: 0 }} />
          </linearGradient>
        </defs>
        <circle cx="32" cy="32" r="28" fill="none" style={{ stroke: "rgb(var(--c-primary) / 0.12)" }} strokeWidth="4" />
        <circle cx="32" cy="32" r="28" fill="none" stroke={`url(#arc-${id})`} strokeWidth="4" strokeLinecap="round" strokeDasharray="120 200" />
      </svg>
      <svg viewBox="0 0 24 24" className="relative h-[38%] w-[38%] text-primary" fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5c0-8.25 5.25-14.25 15-15-.75 9.75-6.75 15-15 15zM4.5 19.5l7.5-7.5" />
      </svg>
    </div>
  );
}
