import type { Config } from "tailwindcss";

// AgriGuard AI — design tokens ("Grove & Viewfinder", see frontend/DESIGN.md).
// Every color is a CSS variable holding RGB channels (defined in src/index.css for
// light and dark themes), so opacity modifiers like `bg-primary/20` keep working and
// the whole app re-themes by toggling the `dark` class on <html>.
const v = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        canvas: v("canvas"),
        ink: v("ink"),
        muted: v("muted"),
        line: v("line"),
        surface: v("surface"),
        grove: v("grove"),
        sprout: v("sprout"),
        primary: {
          DEFAULT: v("primary"),
          dark: v("primary-dark"),
          light: v("primary-light"),
        },
        accent: {
          DEFAULT: v("accent"),
          dark: v("accent-dark"),
        },
        severity: {
          mild: v("mild"),
          "mild-bg": v("mild-bg"),
          moderate: v("moderate"),
          "moderate-bg": v("moderate-bg"),
          severe: v("severe"),
          "severe-bg": v("severe-bg"),
        },
        danger: v("severe"),
        success: v("primary"),
      },
      fontFamily: {
        display: ['"Readex Pro Variable"', '"Readex Pro"', '"IBM Plex Sans Arabic"', "ui-sans-serif", "system-ui", "sans-serif"],
        body: ['"IBM Plex Sans"', '"IBM Plex Sans Arabic"', "ui-sans-serif", "system-ui", "sans-serif"],
        arabic: ['"IBM Plex Sans Arabic"', '"IBM Plex Sans"', "ui-sans-serif", "sans-serif"],
        // Diagnostic numbers (confidence, counts, dates) use the display face with
        // tabular figures rather than a monospace, so readings stay aligned in columns.
        data: ['"Readex Pro Variable"', '"Readex Pro"', '"IBM Plex Sans Arabic"', "ui-sans-serif", "sans-serif"],
      },
      borderRadius: {
        card: "1rem",
        panel: "1.5rem",
      },
      boxShadow: {
        soft: "0 1px 2px rgb(var(--c-shadow) / 0.06), 0 12px 32px -16px rgb(var(--c-shadow) / 0.28)",
        elevate: "0 2px 6px rgb(var(--c-shadow) / 0.08), 0 24px 48px -20px rgb(var(--c-shadow) / 0.38)",
        glow: "0 10px 30px -10px rgb(var(--c-primary) / 0.6)",
        "glow-lg": "0 18px 44px -12px rgb(var(--c-primary) / 0.7)",
        "inner-hi": "inset 0 1px 0 rgb(255 255 255 / 0.22)",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        "scan-sweep": {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(320%)" },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "none" },
        },
        "rise-in": {
          "0%": { opacity: "0", transform: "translateY(18px) scale(0.985)" },
          "100%": { opacity: "1", transform: "none" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.94) translateY(8px)" },
          "100%": { opacity: "1", transform: "none" },
        },
        ripple: {
          "0%": { transform: "translate(-50%, -50%) scale(0)", opacity: "0.35" },
          "100%": { transform: "translate(-50%, -50%) scale(1)", opacity: "0" },
        },
        shine: {
          "0%": { transform: "translateX(-120%) skewX(-20deg)" },
          "100%": { transform: "translateX(220%) skewX(-20deg)" },
        },
        "spin-slow": {
          to: { transform: "rotate(360deg)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.85)", opacity: "0.7" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        drift: {
          "0%": { transform: "translate3d(0, 0, 0) scale(1)" },
          "33%": { transform: "translate3d(6%, -4%, 0) scale(1.08)" },
          "66%": { transform: "translate3d(-4%, 5%, 0) scale(0.96)" },
          "100%": { transform: "translate3d(0, 0, 0) scale(1)" },
        },
        "grow-x": {
          from: { transform: "scaleX(0)" },
          to: { transform: "scaleX(1)" },
        },
        "grow-y": {
          from: { transform: "scaleY(0)" },
          to: { transform: "scaleY(1)" },
        },
        "dash-march": {
          to: { strokeDashoffset: "-24" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "scan-line": {
          "0%, 100%": { top: "6%" },
          "50%": { top: "90%" },
        },
        draw: {
          from: { strokeDashoffset: "1" },
          to: { strokeDashoffset: "0" },
        },
        "pop-in": {
          "0%": { opacity: "0", transform: "scale(0.6)" },
          "70%": { opacity: "1", transform: "scale(1.06)" },
          "100%": { opacity: "1", transform: "none" },
        },
      },
      animation: {
        "scan-sweep": "scan-sweep 2.2s cubic-bezier(0.45, 0, 0.55, 1) infinite",
        "fade-in": "fade-in 0.35s ease-out both",
        "rise-in": "rise-in 0.7s cubic-bezier(0.16, 1, 0.3, 1) both",
        "scale-in": "scale-in 0.35s cubic-bezier(0.16, 1, 0.3, 1) both",
        ripple: "ripple 0.6s cubic-bezier(0.22, 1, 0.36, 1) forwards",
        shine: "shine 0.9s ease-in-out",
        "spin-slow": "spin-slow 6s linear infinite",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.2, 0.6, 0.4, 1) infinite",
        float: "float 6s ease-in-out infinite",
        drift: "drift 38s ease-in-out infinite",
        "grow-x": "grow-x 1s cubic-bezier(0.16, 1, 0.3, 1) both",
        "grow-y": "grow-y 0.9s cubic-bezier(0.16, 1, 0.3, 1) both",
        "dash-march": "dash-march 1.2s linear infinite",
        shimmer: "shimmer 1.6s linear infinite",
        "scan-line": "scan-line 4.5s cubic-bezier(0.45, 0, 0.55, 1) infinite",
        draw: "draw 1.4s cubic-bezier(0.16, 1, 0.3, 1) both",
        "pop-in": "pop-in 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) both",
      },
    },
  },
  plugins: [],
} satisfies Config;
