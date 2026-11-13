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
[DATASET_SETUP_GUIDE.md](DATASET_SETUP_GUIDE.md) for the data each feature needs and how to
train the models.

Everything runs **natively on Windows — Docker is not required**. (Docker
Compose remains available as an optional deployment method; see
[docker/README.md](docker/README.md).)

> **New to the project?** Follow **[docs/SETUP_AND_RUN.md](docs/SETUP_AND_RUN.md)**: the
> complete step-by-step Windows guide (prerequisites, PostgreSQL, API keys, AI models,
> one-command startup, database backup, tests and troubleshooting). It is the only setup guide.

| Folder | What it is |
|---|---|
| `backend/` | FastAPI API, Alembic migrations, tests |
| `ai/` | Training and inference pipelines: classifier (`train.py`, `inference.py` at the repo root), `ai/segmentation/`, `ai/outbreak/`, `ai/recovery/`, `ai/registry.py` |
| `configs/` | Configs for segmentation, outbreak and recovery pipelines |
| `frontend/` | React + TypeScript + Tailwind app |
| `scripts/` | PowerShell scripts for installing, running and testing |
| `datasets/` | Training images (Git LFS), plus `segmentation/`, `outbreak/`, `recovery/` packages (READMEs and schemas only; your data stays local) |
| `docs/` | Requirements, system design, feature, dataset, setup and testing guides |

## Getting started

| I want to | Read |
|---|---|
| Install and run the app for the first time (Windows) | **[docs/SETUP_AND_RUN.md](docs/SETUP_AND_RUN.md)** |
| Add my datasets and train the models | **[DATASET_SETUP_GUIDE.md](DATASET_SETUP_GUIDE.md)** |
| Run it with Docker instead | [docs/SETUP_AND_RUN.md, section 9](docs/SETUP_AND_RUN.md#9-docker-optional) |

After the first-time setup, these are the commands you use (from the repository folder):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1         # start backend + frontend, then open http://127.0.0.1:5173 (Ctrl+C stops them)
powershell -ExecutionPolicy Bypass -File scripts\test.ps1        # all automated checks
powershell -ExecutionPolicy Bypass -File scripts\backup-db.ps1   # back up the database (before every migration)
```

**No trained model is included.** Until you train the classifier
([DATASET_SETUP_GUIDE.md](DATASET_SETUP_GUIDE.md)), a scan answers 503 "model not available"
and `/health` reports `ai_service: degraded`; everything else works, and no diagnosis is
ever made up.

Configuration lives in `.env` (created from [.env.example](.env.example) by the install
script, git-ignored; never commit it). The settings are explained in
[docs/SETUP_AND_RUN.md, section 4.3](docs/SETUP_AND_RUN.md).

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
