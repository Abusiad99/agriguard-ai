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
```bash
npm install
npm run dev        # http://localhost:5173, proxies /api and /storage to :8000 (see vite.config.ts)
```
The backend (Phase 3) must be running at `http://localhost:8000` — see `backend/README`
equivalent instructions in `docker/README.md`, or run it directly:
```bash
cd ../backend
uvicorn app.main:app --reload
```

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

## Known environment limitation (disclosed, not hidden)
This project was built in a sandboxed environment with no network access to the npm registry, so
`npm install` / `npm run build` / `npm run typecheck` could not be executed here. Every file was
written by hand with careful attention to the TypeScript types and React/Router APIs involved, and
cross-checked against the backend's actual schemas and routes (see the Phase 4 validation report).
Run `npm install && npm run typecheck && npm run build` in a networked environment to get a real
compiler-verified pass before deploying.
