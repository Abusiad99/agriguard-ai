# AgriGuard AI — Frontend Design System ("Grove & Viewfinder")

## Subject & primary user
The primary persona ("Farmer Youssef") uses the app outdoors, on a phone, often one-handed and
not tech-savvy; the secondary persona (agronomist/admin) reviews data indoors on a larger screen.
The interface has to feel like a trustworthy professional instrument for both — calm, legible and
fast — while still feeling alive and premium.

## The idea
Two images from the subject's own world carry the identity:

- **The grove** — date palms and leaf canopy. Deep grove greens, chlorophyll gradients and a
  touch of date-gold give the palette its warmth.
- **The viewfinder** — the moment the camera locks onto a leaf. Corner brackets, a sweeping scan
  line and the "scan ring" gauge appear wherever the AI is looking, waiting or reporting.

Behind everything sits a **topographic survey map**: procedurally generated contour rings (every
fifth line heavier, like index contours on a real topo sheet) that turn very slowly over soft pools
of light. It is the one ambient effect in the app, and it is frozen under reduced motion.

## Color tokens
All colors are CSS variables holding RGB channels (`src/index.css`) mapped in
`tailwind.config.ts`, so opacity modifiers (`bg-primary/20`) work and the entire app re-themes by
toggling the `dark` class on `<html>`.

| Token | Light | Dark | Role |
|---|---|---|---|
| `canvas` | `#F2F6F3` morning mist | `#05130E` grove at night | page background |
| `surface` | `#FFFFFF` | `#0C2119` | glass panels (used at 55–72% opacity) |
| `ink` / `muted` | `#0D241B` / `#546B60` | `#E5F1EA` / `#8CA699` | text |
| `primary` | `#158054` chlorophyll | `#38C884` | actions, active states, data |
| `sprout` | `#7ED957` | `#8CE664` | highlights, scan line, gradient ends |
| `accent` | `#D9A33B` date gold | `#E9B752` | brand mark detail, weather, tips |
| `grove` | `#093426` | `#07281D` | dark hero panels |

**Severity colors stay functional.** `mild` (wheat), `moderate` (ochre) and `severe` (rust) are
only ever used for real Mild / Moderate / Severe data — badges, the severity ring, the affected-area
bar, pest confidence — never as decoration.

The brand gradient (`.bg-brand`, `#22A56C → #0A5A3B`) is used for primary buttons, the logo mark,
avatars and the latest data point in charts.

## Typography
- **Readex Pro** (variable) — headings and numbers. Designed for Arabic *and* Latin, so English
  and Arabic headings share one voice instead of Arabic falling back to a system serif.
- **IBM Plex Sans / IBM Plex Sans Arabic** — body text, a true bilingual pair.
- Numbers use tabular figures (`font-data tabular-nums`) so readings line up.
- Fonts are self-hosted via `@fontsource` (no Google Fonts request — works on weak connections).

## Surfaces & shape
- `.glass` — translucent surface with backdrop blur, hairline border and a top highlight.
- Radius encodes hierarchy: panels `1.5rem`, inner items `1rem`, controls `0.75rem`, chips full.
- `.ring-gradient` — gradient hairline border for the one highlighted panel per screen (the result
  hero, the AI analysis).
- Shadows are tinted with the grove color, never neutral grey.

## Motion
Motion answers the person, or orchestrates one moment per page:

- **Buttons**: press scales to 97%; a ripple spreads from the exact press point; on hover the
  button lifts 2px, its glow deepens and a sheen sweeps across; trailing arrows nudge forward
  (mirrored in RTL).
- **Navigation**: a single pill glides between sidebar items, tabs and admin sections
  (`useSlidingIndicator`) instead of each item blinking on/off.
- **Page entrance**: direct children of `.stagger` rise in one after another — once per page.
- **Data**: rings sweep from zero while the number counts up; bars grow from their baseline;
  the sparkline draws itself.
- **AI work**: the scan ring, the scan line and the viewfinder brackets.
- Entrance keyframes end on `transform: none` so finished animations never trap `position: fixed`
  children; modals are additionally portalled to `<body>`.
- Everything respects `prefers-reduced-motion`.

## Layout
- **Desktop**: floating glass sidebar (logo, nav, theme + language + logout, user card) and a
  `max-w-6xl` content column.
- **Mobile**: glass top bar with theme/language toggles; floating bottom bar with a raised,
  pulsing **Scan** button in the middle — the primary action, in thumb reach.
- **RTL**: logical properties throughout (`ps-`, `start-`, `rounded-ss-`…); directional icons use
  `.flip-rtl`; free text that comes from the API uses `dir="auto"` so English content stays readable
  inside the Arabic UI.

## Themes
Light and dark are both first-class. The initial theme follows the OS, the toggle (sidebar,
mobile top bar, sign-in screen, Profile → Appearance) remembers the choice, and an inline script in
`index.html` applies theme and direction before first paint.
