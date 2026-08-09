import type { Config } from "tailwindcss";

// AgriGuard AI — design token system.
// Palette grounded in "midday field-inspection" clarity (not golden-hour cream):
// a flax-linen canvas, deep leaf-green primary, and a severity scale (wheat/ochre/
// rust) that is FUNCTIONAL — it always maps to Mild/Moderate/Severe diagnosis data,
// never used decoratively. See frontend/DESIGN.md for the full rationale.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        canvas: "#F7F5EE",
        ink: "#1C2B22",
        muted: "#5B6B5A",
        line: "#D8DCC9",
        primary: {
          DEFAULT: "#2F6B4F",
          dark: "#20492F",
          light: "#DCEAE1",
        },
        accent: {
          DEFAULT: "#D8A73D",
          dark: "#B4862A",
        },
        severity: {
          mild: "#D8A73D",
          "mild-bg": "#FBF1DA",
          moderate: "#C8722A",
          "moderate-bg": "#F8E4D2",
          severe: "#A13D2C",
          "severe-bg": "#F5DCD6",
        },
        surface: "#FFFFFF",
        danger: "#A13D2C",
        success: "#2F6B4F",
      },
      fontFamily: {
        display: ["Fraunces", "ui-serif", "Georgia", "serif"],
        body: ["IBM Plex Sans", "IBM Plex Sans Arabic", "ui-sans-serif", "system-ui", "sans-serif"],
        arabic: ["IBM Plex Sans Arabic", "IBM Plex Sans", "ui-sans-serif", "sans-serif"],
        data: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        card: "0.5rem",
      },
      boxShadow: {
        elevate: "0 8px 24px -8px rgba(28, 43, 34, 0.18)",
      },
      keyframes: {
        "scan-sweep": {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "scan-sweep": "scan-sweep 1.6s ease-in-out infinite",
        "fade-in": "fade-in 0.25s ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
