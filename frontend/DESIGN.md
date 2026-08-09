# AgriGuard AI — Frontend Design Rationale

## Subject & Primary User
The primary persona (Phase 1: "Farmer Youssef") uses this app outdoors, on a phone, in bright
midday light, often not tech-savvy. The secondary persona (agronomist/admin) uses it indoors on a
larger screen to review data. The design serves both without compromising either: a mobile-first
utility app, not a marketing site.

## Why Not the Generic AI-Template Look
Two defaults were deliberately avoided:
- **Cream/off-white (#F4F1EA) + warm clay/terracotta (#D97757) + Inter everywhere** — the most
  common "AI product" palette right now. Reusing it would make AgriGuard AI look like every other
  generated app rather than a purpose-built agricultural tool.
- **Rounded-2xl cards + drop-shadow-everywhere** — a generic SaaS-dashboard visual language with
  no connection to the subject matter.

## The Actual Palette: "Midday Field-Inspection"
Grounded in the literal moment of use — a farmer inspecting a leaf at noon, not a golden-hour
marketing photo:
- **Canvas** `#F7F5EE` — a cooler, greener linen-white than the cliché cream, reads as a field
  notebook page.
- **Ink** `#1C2B22` — deep bottle-green-black instead of pure black, evokes wet soil/foliage
  shadow.
- **Primary** `#2F6B4F` — a confident, desaturated leaf green for actions/navigation.
- **Severity scale** — `mild` wheat-gold `#D8A73D`, `moderate` burnt ochre `#C8722A`, `severe`
  rust `#A13D2C`. This is the one place warm color appears, and it is used **only** functionally,
  always tied to real severity data (never decoratively) — this is the "structure is information"
  principle applied directly to the disease-severity domain.
- **Line/border** `#D8DCC9` — a muted sage hairline used as the primary depth cue instead of drop
  shadows (a "printed field-guide card" feel; shadows are reserved for actual overlays like
  modals).

## Typography
- **Fraunces** (display/headings) — a warm serif with real character (variable optical size),
  giving page titles and numerals an "almanac/seed-catalog" feel rather than generic
  sans-everywhere.
- **IBM Plex Sans / IBM Plex Sans Arabic** (body) — a genuine bilingual pairing, not a decorative
  choice: switching locale swaps to a true companion typeface in the same family, so Arabic and
  English content look visually consistent rather than Arabic being an afterthought rendered in a
  mismatched fallback font.
- **IBM Plex Mono** (data) — used specifically for confidence percentages, dates, and counts,
  reinforcing the "instrument reading" nature of diagnostic numbers.

## Signature Motif: the Scan Ring
`components/ui/ProgressRing.tsx` is the one recurring, memorable element — a radial gauge used for
confidence % (Dashboard stat, Diagnosis Result), severity (Diagnosis Result), and the scanning
animation during AI analysis (Scan page). It is functional in every appearance (always bound to
real data), never purely decorative, and ties the whole app together visually.

## Layout
- **Desktop**: fixed left sidebar (icon + label nav) + card-based main content — a utility-app
  pattern, not a hero-driven landing page.
- **Mobile**: bottom tab bar, thumb-reachable, since the primary action (scanning) happens
  outdoors, often one-handed.
- **RTL**: `dir="rtl"` is set on `<html>` when Arabic is active; all layout uses logical Tailwind
  properties (`ps-`/`pe-`/`start-`/`end-` instead of `pl-`/`pr-`/`left-`/`right-`) so the mirrored
  layout is correct, not just text-direction-flipped.
