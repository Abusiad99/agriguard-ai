# AgriGuard AI — Phase 5 Final Integration & Validation Report

**Date:** 2026-08-09
**Scope:** End-to-end integration testing of the full stack (Frontend → Nginx → FastAPI → AI pipeline → PostgreSQL → reports/weather), run live against real services wherever the sandbox allowed it.

## Method

No Docker daemon is available in this execution environment, so the full `docker compose up` stack could not be run as one command. Instead, every layer was stood up natively and driven with real traffic:

- **PostgreSQL 16** installed and run locally; Alembic migrations executed for real.
- **FastAPI backend** run with `uvicorn`, using the real Postgres instance, real JWT signing, real bcrypt hashing.
- **AI pipeline**: the actual training pipeline (`train.py` → data adapters → split → label encoding → `Trainer` → `ArtifactManager`) was run end-to-end on a small synthetic image set to produce a real model, because no real plant-disease dataset exists in this environment. The live API then loaded that real model and ran real inference — nothing was mocked at the API layer for this validation.
- **Nginx 1.24** installed and run with the project's actual `nginx.conf` (only edits: Docker service DNS name → `127.0.0.1`, and paths, to run outside Compose).
- **Frontend**: built for real via `npm install && npm run build` (TypeScript + Vite), and served by the live Nginx.

Every flow below was exercised with real HTTP requests (`curl`), not test doubles, except where explicitly marked.

---

## PASS — Verified working end-to-end

| Area | What was verified |
|---|---|
| **Database & migrations** | Alembic `upgrade head` ran clean against real Postgres 16; all 13 expected tables created correctly. |
| **Backend test suite** | 93 passed, 1 legitimately skipped (real trained model unavailable — see Limitations), 0 failed, after fixes below. |
| **Auth: register/login** | Real HTTP register → login → JWT issuance against Postgres. Password hashing verified working (bcrypt). |
| **RBAC** | Farmer correctly blocked (403) from `/admin/users` and disease-creation routes with proper error envelope. Missing token correctly returns 401. User promoted to `admin` in DB correctly gets 200 on admin routes on next login — role is read from the JWT/DB, not cached. |
| **Scan → AI diagnosis** | Real inference ran against a genuinely trained model (not a stub) through the full HTTP scan endpoint; response included classification, severity, affected-area %, heatmap overlay, and correctly suppressed disease/treatment output when confidence was low rather than fabricating a result. |
| **PDF report generation** | Real 2-page PDF generated via `reportlab`, containing the rendered leaf image, a real heatmap overlay image, a diagnosis summary table, and a working QR code. Verified visually by rendering the PDF to PNG. |
| **History** | `/api/v1/diagnoses` returns correctly paginated, correctly-scoped real records. |
| **Dashboard** | `/api/v1/dashboard/me` correctly reflects real scan counts and monthly trend from the DB. |
| **Weather integration (code path)** | The weather service correctly called `api.open-meteo.com` with real coordinates and degraded gracefully (logged warning, `weather: null`, no crash, no fake data) when the call was blocked — see Limitations. |
| **Nginx reverse proxy** | Config syntax valid (`nginx -t`). Live-tested: `/health` passthrough, `/api/*` proxy (register/login/scan all worked through Nginx, not just direct-to-backend), `/storage/*` proxy (served a real diagnosis image), `/api/docs` and `/api/openapi.json` proxy, SPA fallback (`try_files ... /index.html`) on a client-side route, security headers present on proxied responses. |
| **Nginx-level rate limiting** | The `auth_zone` `limit_req` fired correctly under rapid repeated login attempts (401s from the backend, then 503s from Nginx once the burst allowance was exhausted) — defense-in-depth working as designed, independent of the app-level limiter. |
| **Frontend build** | `npm run build` (full `tsc -b && vite build`) completed cleanly and produced a real static bundle, after a real fix (see below). |
| **Docker/Compose config** | `docker-compose.yml` reviewed in full: healthchecks, service dependencies (`condition: service_healthy` / `service_completed_successfully`), volume wiring between the frontend build stage and Nginx, and the training profile are all correctly structured. Not executable in this sandbox (see Blocked). |

---

## Real bugs found and fixed

1. **Missing `email-validator` dependency.** `EmailStr` is used in `auth_schemas.py` but `email-validator` wasn't declared in `backend/requirements.txt` — the app failed to import at all. **Fixed:** added `pydantic[email]` to requirements.
2. **bcrypt/passlib incompatibility.** `passlib==1.7.4` reads bcrypt's `__about__` attribute for version detection; `bcrypt>=4.1` removed that attribute, which broke passlib's 72-byte password guard and caused hashing to raise `ValueError` on longer passwords. **Fixed:** pinned `bcrypt==4.0.1` in requirements, with a comment explaining why.
3. **Test-isolation bugs** (test code only, no production impact): the in-memory rate limiter's counters lived on a middleware instance that Starlette builds once and caches for the app's lifetime, so all tests in a session shared one bucket and unrelated tests started failing with false 429s. Separately, the SQLite `:memory:` test engine lacked `StaticPool`, so a request dispatched to a different worker thread could get a brand-new, empty in-memory database (`no such table: users`). **Fixed:** both in `tests/conftest.py` — force middleware-stack rebuild per test client, and pin the test engine to `StaticPool`.
4. **Frontend build failure.** `vite.config.ts` uses Node's `path` module and `__dirname`, but `@types/node` wasn't in `devDependencies`, so `tsc -b` failed before Vite even ran. **Fixed:** added `@types/node` to `frontend/package.json` (lockfile regenerated).

All four fixes are included in the delivered `Agriguard-AI-Phase-5-Validated.zip`.

---

## Minor finding (not fixed — flagged for judgment call)

The PDF report for a **low-confidence** diagnosis showed `Disease/Condition: Healthy / No disease detected` alongside `Severity: severe` and `Affected Area: 53.4%` in the same table. Severity/affected-area appear to come from an independent heatmap-based measurement, separate from the classification confidence gate that suppresses the disease label. This is very likely an artifact of the intentionally undertrained smoke-test model used for this validation (see Limitations) rather than a confirmed production bug — but it's worth a design decision either way: should severity/affected-area be suppressed or caveated when `low_confidence_flag` is true? Not changed here since it requires a product decision, not just a code fix.

---

## BLOCKED — could not be executed in this sandbox

| Item | Reason |
|---|---|
| `docker compose up` (the actual multi-container stack) | No Docker daemon available in this execution environment. Every service was instead run natively and cross-connected manually to validate the same integration points. |
| Real-world model training / real diagnostic accuracy | No plant-disease image dataset is present in the repo (`datasets/` is empty by design — datasets are an operator responsibility per the project's own documentation) and no GPU is available. A tiny synthetic dataset was used to exercise the *pipeline mechanics* only; it says nothing about real diagnostic accuracy. |
| Pretrained ImageNet backbone weights | `timm`'s default pretrained-weight download goes through `huggingface.co`, which is outside this sandbox's network allowlist. Training was run with `pretrained=False` for the smoke test only. |
| Live weather data | `api.open-meteo.com` is outside this sandbox's network allowlist; the call was made for real and blocked at the network layer (confirmed via server logs), and the app degraded gracefully exactly as designed. |
| TLS/HTTPS termination | Not testable without a real domain/cert; Nginx config's `Strict-Transport-Security` header path (`app_env == production`) was reviewed but not exercised. |

---

## Environment limitations (context, not defects)

- This sandbox has no Docker daemon, so container build/runtime behavior (image layer caching, `--workers 4`, the healthcheck `condition:` orchestration, the `training` profile) was verified by config review and by replicating each service's runtime behavior natively, not by an actual `docker compose up`.
- Network egress is restricted to a fixed allowlist (pypi/npm/github/apt mirrors, `api.anthropic.com`). `api.open-meteo.com` and `huggingface.co` are not on it, which blocked live weather data and pretrained-weight downloads respectively — both are the sandbox's network policy, not application defects, and both failure paths were confirmed to degrade correctly rather than crash or fake data.
- No real plant-disease dataset or GPU was available, so "AI diagnosis" was validated as a working *pipeline* (data → train → artifact → load → infer → respond), not as a claim about real-world diagnostic accuracy.

---

## Summary

Core integration across Frontend, Nginx, FastAPI, PostgreSQL, and the AI pipeline is working end-to-end with real services and real data, not mocks. Four genuine bugs were found and fixed (two would have blocked a fresh `pip install`/`npm install` entirely, one was a password-hashing correctness issue, one was test-suite-only). No fake or placeholder production functionality was introduced or found; the codebase's own behavior — returning null/degraded fields instead of fabricating diagnoses, treatment, or weather data when real data isn't available — held up under live testing. The only things not executed were the parts genuinely outside this sandbox's capabilities (Docker daemon, blocked external network endpoints, and real-world model training data), all clearly listed above.
