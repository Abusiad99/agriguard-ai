# AgriGuard AI — Setup and Run Guide (Windows)

This guide takes you from a fresh Windows 10/11 machine to a running AgriGuard AI: a
FastAPI backend, a React/Vite frontend and a PostgreSQL database. Every command was run
on Windows 11 with Windows PowerShell 5.1, Python 3.11/3.12, Node.js 22, npm 10 and
PostgreSQL 16, including a complete run-through from a fresh `git clone` of GitHub's `main`.
Docker is **not** needed (it is an optional alternative, section 9).

Run all commands from the repository folder (`agriguard-ai`) unless a step says otherwise.

---

## Quick start

### What you need

| Software | Version | Required? |
|---|---|---|
| Git | **2.45.2 or newer** (2.45.1 has a clone bug, section 2.1) | Yes |
| Python | **3.11 or 3.12** (3.10 also works) | Yes |
| Node.js (includes npm) | **18 or newer** (LTS recommended) | Yes |
| PostgreSQL | **14 or newer** (16 tested) | Yes |
| VS Code | any | Optional |
| Docker Desktop | — | Not needed (optional deployment only) |

| API key / account | Required? |
|---|---|
| Gemini API key (`GEMINI_API_KEY`) | **Optional.** Adds an AI explanation to diagnoses and lets reports have an AI-worded summary |
| Weather (Open-Meteo) | No key needed; needs internet access |
| Anything else | Nothing else is used |

### First-time installation

```powershell
# 1. Get the code (the first line skips 1.7 GB of training images you don't need to run the app)
$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://github.com/Abusiad99/agriguard-ai.git
cd agriguard-ai

# 2. Create the database user and database (as the PostgreSQL superuser "postgres").
#    Replace YOUR_DB_PASSWORD with a password you choose. Section 3 has the details.
psql -U postgres -c "CREATE ROLE agriguard LOGIN PASSWORD 'YOUR_DB_PASSWORD';"
psql -U postgres -c "CREATE DATABASE agriguard OWNER agriguard;"

# 3. Install the backend (creates .venv\ and .env) and the frontend packages
powershell -ExecutionPolicy Bypass -File scripts\install-backend.ps1
powershell -ExecutionPolicy Bypass -File scripts\install-frontend.ps1

# 4. Put your database password into .env (replace YOUR_DB_PASSWORD in DATABASE_URL)
notepad .env

# 5. Check the database and create the tables
powershell -ExecutionPolicy Bypass -File scripts\check-db.ps1
powershell -ExecutionPolicy Bypass -File scripts\migrate.ps1

# 6. Start everything
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

Then open **http://127.0.0.1:5173** and create an account with **Sign up**.

### Daily startup

```powershell
cd agriguard-ai
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

`dev.ps1` checks your setup and the database, starts the backend and the frontend, and
prints their addresses. Keep the window open. PostgreSQL normally runs as a Windows service
and starts with Windows (section 3.2 shows how to check).

### Stopping

- If `dev.ps1` is running in a window: press **Ctrl+C** in that window.
- If you started the servers in the background (`dev.ps1 -Detach`, `start-backend.ps1`,
  `start-frontend.ps1`):

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
  ```

Neither touches the database.

### Is it working?

| Check | Expected |
|---|---|
| http://127.0.0.1:8000/health | `{"status":"ok","database":"ok",...}` |
| http://127.0.0.1:8000/api/docs | The interactive API documentation (Swagger UI) |
| http://127.0.0.1:5173 | The AgriGuard sign-in page |
| Sign up, then open **Dashboard**, **History**, **My plants**, **Outbreak risk**, **Reports** | Each page loads |
| **Scan Plant** → upload a photo | Works only with a trained model. Without one you get a "model not available" error (section 8) |

`"ai_service":"degraded"` in `/health` is normal on a fresh install: it means no image
classifier has been trained yet (section 8).

---

## 1. Prerequisites

### 1.1 Install

| Software | Where to get it | Notes |
|---|---|---|
| Git | https://git-scm.com/download/win | Default options are fine. Use 2.45.2 or newer (`git --version`) |
| Python 3.12 or 3.11 | https://www.python.org/downloads/windows/ | Tick **"Add python.exe to PATH"**. Python 3.13+ is not what the scripts look for first; they choose 3.12, then 3.11, then 3.10 |
| Node.js LTS | https://nodejs.org/ | npm is included |
| PostgreSQL | https://www.postgresql.org/download/windows/ | Use the EDB installer. Remember the password you give the `postgres` superuser |
| Git LFS (optional) | https://git-lfs.com | Only if you want the training images in `datasets/` (section 2.2) |
| VS Code (optional) | https://code.visualstudio.com/ | Any editor works |

### 1.2 Verify

Open a **new** PowerShell window (so it sees the updated PATH) and run:

```powershell
git --version
node --version
npm --version
python --version
py -0p            # lists every installed Python version (Python launcher)
psql --version
```

### 1.3 PATH problems

| Message | Fix |
|---|---|
| `python : The term 'python' is not recognized` | Re-run the Python installer, choose **Modify**, and enable **Add Python to environment variables**. Or use the Python launcher instead: `py -3.12 --version`. The install script uses the launcher, so it works either way |
| `python` opens the Microsoft Store | Turn off the store aliases: **Settings → Apps → Advanced app settings → App execution aliases**, switch off `python.exe` and `python3.exe` |
| `node` / `npm` not recognized | Reinstall Node.js, then open a new terminal. Check that `C:\Program Files\nodejs\` is in PATH |
| `psql` not recognized | The installer does not add it to PATH. Use the full path, for example `& "C:\Program Files\PostgreSQL\16\bin\psql.exe" --version` (use your version number), or add that `bin` folder to PATH: **Settings → System → About → Advanced system settings → Environment Variables → Path → Edit → New** |

After changing PATH, close and reopen PowerShell (and VS Code).

---

## 2. Get the code

### 2.1 Clone

```powershell
$env:GIT_LFS_SKIP_SMUDGE = "1"     # optional: skip the 1.7 GB of training images (section 2.2)
git clone https://github.com/Abusiad99/agriguard-ai.git
cd agriguard-ai
```

Use `git clone`, not GitHub's **Download ZIP**: the ZIP does not contain the Git LFS
training images. Everything needed to run the app (source, migrations, `configs/`, scripts,
templates, fonts) is in the repository; nothing has to be copied from another computer.

**`fatal: active post-checkout hook found during git clone`** — Git for Windows **2.45.1**
rejects the hook Git LFS installs and stops before checking out the files. Either update Git
(2.45.2+), or finish the checkout inside the new folder:

```powershell
cd agriguard-ai
git restore --source=HEAD :/
```

### 2.2 Training images (optional)

The 11,488 plant images in `datasets/plantwild_v2/` (about 1.7 GB) are stored with Git LFS.
You only need them to **train** the classifier (section 8). If Git LFS is installed, a normal
clone downloads them automatically; with `GIT_LFS_SKIP_SMUDGE=1` (above) the clone gets small
placeholder files instead. To download them later:

```powershell
git lfs install     # once per computer
git lfs pull        # inside agriguard-ai
```

### 2.3 Folder structure

| Folder | Contents |
|---|---|
| `backend/` | FastAPI application (`backend/app/`), Alembic migrations, backend tests, `requirements.txt` |
| `ai/` | AI pipelines: classifier training and inference, `segmentation/`, `outbreak/`, `recovery/`, `registry.py`, `requirements.txt` |
| `frontend/` | React + TypeScript + Tailwind app (Vite) |
| `configs/` | Report rules, the reference catalogue and settings for the segmentation, outbreak and recovery pipelines |
| `scripts/` | PowerShell scripts to install, check, migrate, start, stop and test |
| `datasets/` | Training data (images via Git LFS) and dataset schemas |
| `docker/` | Optional Docker Compose deployment |
| `docs/` | Requirements, design, feature, dataset and testing documentation |
| `train.py`, `evaluate.py`, `predict.py`, `inference.py` | Classifier training and command-line inference |

Created while you work (all git-ignored): `.venv/`, `.env`, `storage/` (uploaded photos,
heatmaps, PDF reports), `logs/`, `artifacts/` (trained models), `.run/` (records of the
running dev servers), `frontend/node_modules/`, `frontend/dist/`.

---

## 3. PostgreSQL

AgriGuard AI stores everything in PostgreSQL. The migrations use PostgreSQL-only
features (`JSONB`, `gen_random_uuid()`, a materialized view), so the database must be
PostgreSQL. Version 14 or newer works; 16 is tested.

### 3.1 Install

Run the EDB installer from https://www.postgresql.org/download/windows/. Keep the default
port **5432**, set a password for the `postgres` superuser and store it somewhere safe.
Stack Builder at the end is not needed.

### 3.2 Make sure the service is running

```powershell
Get-Service postgresql*
```

`Status` should be `Running`. If it is `Stopped`:

```powershell
Start-Service postgresql-x64-16      # use the exact name shown by Get-Service
```

`Start-Service` may need a PowerShell window opened with **Run as administrator**. You can
also start it in **services.msc**. The installer sets the service to start automatically
with Windows.

### 3.3 Create the application user and database

Choose a password for the application's own database user. Do not reuse the `postgres`
superuser password. Then, as the superuser:

```powershell
psql -U postgres -c "CREATE ROLE agriguard LOGIN PASSWORD 'YOUR_DB_PASSWORD';"
psql -U postgres -c "CREATE DATABASE agriguard OWNER agriguard;"
```

`psql` asks for the **postgres** password. Replace `YOUR_DB_PASSWORD` with your chosen
password, and avoid single quotes in it. If `psql` is not in PATH, see section 1.3.

### 3.4 Connection URL

The backend reads the connection from `DATABASE_URL` in `.env` (created in section 4):

```env
DATABASE_URL=postgresql+psycopg2://agriguard:YOUR_DB_PASSWORD@127.0.0.1:5432/agriguard
```

Format: `postgresql+psycopg2://<user>:<password>@<host>:<port>/<database>`. If the
password contains characters such as `@ : / ? # %`, encode it first:

```powershell
[uri]::EscapeDataString('p@ss:word')     # -> p%40ss%3Aword
```

Keep the database password private: it lives only in `.env`, which Git ignores. Never
commit it or paste it into chats, issues or screenshots.

### 3.5 Create the tables (migrations)

The schema is managed by Alembic (migrations `0001` to `0008` in
`backend/app/infrastructure/db/migrations/versions/`).

```powershell
powershell -ExecutionPolicy Bypass -File scripts\migrate.ps1                       # upgrade to the latest
powershell -ExecutionPolicy Bypass -File scripts\migrate.ps1 -Action current       # show the current revision
powershell -ExecutionPolicy Bypass -File scripts\migrate.ps1 -Action history       # list all revisions
```

Without the script (virtual environment activated, section 4.2):

```powershell
cd backend
python -m alembic upgrade head
python -m alembic current          # prints "0008 (head)" when up to date
cd ..
```

Run the upgrade again after every `git pull` that adds a migration. `dev.ps1` refuses to
start when the database is behind and tells you so. Downgrades are never run implicitly.
`migrate.ps1 -Action downgrade -Revision <rev>` exists, but it **drops the tables and
columns that were added later, including their data**.

### 3.6 Verify the connection

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-db.ps1
```

Expected (the password is always shown as `***`):

```
    URL       postgresql+psycopg2://agriguard:***@127.0.0.1:5432/agriguard
    SERVER    PostgreSQL 16.x
    LOGIN     user=agriguard database=agriguard
    SCHEMA    migrated to revision 0008 (latest)
    OK  Database reachable
```

It only reads; it never changes the database.

### 3.7 Connection errors

| `check-db.ps1` says | Cause | Fix |
|---|---|---|
| `DATABASE_URL still has the placeholder password` | `.env` still contains `YOUR_DB_PASSWORD` | Edit `.env` and put your password in `DATABASE_URL` |
| `password authentication failed for user "agriguard"` | Wrong password in `DATABASE_URL`, or the role doesn't exist | Fix the password in `.env`, or set a new one: `psql -U postgres -c "ALTER ROLE agriguard PASSWORD 'YOUR_DB_PASSWORD';"` |
| `database "agriguard" does not exist` | Step 3.3 not done | `psql -U postgres -c "CREATE DATABASE agriguard OWNER agriguard;"` |
| `Connection refused` | PostgreSQL is not running, or listens on another port | Section 3.2. Check the port in `C:\Program Files\PostgreSQL\16\data\postgresql.conf` (`port = ...`) |
| `SCHEMA not migrated yet` / `behind the latest` | Migrations not run | Section 3.5 |

### 3.8 SQLite

The automated backend tests use an in-memory SQLite database, so they run without
PostgreSQL. SQLite is **not supported for running the application**: the migrations target
PostgreSQL, and a SQLite database would have no migration history.

---

## 4. Backend

### 4.1 With the install script (recommended)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-backend.ps1
```

It does the following:

1. Finds Python 3.12, 3.11 or 3.10 through the `py` launcher, or uses `python`.
2. Creates the virtual environment `.venv\` in the repository folder.
3. Installs `backend\requirements.txt` and `ai\requirements.txt`. The AI packages include
   PyTorch, which is a large download. `-SkipAi` leaves them out: the API still runs, but
   scans cannot work.
4. Creates `.env` from `.env.example`, if `.env` doesn't exist yet, with a random
   `JWT_SECRET_KEY`. An existing `.env` is never changed.

Then put your database password into `.env` (`notepad .env`, replace `YOUR_DB_PASSWORD`).

If the repository sits in a very deep folder and pip fails with path-length errors, use a
shorter folder for the environment. Set it in every PowerShell window you use for the
scripts:

```powershell
$env:AGRIGUARD_VENV = "C:\venvs\agriguard"
```

### 4.2 Manually

```powershell
py -3.12 -m venv .venv          # or: py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
pip install -r ai\requirements.txt
Copy-Item .env.example .env
notepad .env
```

In `.env`, set `DATABASE_URL` (section 3.4) and replace `JWT_SECRET_KEY` with a random value
from:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**If activation is blocked** (`running scripts is disabled on this system`), allow scripts
for the current window only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

This changes nothing permanently. It ends when you close the window. The project scripts
avoid the issue by being run as `powershell -ExecutionPolicy Bypass -File ...`.

### 4.3 Configuration (`.env`)

`.env` in the repository root holds the local configuration. It is git-ignored.
`.env.example` documents every setting next to the value it ships with. Precedence, from
strongest to weakest:

1. real environment variables (for example `$env:DATABASE_URL = "..."` in the current window)
2. `backend\.env`, if you create one
3. `.env` in the repository root

| Setting | What to set | Default in `.env.example` |
|---|---|---|
| `DATABASE_URL` | Your PostgreSQL connection (section 3.4) | Placeholder password: **must be edited** |
| `JWT_SECRET_KEY` | Long random secret; also signs the private image links | Generated by `install-backend.ps1` |
| `APP_ENV` | `development` locally | `development` |
| `GEMINI_API_KEY` | Optional (section 7.1) | empty = disabled |
| `GEMINI_MODEL` | Gemini model name | `gemini-3.6-flash` |
| `CORS_ALLOW_ORIGINS` | Only needed when a page on another origin calls the API directly | localhost:5173 |
| `MAX_UPLOAD_SIZE_BYTES` | Largest accepted photo | 15 MB |
| `LOCAL_STORAGE_DIR`, `LOG_DIR` | Leave commented out: defaults are `storage\` and `logs\` in the repo | — |
| `AGRIGUARD_ARTIFACTS_DIR`, `AI_ARTIFACTS_RUN_DIR`, `AGRIGUARD_DEVICE` | AI model location and device (section 8) | defaults |

With `APP_ENV=production`, the backend refuses to start while `JWT_SECRET_KEY` is the example
value or shorter than 32 characters.

Restart the backend after you change `.env`. (`--reload` restarts it when code changes,
not when `.env` changes.)

### 4.4 Start the backend

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1               # background, logs in logs\
powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1 -Foreground   # in this window, Ctrl+C stops it
```

Manually, with the virtual environment activated:

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

| URL | What |
|---|---|
| http://127.0.0.1:8000/api/docs | Swagger UI: every endpoint, with **Authorize** for a token from `/api/v1/auth/login` |
| http://127.0.0.1:8000/api/redoc | The same documentation as ReDoc |
| http://127.0.0.1:8000/api/openapi.json | OpenAPI schema |
| http://127.0.0.1:8000/health | Health check (no login) |

All API routes are under `/api/v1`. `/health` answers HTTP 200 while the database is
reachable and HTTP 503 when it is down. `ai_service` is `ok` with a trained classifier,
`degraded` when none is installed (scans unavailable, everything else works) and `down`
when a model exists but fails to load.

---

## 5. Frontend

### 5.1 Install

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-frontend.ps1
```

This checks for Node.js 18+ and runs `npm ci` (exact versions from `package-lock.json`).
Manually:

```powershell
cd frontend
npm ci
```

### 5.2 Configuration

The frontend needs no `.env` and holds **no secrets or API keys**. It calls the backend
through relative `/api/...` paths. The Vite dev server forwards them to
`http://127.0.0.1:8000`. To use a backend on another address, set this before starting the
frontend:

```powershell
$env:AGRIGUARD_API_URL = "http://127.0.0.1:8001"
```

### 5.3 Commands (from `frontend/package.json`)

| Command (run in `frontend\`) | What it does |
|---|---|
| `npm run dev` | Development server on http://127.0.0.1:5173 (fails if 5173 is taken) |
| `npm run build` | Type-checks and builds the production files into `frontend\dist\` |
| `npm run preview` | Serves the built `dist\` locally on http://localhost:4173 for a final check |
| `npm run lint` | ESLint, zero warnings allowed |
| `npm run typecheck` | TypeScript type check |
| `npm test` | Vitest unit tests |

Or with the script, from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-frontend.ps1               # background
powershell -ExecutionPolicy Bypass -File scripts\start-frontend.ps1 -Foreground   # in this window
```

Open **http://127.0.0.1:5173**.

---

## 6. One-command startup (`scripts\dev.ps1`)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

`dev.ps1` does the following:

1. Checks the Python environment, `.env`, Node.js and the frontend packages.
2. Checks that the database in `DATABASE_URL` is reachable and fully migrated. It never
   migrates by itself; it tells you to run `migrate.ps1`.
3. Starts the backend and the frontend through `start-backend.ps1` and
   `start-frontend.ps1`, and waits until both answer.
4. Prints the app, API, API docs and health URLs, whether the classifier is ready, and the
   log files.
5. Waits. **Ctrl+C** stops the two servers it started. If one of them stops on its own, the
   other is stopped too and the script ends with an error.

Behaviour you can rely on:

- A server that is already running (started earlier by the start scripts) is reused and
  left running; nothing is started twice.
- Only processes this script recorded in `.run\` are stopped, identified by process id and
  start time. Other Python or Node programs are never touched.
- Secrets are not printed; the database password shows as `***`.

| Option | Effect |
|---|---|
| `-Detach` | Start both servers in the background and return. Stop them later with `stop-dev.ps1` |
| `-BackendPort 8001 -FrontendPort 5174` | Use other ports. The frontend is pointed at the backend port automatically |
| `-SkipDbCheck` | Skip the database check |

**Logs:** `logs\backend-dev.err.log` (Uvicorn writes its log here) and
`logs\frontend-dev.out.log`. To follow one live:

```powershell
Get-Content logs\backend-dev.err.log -Wait -Tail 30
```

**Debugging one service:** start it alone in the foreground and watch its output:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-backend.ps1 -Foreground
powershell -ExecutionPolicy Bypass -File scripts\start-frontend.ps1 -Foreground    # in a second window
```

---

## 7. API keys and external services

### 7.1 Gemini (optional)

| Item | Value |
|---|---|
| Service | Google Gemini API (`google-genai` SDK), called **only by the backend** |
| Settings | `GEMINI_API_KEY` (key), `GEMINI_MODEL` (default `gemini-3.6-flash`), `GEMINI_TIMEOUT_SECONDS` (20), `GEMINI_MAX_TOOL_CALLS` (6), `REPORTS_LLM_ENABLED` (`true`) |
| Where | `.env` in the repository root |
| Required? | No |
| What it adds | An **AI Agricultural Analysis** section on each new diagnosis (explains the classifier's result; it can't change it), and AI-worded executive summaries in reports. The summaries are checked against the report's facts and replaced by a template when they fail the checks |
| Without it | Both are skipped. Diagnoses show no AI section; reports use the template summary. Everything else works the same |

**Get a key**

1. Open Google AI Studio: https://aistudio.google.com/apikey and sign in with a Google
   account.
2. Choose **Create API key** and pick or create a Google Cloud project.
3. Copy the key. Treat it like a password.

**Add it**

```powershell
notepad .env
```

Find the line `GEMINI_API_KEY=` and paste the key after the `=` (no quotes, no spaces).
Save the file.

**Restart the backend** so it reads the new value. Press Ctrl+C in the `dev.ps1` window
and start it again, or:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

**Verify safely**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-gemini.ps1
```

This sends one model-lookup request to Google. It generates no content and never prints the
key, only its length.

| Output | Meaning |
|---|---|
| `OK  the key works and the model is available` | Ready |
| `KEY  not set - Gemini is disabled` | No key in `.env`; Gemini features are off (not an error) |
| `ClientError (HTTP 400): API key not valid` | Wrong or revoked key: create a new one and replace it |
| `HTTP 404` / model not found | `GEMINI_MODEL` is not a current model name; see https://aistudio.google.com/docs/models |
| `HTTP 429` | Quota or rate limit reached: wait, or check your plan in AI Studio |
| Network or timeout errors | This computer can't reach `generativelanguage.googleapis.com` (firewall, proxy, offline) |

In the app, an outbreak **area report** shows whether Gemini worded its summary
(**Reports** → open the report → *Technical details* → *Narrative*). Diagnosis
explanations need a trained classifier first (section 8).

If the key is missing, invalid or over quota while the app runs, every Gemini call fails
safely: the diagnosis is saved without the AI section (or with "AI analysis temporarily
unavailable"), and reports fall back to the template summary. The error is logged without
the key.

**Rules for keys**

- Keys belong only in the backend's `.env`. **Never** put a key in frontend code: the
  frontend has no key settings, and anything shipped to the browser is public.
- `.env` and `backend\.env` are git-ignored. Check with `git check-ignore -v .env`; it
  should print a `.gitignore` line. Never `git add -f` them.
- `.env.example` holds placeholders only. Never write a real key or password into it.
- Never print keys in logs or terminal output, and never paste them into chats, issues or
  screenshots. If a key leaks, delete it in AI Studio and create a new one.

### 7.2 All external services

| Service | Provider | Setting(s) | Required? | Credentials | Configure in | Verify | Without it |
|---|---|---|---|---|---|---|---|
| Database | PostgreSQL (local) | `DATABASE_URL` | **Yes** | Your own role/password | `.env` | `scripts\check-db.ps1` | `/health` returns 503; the app doesn't work |
| AI explanations, report summaries | Google Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL`, `REPORTS_LLM_ENABLED` | No | https://aistudio.google.com/apikey | `.env` | `scripts\check-gemini.ps1` | Sections omitted; template summary |
| Weather at scan time (spraying conditions) | Open-Meteo forecast API | `WEATHER_API_BASE_URL` | No key; internet needed | None | `.env` (default works) | Scan with **Attach my location** on; the result shows weather | Diagnosis completes; spraying check says "Not assessed" |
| Daily weather for outbreak estimates | Open-Meteo forecast and archive APIs | `WEATHER_API_BASE_URL`, `WEATHER_ARCHIVE_BASE_URL` | No key; internet needed | None | `.env` (defaults work) | **Outbreak risk** → pick a crop and disease → select an area → **Estimate risk** | Limitation "weather unavailable"; no risk level |
| Map tiles | OpenStreetMap (loaded by the browser) | none | No key; internet needed | None | — | The outbreak map shows a base map | Grid cells still listed; no base map |
| Location for weather | The browser's geolocation | none | Optional, opt-in per scan | Browser permission | — | Browser asks when you tick the option | Scan without weather |

These settings exist in `.env.example` but **no code uses them yet**, so filling them in has
no effect: `SMTP_*` (password reset by email is not implemented), `STORAGE_BACKEND` and
`S3_*` (only local file storage exists), `WEATHER_API_PROVIDER` and `WEATHER_API_KEY`
(only Open-Meteo exists), `REDIS_URL` (nothing connects to Redis) and
`ALLOWED_IMAGE_CONTENT_TYPES` (uploads are checked by decoding the image). There is no
external login provider: accounts are email and password, stored in your database.

---

## 8. AI models and what works without them

### 8.1 The image classifier (disease diagnosis)

| Question | Answer |
|---|---|
| Model | A `timm` image classifier, `efficientnet_b0` by default (`AGRIGUARD_ARCHITECTURE`) |
| Where the trained model lives | `artifacts\runs\<timestamp>_<architecture>\model.pt` plus label files; `artifacts\runs\latest.json` points to the newest run |
| How it's loaded | At backend start (and on the first scan if that failed): the run in `latest.json`, or the folder set in `AI_ARTIFACTS_RUN_DIR`. `AGRIGUARD_ARTIFACTS_DIR` moves the whole `artifacts` folder |
| Downloaded automatically? | **No trained AgriGuard model is downloaded or shipped.** Training (`train.py`) starts from ImageNet-pretrained weights, which `timm` downloads once (internet needed). Running the app never downloads weights |
| Required for scans? | **Yes.** Without a trained run, `POST /api/v1/scans` answers **503** (`SERVICE_UNAVAILABLE`: "No trained model found...") and `/health` shows `"ai_service":"degraded"`. Everything else works |
| CPU / GPU | `AGRIGUARD_DEVICE=auto` uses CUDA if available, then Apple MPS, then CPU. `pip install -r ai\requirements.txt` installs CPU PyTorch on Windows; for an NVIDIA GPU, install PyTorch with the command from https://pytorch.org/get-started/locally/ |

Train and check a model (needs the images from section 2.2, and takes a long time on a CPU):

```powershell
.\.venv\Scripts\python.exe train.py                                   # writes artifacts\runs\<timestamp>_<arch>\
.\.venv\Scripts\python.exe evaluate.py                                # test-split metrics of the latest run
.\.venv\Scripts\python.exe inference.py --image path\to\leaf.jpg      # JSON prediction for one photo
```

Restart the backend afterwards; `/health` then shows `"ai_service":"ok"`.

### 8.2 Status of each feature

| Feature | Status | Needs |
|---|---|---|
| Accounts, roles, history, dashboard, knowledge base admin | Implemented and working | PostgreSQL |
| Disease classification (Scan Plant) | Implemented | **A trained classifier** (8.1). Not included in this repository, so scans return 503 until you train one |
| Heatmap and severity | Implemented | The classifier. Severity and affected area come from the Grad-CAM attention map and are labelled as estimates, not measurements |
| Disease localization (segmentation) | Software implemented | **A pixel-annotated dataset and a trained segmentation model** (`docs/features/disease-localization.md`). Without one, every scan records "waiting for a trained model" |
| Plant recovery tracking (My plants) | Implemented and working | Diagnoses from a classifier. Measured change needs the segmentation model; until then the status is *Inconclusive* with the reason shown |
| Outbreak risk map | Map of observed cases is implemented | Located scans (opt-in) or imported survey data. **Risk estimates need historical inspection data and a trained outbreak model** (`docs/features/outbreak-prediction.md`); without them they say *model not ready* or *insufficient data* |
| Weather guidance (spraying conditions) | Implemented and working | Internet access to Open-Meteo. Uses published wind limits and an AgriGuard rain threshold; checks conditions at scan time only |
| Agricultural reports (diagnosis, plant progress, regional risk) | Implemented and working | Built from stored records. The diagnosis and plant reports need diagnoses (so a classifier). Wording by Gemini is optional |
| Gemini explanation | Implemented | `GEMINI_API_KEY` **and** a trained classifier (it explains the classifier's result) |

None of the models has been trained or evaluated on real field data in this repository.
The automated tests use clearly labelled **synthetic** data and a stand-in classifier. They
prove the software works, not that any model is accurate. Real agricultural validation is
still needed before relying on the results.

### 8.3 Running without trained models

This is the normal state of a fresh clone, and it is safe:

- The backend starts; `/health` is `ok` for the database and `degraded` for the AI service.
- Scans return a clear 503 error. No fake diagnosis is produced.
- The localization card says it is waiting for a trained model.
- Tracked plants show *Inconclusive* with the reason.
- The outbreak map shows observed cases; estimates report *model not ready*.
- **Admin → AI models** (`/admin/models`, admin or agronomist role) shows each model's readiness.

---

## 9. Docker (optional)

Docker Compose can run PostgreSQL, the backend, NGINX and a frontend build together
(`docker/docker-compose.yml`, instructions in [docker/README.md](../docker/README.md)):

First time (Docker Desktop running):

```powershell
cd docker
Copy-Item .env.example .env
notepad .env          # set JWT_SECRET_KEY (48+ random characters), POSTGRES_PASSWORD, CORS_ALLOW_ORIGINS
docker compose up -d --build
docker compose ps     # wait until postgres, backend and nginx show "healthy"
```

Then open **http://localhost** (NGINX serves the app and forwards `/api`). The API is also
published directly on http://localhost:8000 (docs: http://localhost:8000/api/docs).

| Task | Command (in `docker\`) |
|---|---|
| Start again later | `docker compose up -d` |
| Logs | `docker compose logs -f backend` |
| Stop (keeps all data) | `docker compose down` |
| Rebuild after `git pull` | `docker compose up -d --build` |

Never add `-v` to `docker compose down` unless you mean to **delete** the database and
uploaded files: it removes the data volumes.

Notes:

- `docker\.env` is separate from the root `.env` and is also git-ignored. The compose file
  refuses to start without `JWT_SECRET_KEY`, and with `APP_ENV=production` (the default
  there) the backend refuses the example value or anything shorter than 32 characters.
- The stack publishes ports 80 (NGINX), 8000 (backend) and 5432 (PostgreSQL). Stop a local
  PostgreSQL (or the native dev servers) first, or change the ports, if they clash.
- The backend container waits for PostgreSQL and runs `alembic upgrade head` on every start.
- The backend image uses the **CPU-only** PyTorch build (about 2.4 GB image; the backend
  container gets no GPU). For the CUDA build:
  `docker compose build --build-arg TORCH_INDEX_URL= backend`.
- Trained models live in the `artifacts_data` Docker volume, which the optional `training`
  service writes and the backend reads. Without a model there, scans return 503
  (see docker/README.md).

**Verified (11 November 2026)** with Docker Desktop 4.85 / Engine 29.6.2, in an isolated
compose project:

- Images: both build.
- Startup: PostgreSQL, the backend and NGINX all become healthy.
- Migrations: run from empty to `0008`; `configs/` is present in the image.
- Through NGINX:
  - the frontend loads in English and Arabic;
  - sign-up and login work;
  - an Arabic report and its PDF are generated;
  - corrupt uploads are rejected, and a real photo returns the documented 503 (no model);
  - forged media links are refused;
  - weather is fetched from inside the container.
- With the example JWT secret, the backend refuses to start.

Two fixes came out of this run:

- **The backend container could not start on Windows clones.** Its start script was checked
  out with CRLF line endings (`exec ... backend-entrypoint.sh: no such file or directory`).
  Fixed by `.gitattributes` and by the Dockerfile.
- **NGINX was always reported unhealthy.** Its healthcheck asked `localhost` over IPv6.

If you built an older checkout, rebuild with `docker compose up -d --build`.

---

## 10. Tests

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
```

This runs the backend tests (pytest, in-memory SQLite, no database needed), then the
frontend lint, type check, unit tests and production build. It prints a failure summary
at the end.

To also run the database and migration tests on real PostgreSQL, create a **throwaway**
database whose name ends in `_test`. The tests drop and recreate everything in it, so never
point it at your real database.

```powershell
psql -U postgres -c "CREATE DATABASE agriguard_test OWNER agriguard;"
powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -PostgresUrl postgresql+psycopg2://agriguard:YOUR_DB_PASSWORD@127.0.0.1:5432/agriguard_test
```

Other options: `-BackendOnly`, `-FrontendOnly`. Frontend only, by hand:

```powershell
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Two backend tests skip themselves without PostgreSQL (`test_migrations_postgres.py`), and
one needs a trained model (`test_ai_inference_integration.py`). The Gemini and weather
tests use mocks: they never call Google or Open-Meteo.

---

## 11. Production build

- **Frontend:** `cd frontend; npm run build` produces static files in `frontend\dist\`.
  Serve them with any web server that also forwards `/api` to the backend. NGINX does this
  in the Docker setup (`docker/nginx/nginx.conf`). `npm run preview` serves the build
  locally for a check.
- **Backend:** set `APP_ENV=production` and a strong `JWT_SECRET_KEY`, set
  `CORS_ALLOW_ORIGINS` to your site's origin, and run Uvicorn without `--reload`, for
  example `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4` from
  `backend\` behind a reverse proxy with HTTPS. Run `alembic upgrade head` before each
  release.
- The project is a functional prototype: the models are untrained and real-world
  validation is outstanding. See the README's status notes before deploying it for real use.

---

## 12. Troubleshooting

| Problem | Likely cause | How to check | Safe fix |
|---|---|---|---|
| `python` not found / opens the Store | Not in PATH, or Store alias | `py -0p` | Section 1.3 |
| `Python 3.10 or newer was not found` (install script) | No suitable Python | `py -0p` | Install Python 3.12 from python.org |
| `node` / `npm` not found | Node.js missing or terminal opened before install | `node --version` in a new window | Install Node.js LTS, reopen the terminal |
| `running scripts is disabled on this system` | PowerShell execution policy | `Get-ExecutionPolicy -List` | Run scripts as `powershell -ExecutionPolicy Bypass -File scripts\<name>.ps1`; for venv activation see 4.2. Don't change the machine-wide policy |
| `Python environment not found ... Run scripts\install-backend.ps1` | `.venv` missing, or `AGRIGUARD_VENV` not set in this window | `Test-Path .venv\Scripts\python.exe` | Run the install script, or set `$env:AGRIGUARD_VENV` again |
| `No .env found` | `.env` not created | `Test-Path .env` | `Copy-Item .env.example .env`, then edit it |
| PostgreSQL connection refused / password failed / database missing | See 3.7 | `scripts\check-db.ps1` | Section 3.7 |
| `alembic` errors: `relation ... already exists` | Tables were created outside Alembic | `scripts\migrate.ps1 -Action current` | Use a fresh, empty database for AgriGuard. Don't drop tables in a database that holds data you need |
| `dev.ps1`: `The database schema is not up to date` | New migrations after `git pull` | `scripts\check-db.ps1` | `scripts\migrate.ps1` |
| Backend fails at start with a settings `ValidationError`, or files land in odd folders | Typo or wrong type in `.env` (for example text where a number is expected), or an empty path such as `LOCAL_STORAGE_DIR=` | `logs\backend-dev.err.log` | Fix the line; leave the optional path settings commented out |
| `Refusing to start: JWT_SECRET_KEY must be ...` | `APP_ENV=production` with a weak secret | — | Set a 48+ character random secret |
| `ClientError (HTTP 400): API key not valid` | Wrong Gemini key | `scripts\check-gemini.ps1` | New key from AI Studio (7.1) |
| Gemini HTTP 429 / "AI analysis temporarily unavailable" | Gemini quota or rate limit | `scripts\check-gemini.ps1`, backend log | Wait, or raise the quota; the app keeps working without it |
| Scan returns 503 "No trained model found" | No classifier trained | `/health` shows `ai_service: degraded` | Train one (8.1), then restart the backend |
| Scan error after training / `ai_service: down` | Broken or incomplete model run | `logs\backend-dev.err.log` | Re-run `train.py`, or point `AI_ARTIFACTS_RUN_DIR` at a complete run |
| `Port 8000 is already in use` / `Port 5173 ...` | Another server, or one still shutting down | `Get-NetTCPConnection -LocalPort 8000 -State Listen` | `scripts\stop-dev.ps1`; wait a few seconds; or use `-BackendPort` / `-FrontendPort` |
| Frontend shows network errors, `/api` calls fail | Backend not running, or on another port | http://127.0.0.1:8000/health | Start the backend; set `$env:AGRIGUARD_API_URL` for a different port |
| CORS errors in the browser console | Page opened from an origin that isn't allowed while calling the API directly | Browser dev tools → Console | Use the dev server URL (http://127.0.0.1:5173), or add your origin to `CORS_ALLOW_ORIGINS` and restart the backend |
| Upload: `Image exceeds the maximum allowed size` (413) | File larger than `MAX_UPLOAD_SIZE_BYTES` (15 MB) | — | Use a smaller photo |
| Upload: `not a valid, decodable image` / `dimensions are too large` (422) | Not an image, a corrupt file, or more than about 89 megapixels | — | Export as JPEG or PNG at a normal resolution |
| `429 Too Many Requests` | Built-in rate limits (10 sign-ins per 5 min, 30 scans per hour per client) | — | Wait, or raise the `RATE_LIMIT_*` settings in `.env` for local testing |
| PDF report fails or Arabic shows boxes | Missing `reportlab`, `arabic-reshaper` or `python-bidi` | `logs\backend-dev.err.log` | Re-run `scripts\install-backend.ps1` |
| Old photo links `/storage/...` return 404 | Photos are private now and use signed links | — | Expected; links in the app work |
| PowerShell script errors in a non-English path | Very long or unusual path | — | Clone to a short path such as `C:\dev\agriguard-ai`, or set `$env:AGRIGUARD_VENV` |
| `git clone` ends with `active post-checkout hook found` | Git for Windows 2.45.1 bug with Git LFS | `git --version` | Update Git, or run `git restore --source=HEAD :/` in the cloned folder (section 2.1) |
| Clone downloads gigabytes | Git LFS fetches the 1.7 GB of training images | — | Clone with `$env:GIT_LFS_SKIP_SMUDGE = "1"` (section 2.1) |
| Docker: backend restarts with `exec /usr/local/bin/backend-entrypoint.sh: no such file or directory` | Image built from an older checkout whose script had Windows line endings | `docker compose logs backend` | `git pull`, then `docker compose up -d --build` |
| Docker: `port is already allocated` (80, 8000 or 5432) | The native dev servers or a local PostgreSQL use the same port | `Get-NetTCPConnection -LocalPort 5432 -State Listen` | Stop the other service, or change the published port in `docker-compose.yml` |
| Docker Desktop shows an error and quits: `remove ...\Docker\run\dockerInference` (or `...\docker-secrets-engine\engine.sock`): `The file cannot be accessed by the system` | On some Windows builds Docker's leftover socket files cannot be deleted | Docker Desktop log in `%LOCALAPPDATA%\Docker\log\host\` | Quit Docker Desktop, rename the folders `%LOCALAPPDATA%\Docker\run` and `%LOCALAPPDATA%\docker-secrets-engine` (for example to `run.old`), start Docker Desktop again. Don't use **Reset to factory defaults**: it deletes all images and volumes |

Never drop or recreate your real database as a troubleshooting step. Use `check-db.ps1`
(read-only) and the logs first.

---

## Appendix: scripts

| Script | Purpose |
|---|---|
| `install-backend.ps1` | Python environment, backend + AI packages, `.env` from the template |
| `install-frontend.ps1` | `npm ci` |
| `check-db.ps1` | Read-only database check (server, login, migration revision) |
| `migrate.ps1` | Alembic `upgrade` (default), `current`, `history`, `downgrade -Revision <rev>` |
| `check-gemini.ps1` | Optional Gemini key check (one model lookup, key never printed) |
| `dev.ps1` | Check everything and start backend + frontend; Ctrl+C stops them |
| `start-backend.ps1` / `start-frontend.ps1` | Start one server (background, or `-Foreground`) |
| `stop-dev.ps1` | Stop the servers the scripts started |
| `test.ps1` | All automated checks |
| `segmentation.ps1`, `outbreak.ps1`, `recovery-data.ps1` | Data preparation and training for the AI features (see the feature docs) |
