# AgriGuard AI — Frontend

React + TypeScript + Tailwind CSS frontend for the AgriGuard AI backend (Phase 3).

## Stack
- **React 18** + **TypeScript** (strict mode) + **React Router v6**
- **Tailwind CSS** with a custom design token system (see [`DESIGN.md`](./DESIGN.md))
- **Vite** for dev server / build
- No data-fetching or i18n library dependency — both are hand-rolled
  (`src/hooks/useAsync.ts`, `src/context/LocaleContext.tsx`) to keep the dependency
  surface minimal and fully auditable for a project this size.

## Running locally
No Docker or NGINX is needed. From the repository root (see the root
[README.md](../README.md) for the full setup):
```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-frontend.ps1   # npm ci
powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1      # API on 127.0.0.1:8000
powershell -ExecutionPolicy Bypass -File scripts\start-frontend.ps1     # http://127.0.0.1:5173
```
Or by hand: `npm ci` then `npm run dev`. The dev server proxies `/api` and `/storage`
to `http://127.0.0.1:8000` (see `vite.config.ts`); set `AGRIGUARD_API_URL` to point it
elsewhere.

## Type checking & build
```bash
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm run build        # tsc -b && vite build -> dist/
```

## Project structure
```
src/
  types/api.ts          # TypeScript types mirroring backend Pydantic schemas exactly
  lib/apiClient.ts       # fetch wrapper: auth header injection, error parsing, token refresh
  lib/endpoints/         # one module per backend router (auth, scans, dashboard, admin, ...)
  lib/tokenStorage.ts     # access token in memory, refresh token in localStorage
  context/                # AuthContext, LocaleContext (i18n + RTL)
  hooks/useAsync.ts       # minimal dependency-free data-fetching hook
  components/ui/          # reusable primitives (Button, Card, Input, Modal, ProgressRing, ...)
  components/layout/      # AppShell (sidebar/tab-bar), AuthLayout, AdminLayout
  components/diagnosis/   # diagnosis-result sub-components (severity, weather, treatment, ...)
  routes/                 # ProtectedRoute, GuestRoute, RoleRoute
  pages/                  # one file per route
  i18n/                   # en.ts / ar.ts dictionaries
  utils/                  # format.ts, validators.ts
```

## API integration
Every network call goes through `src/lib/apiClient.ts`'s `request()`/`requestBlob()` — there is
no mock or fake API anywhere in this codebase. Endpoint modules under `src/lib/endpoints/` map
1:1 to the FastAPI routers in `backend/app/interface/api/v1/`, and `src/types/api.ts` mirrors the
backend's Pydantic response/request schemas field-for-field so a backend contract change surfaces
as a TypeScript type error rather than a silent runtime mismatch.

## Internationalization
English and Arabic are supported via `LocaleContext`, which also flips `<html dir>` for true RTL
layout (not just mirrored text) — see `DESIGN.md`'s RTL section for the logical-properties
convention used throughout.

## Status of the checks
`npm run typecheck` and `npm run build` pass on Node.js 22 / Windows. `npm run lint`
currently fails on pre-existing issues (one unused `eslint-disable` directive in
`src/hooks/useAsync.ts`, plus five warnings — `react-refresh/only-export-components`
and one `react-hooks/exhaustive-deps` in `AuthContext.tsx` — which fail under
`--max-warnings 0`). There is no frontend unit-test suite yet.

`tsc -b` writes its build info under `node_modules/.tmp/`, so no generated
`vite.config.js` sits next to `vite.config.ts` (Vite would load a stale `.js` first).
