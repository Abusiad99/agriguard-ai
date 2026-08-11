# AgriGuard AI — Deployment Guide 
> ⚠️ **مهم قبل التحميل — هذا المشروع يستخدم Git LFS**
>
> مجلد `datasets/` يحتوي على آلاف صور التدريب المخزّنة عبر **Git LFS** (Git Large File Storage). لازم تتبع الخطوات التالية **بالترتيب** وإلا ستحصل على أخطاء تدريب غامضة (كل الصور تُرفض كـ "تالفة").
>
> **❌ لا تستخدم زر "Download ZIP"** — هذا ينزّل ملفات LFS كـ "pointer files" فارغة (~130 بايت لكل صورة بدل الصورة الفعلية)، وسيفشل التدريب فورًا.
>
> **✅ استخدم `git clone` بدلاً من ذلك:**
>
> ```bash
> # 1) ثبّت Git LFS إذا لم يكن مثبتًا (مرة واحدة فقط على جهازك):
> #    حمّله من https://git-lfs.com
>
> # 2) فعّل Git LFS (مرة واحدة فقط لكل جهاز):
> git lfs install
>
> # 3) استنسخ الريبو (سيُنزّل صور LFS الحقيقية تلقائيًا):
> git clone https://github.com/Abusiad99/agriguard-ai.git
> cd agriguard-ai
> ```
>
> **تحقق أن الصور نزلت بشكل صحيح** (يجب أن يكون الحجم عشرات/مئات الكيلوبايتات وليس ~130 بايت):
>
> ```bash
> # PowerShell (Windows):
> Get-ChildItem -Recurse -Filter *.jpg -Path datasets | Select-Object -First 1 | Get-Item | Select-Object Name, Length
>
> # bash/Linux/macOS:
> ls -la datasets/plantwild_v2/*/*.jpg | head -1
> ```
>
> إذا كان حجم الملف صغيرًا جدًا (~130 بايت)، فهذا يعني أن Git LFS لم يُفعَّل قبل الاستنساخ. الحل:
>
> ```bash
> git lfs install
> git lfs pull
> ```

## 1. Prerequisites
- Docker Engine 24+ and Docker Compose v2 (`docker compose`, not the legacy `docker-compose`).
- A trained model (`python train.py` from the repo root, with datasets placed in `datasets/`)
  if you want the `/api/v1/scans` endpoint to return real diagnoses rather than a
  `SERVICE_UNAVAILABLE` (503) response — the backend starts and serves all other endpoints
  correctly even without a trained model (see `app/main.py`'s startup lifecycle, which logs a
  warning rather than failing to boot).

## 2. First-time setup
```bash
cp .env.example .env
# Edit .env: set JWT_SECRET_KEY (required — the compose file will refuse to start without it),
# POSTGRES_PASSWORD, and CORS_ALLOW_ORIGINS for your frontend's origin.

cd docker
docker compose up --build
```

This starts, in dependency order (via `depends_on` + `condition: service_healthy` /
`condition: service_completed_successfully`):
1. **postgres** (PostgreSQL 16) — healthcheck: `pg_isready`
2. **redis** (Redis 7, AOF persistence) — healthcheck: `redis-cli ping`
3. **backend** (FastAPI) — waits for Postgres to be *reachable* (not just "started"; see
   `docker/scripts/backend-entrypoint.sh`), runs `alembic upgrade head`, then starts
   `uvicorn` with 4 workers. Healthcheck: `GET /health`.
4. **frontend** — a one-shot build container (`docker/frontend.Dockerfile`): compiles the
   React/TypeScript/Tailwind app and copies the static `dist/` output into the shared
   `frontend_dist` volume, then exits 0. There is no long-running Node.js process in
   production — NGINX serves the compiled static files directly.
5. **nginx** — reverse proxy, waits for the backend to be healthy AND the frontend build to
   complete successfully. Healthcheck: `GET /health` through the proxy.

The full app is reachable at `http://localhost/` (frontend, via NGINX), with the API at
`http://localhost/api/v1/...`. The backend is also reachable directly at
`http://localhost:8000/api/v1/...` for local development.
OpenAPI docs: `http://localhost:8000/api/docs`.

To rebuild only the frontend after a source change (without restarting the whole stack):
```bash
docker compose up --build frontend
docker compose restart nginx   # pick up the freshly-populated frontend_dist volume
```

## 3. Running the training pipeline
The training service is **not** part of the default stack (it's a batch job, not a
long-running service — see `docs/02-system-design/11-deployment-diagram.mermaid`). Place
datasets in `../datasets/` (repo root) first, then:
```bash
docker compose --profile training run --rm training
```
Trained artifacts are written to the `artifacts_data` volume, which the `backend` service
also mounts — restart the backend (`docker compose restart backend`) to pick up a newly
trained model (the AI pipeline client loads the latest run lazily on first request, or
eagerly at startup per `app/main.py`'s lifespan hook).

To use a GPU, uncomment the `deploy.resources.reservations.devices` block in
`docker-compose.yml`'s `training` service (requires the NVIDIA Container Toolkit on the host).

## 4. Database migrations
- **Startup strategy**: `docker/scripts/backend-entrypoint.sh` runs `alembic upgrade head`
  automatically every time the `backend` container starts, before the API server launches.
  This is safe to run repeatedly — Alembic no-ops if the schema is already at the latest
  revision.
- **Creating a new migration** (after modifying SQLAlchemy models):
  ```bash
  cd backend
  alembic revision --autogenerate -m "describe the change"
  # review the generated migration, then:
  alembic upgrade head
  ```
- **Manual migration commands** inside a running container:
  ```bash
  docker compose exec backend alembic current
  docker compose exec backend alembic history
  docker compose exec backend alembic downgrade -1
  ```

## 5. Health checks
| Service | Check | Interval |
|---|---|---|
| postgres | `pg_isready -U agriguard -d agriguard` | 10s |
| redis | `redis-cli ping` | 10s |
| backend | `curl -f http://localhost:8000/health` | 30s |
| frontend | (one-shot build; `service_completed_successfully` gates nginx startup) | n/a |
| nginx | `wget --spider http://localhost/health` | 30s |

`GET /health` returns `{"status", "database", "cache", "ai_service"}` — `database: "down"`
returns HTTP 503 (used by the healthcheck); `ai_service: "degraded"` means no trained model
is loaded yet but the rest of the API is fully functional.

## 6. Production notes
- **TLS**: this `nginx.conf` terminates plain HTTP on port 80 for local/staging use. For
  production, either (a) add a `listen 443 ssl;` server block with certificates (e.g. via
  Let's Encrypt/certbot, mounted as a volume), or (b) terminate TLS at an upstream load
  balancer (ALB/Cloud Load Balancer) and keep NGINX on HTTP behind it — either is a small,
  additive change to `docker/nginx/nginx.conf` and does not require any application code
  changes, since `SecurityHeadersMiddleware` already adds `Strict-Transport-Security` when
  `APP_ENV=production`.
- **Secrets**: `JWT_SECRET_KEY` and `POSTGRES_PASSWORD` are read from `.env` (never committed
  — see `.gitignore`/`.dockerignore`). In a real production deployment, prefer your
  orchestrator's secret store (Docker Swarm secrets, Kubernetes Secrets, or a cloud secrets
  manager) over a plain `.env` file.
- **Scaling**: the `backend` service is stateless (NFR-SCALE-1) — scale horizontally with
  `docker compose up --scale backend=3`; NGINX's `upstream backend_upstream { server
  backend:8000; }` automatically round-robins across replicas via Docker's embedded DNS.
- **Ports exposed for local dev only**: `postgres:5432` and `backend:8000` are published to
  the host for convenience. Remove their `ports:` mappings in a production compose override
  so only NGINX (port 80/443) is internet-facing.
