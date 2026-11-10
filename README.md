# AgriGuard AI

AI-powered plant disease detection, severity assessment and crop monitoring: a
FastAPI backend with a PyTorch computer-vision pipeline, a React/Vite frontend, and
PostgreSQL. English and Arabic UI.

It also includes three AI features. Each one reports whether its model is ready, and none of
them shows results from a model that doesn't exist:

| Feature | What it does | Status |
|---|---|---|
| [Disease localization](docs/features/disease-localization.md) | A separate segmentation model outlines lesions and measures the affected share of the leaf | Software complete; **needs a pixel-annotated dataset and training** |
| [Plant recovery monitoring](docs/features/plant-recovery-monitoring.md) | Track a plant over time: follow-up scans, user-recorded treatments, reminders, comparison and an explained recovery status | Software complete; measured change needs the localization model |
| [Outbreak risk map](docs/features/outbreak-prediction.md) | Area-level map of observed cases and a 3/7/14-day risk estimate with weather, using privacy-preserving grid cells | Software complete; **needs historical inspection data and training** |
| [Agricultural reports](docs/features/reports.md) | Versioned diagnosis, plant-progress and regional-risk assessments built from stored records: typed evidence, model test results next to confidence, explained visuals, recovery comparability, risk explanations, recommendations with a stated basis and verified references, PDF (English/Arabic), print, expiring share links, archive and compare | Software complete; content is only as good as the models, their test results and the knowledge base |

None of these models has been trained or evaluated on real data in this repository, and
nothing here is production-ready on the strength of automated tests alone. See
[docs/ai/model-registry.md](docs/ai/model-registry.md) for how readiness is reported and
[docs/datasets/dataset-preparation-guide.md](docs/datasets/dataset-preparation-guide.md)
for the data each feature needs.

This guide runs everything **natively on Windows — Docker is not required**. (Docker
Compose remains available as an optional deployment method; see
[docker/README.md](docker/README.md).)

> **New to the project?** Follow **[docs/SETUP_AND_RUN.md](docs/SETUP_AND_RUN.md)**: the
> complete step-by-step Windows guide (prerequisites, PostgreSQL, API keys, AI models,
> one-command startup, tests and troubleshooting). The sections below are a summary.

| Folder | What it is |
|---|---|
| `backend/` | FastAPI API, Alembic migrations, tests |
| `ai/` | Training and inference pipelines: classifier (`train.py`, `inference.py` at the repo root), `ai/segmentation/`, `ai/outbreak/`, `ai/recovery/`, `ai/registry.py` |
| `configs/` | Configs for segmentation, outbreak and recovery pipelines |
| `frontend/` | React + TypeScript + Tailwind app |
| `scripts/` | PowerShell scripts for installing, running and testing |
| `datasets/` | Training images (Git LFS), plus `segmentation/`, `outbreak/`, `recovery/` packages (READMEs and schemas only; your data stays local) |
| `docs/` | Requirements, system design, feature, dataset, setup and testing guides |

## Prerequisites

- **Python 3.10+** (3.11 or 3.12 recommended) — https://www.python.org/downloads/windows/
- **Node.js 18+** (LTS) — https://nodejs.org/
- **PostgreSQL 14+** running locally — https://www.postgresql.org/download/windows/
- **Git LFS**, only if you want the training images: `git lfs install` before cloning
  (see the note in [docker/README.md](docker/README.md))

Not required: Docker, Redis (nothing uses it yet), NGINX (the backend applies its own
security headers and rate limits; the Vite dev server proxies the API).

## Quick start (Windows PowerShell)

Run these from the repository root. The scripts are written for Windows PowerShell
5.1 and PowerShell 7. If script execution is disabled on your machine, run each one
as `powershell -ExecutionPolicy Bypass -File scripts\<name>.ps1` (as below) instead
of changing the system policy.

```powershell
# 0. Clone. The first line skips 1.7 GB of training images (only needed for training).
#    Use Git 2.45.2+; with 2.45.1, run "git restore --source=HEAD :/" in the folder if the clone stops.
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://github.com/Abusiad99/agriguard-ai.git
cd agriguard-ai

# 1. Database (once): create a role and a database, as the postgres superuser.
#    Choose your own password instead of YOUR_DB_PASSWORD.
psql -U postgres -c "CREATE ROLE agriguard LOGIN PASSWORD 'YOUR_DB_PASSWORD';"
psql -U postgres -c "CREATE DATABASE agriguard OWNER agriguard;"

# 2. Install (creates .venv and .env with a random JWT secret), then put your
#    database password into DATABASE_URL in .env
powershell -ExecutionPolicy Bypass -File scripts\install-backend.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-frontend.ps1
notepad .env

# 3. Database schema
powershell -ExecutionPolicy Bypass -File scripts\check-db.ps1
powershell -ExecutionPolicy Bypass -File scripts\migrate.ps1

# 4. Run both (Ctrl+C stops them); open http://127.0.0.1:5173
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

#    ...or one at a time, in the background
powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1    # http://127.0.0.1:8000/api/docs
powershell -ExecutionPolicy Bypass -File scripts\start-frontend.ps1   # http://127.0.0.1:5173

# 5. Stop servers started in the background
powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
```

If your PostgreSQL user, host or port differ, edit `DATABASE_URL` in `.env` as well.

### Scripts

| Script | What it does |
|---|---|
| `install-backend.ps1` | Creates the virtual environment, installs `backend/requirements.txt` and `ai/requirements.txt` (PyTorch is a large download; `-SkipAi` skips it), and creates `.env` from `.env.example` if missing |
| `install-frontend.ps1` | `npm ci` in `frontend/` |
| `check-db.ps1` | Connects to `DATABASE_URL`; reports the server version and migration revision. Read-only |
| `migrate.ps1` | `alembic upgrade head`. Also `-Action current`, `-Action history`, and `-Action downgrade -Revision <rev>` (never implicit) |
| `dev.ps1` | Checks the setup and the database, starts backend and frontend, prints the URLs; Ctrl+C stops what it started (`-Detach` leaves them running) |
| `check-gemini.ps1` | Checks the optional `GEMINI_API_KEY` with one model lookup; never prints the key |
| `start-backend.ps1` | Uvicorn with auto-reload on 127.0.0.1:8000, in the background (logs in `logs\`). `-Foreground` runs it in the current window |
| `start-frontend.ps1` | Vite dev server on 127.0.0.1:5173, proxying `/api` (and `/storage`, which serves files only with `LEGACY_PUBLIC_MEDIA=true`) to the backend (`$env:AGRIGUARD_API_URL` overrides the target). `-Foreground` available |
| `stop-dev.ps1` | Stops only the processes the two start scripts recorded (by process id and start time), with their child processes. Never touches the database |
| `test.ps1` | Backend pytest + frontend lint, type check, unit tests and build. `-PostgresUrl <url>` runs the database tests on PostgreSQL |
| `segmentation.ps1`, `outbreak.ps1`, `recovery-data.ps1` | Validate / preprocess / train / evaluate / status for the AI features (`-Action`, plus `-Extra "<args>"` with all extra options in one quoted string, e.g. `-Extra "--epochs 30 --device cuda"`). Training is never started by anything else |

The virtual environment defaults to `.venv\`. If the repository sits in a very deep
folder and pip fails with path-length errors, set `$env:AGRIGUARD_VENV` to a shorter
path (e.g. `C:\venvs\agriguard`) before running the scripts.

## Configuration

`.env` (from [.env.example](.env.example)) is the local development configuration.
It is git-ignored; never commit it or put production secrets in it. Notable settings:

- `DATABASE_URL` — `postgresql+psycopg2://agriguard:YOUR_DB_PASSWORD@127.0.0.1:5432/agriguard`
  (replace the placeholder with your PostgreSQL password)
- `JWT_SECRET_KEY` — generated by `install-backend.ps1`
- `GEMINI_API_KEY` — optional; empty disables the Gemini explanation layer and AI-worded
  report summaries (reports then use a template summary)
- `MEDIA_URL_TTL_SECONDS` / `LEGACY_PUBLIC_MEDIA` — scan photos and heatmaps are private and
  served through signed links that expire (default 1 hour). The old public `/storage/...`
  paths are off unless `LEGACY_PUBLIC_MEDIA=true`
- Storage, logs and model artifacts default to `storage\`, `logs\` and `artifacts\`
  under the repository root

The Docker deployment has its own template, [docker/.env.example](docker/.env.example).

## The AI model

Scans need a trained model. Until one exists, `POST /api/v1/scans` answers 503 and
`/health` reports `ai_service: degraded`; everything else works.

```powershell
.venv\Scripts\python.exe train.py      # reads datasets\, writes artifacts\runs\<timestamp>_<arch>\
```

Restart the backend afterwards to load the new model. `AGRIGUARD_ARCHITECTURE`,
`AGRIGUARD_DEVICE`, `AGRIGUARD_NUM_EPOCHS` etc. in `.env` control training.

The localization and outbreak models are trained separately. Their commands are in the
feature docs, and they are picked up without a restart. **Admin → AI models** shows what is
installed. More setup detail: [docs/development/local-setup.md](docs/development/local-setup.md).

## Tests

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
```

- Backend tests run on in-memory SQLite by default — no database needed.
- To run the database tests and the Alembic migration tests on real PostgreSQL,
  create a throwaway database whose name ends in `_test` (the tests drop and
  recreate everything in it) and pass its URL:

  ```powershell
  psql -U postgres -c "CREATE DATABASE agriguard_test OWNER agriguard;"
  powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -PostgresUrl postgresql+psycopg2://agriguard:YOUR_DB_PASSWORD@127.0.0.1:5432/agriguard_test
  ```

Feature tests generate clearly marked synthetic data in temporary folders. They never touch
`datasets/` or `artifacts/`. The manual browser checklist is in
[docs/testing/feature-verification.md](docs/testing/feature-verification.md).

Tests that genuinely need external infrastructure skip themselves with a reason:
`test_migrations_postgres.py` (needs the PostgreSQL URL above) and the trained-model
inference test (needs a model from `train.py`). The Gemini and weather tests mock
their external services.

## External services at runtime

| Feature | Needs | Without it |
|---|---|---|
| Everything | PostgreSQL | API returns 503 from `/health`; most endpoints fail |
| Scans / diagnosis | A trained model (`train.py`) | `POST /scans` returns 503 |
| Weather and spraying conditions | Internet access to api.open-meteo.com (no key) | Diagnosis completes without weather; the spraying check says "Not assessed" |
| Disease localization | A trained segmentation model | Scans record "waiting for a model"; diagnosis unaffected |
| Outbreak estimates | A trained outbreak model + Open-Meteo (forecast and archive APIs) | Map shows observed cases; estimates report *model not ready* / *insufficient data* |
| Outbreak map tiles | Browser access to tile.openstreetmap.org | Cells still listed; no base map |
| AI explanation | `GEMINI_API_KEY` and internet access | Section omitted; diagnosis unaffected |
| AI-worded report summary | `GEMINI_API_KEY` and internet access | Deterministic template summary; the rest of the report is unchanged |
| Password reset by email | Not implemented yet (the `SMTP_*` settings are reserved) | — |

## Optional: Docker

`docker/docker-compose.yml` still deploys the full stack (PostgreSQL, backend, NGINX,
frontend build, optional training job). It was built and run end to end on Docker Desktop
4.85 (November 2026). Commands and notes:
[docs/SETUP_AND_RUN.md, section 9](docs/SETUP_AND_RUN.md#9-docker-optional); details in
[docker/README.md](docker/README.md).

```powershell
cd docker
Copy-Item .env.example .env; notepad .env     # set JWT_SECRET_KEY and POSTGRES_PASSWORD
docker compose up -d --build                  # app: http://localhost  API docs: http://localhost:8000/api/docs
docker compose down                           # stop (keeps the data)
```
