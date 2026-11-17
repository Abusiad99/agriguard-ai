"""Vercel build step for the free public demo (pyproject.toml, [tool.vercel.scripts] build).
Vercel runs it after installing the Python dependencies, before the deployment goes live.

1. Production deployments only: apply database migrations (`alembic upgrade head`) to the Neon
   database in MIGRATION_DATABASE_URL, its direct (non-pooled) connection string. Migrations
   only add tables and columns. If one fails, the build fails and the previous deployment
   keeps serving.
2. Build the React app into frontend/dist, which Vercel serves from its CDN.

Preview deployments (other branches) skip step 1, so they never change the database.
To rehearse locally:  python scripts/vercel_build.py --skip-migrations
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list, cwd: Path, env: dict | None = None) -> None:
    print("$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def migrate() -> None:
    if os.environ.get("VERCEL_ENV") != "production":
        print("Not a production deployment (VERCEL_ENV is not 'production'): database migrations skipped.")
        return
    url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("MIGRATION_DATABASE_URL is not set. Add Neon's direct connection string as an "
                 "environment variable for Production (docs/SETUP_AND_RUN.md section 9.9).")
    print("Applying database migrations (alembic upgrade head)...", flush=True)
    run([sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"], ROOT / "backend",
        env=dict(os.environ, DATABASE_URL=url))
    run([sys.executable, "-m", "alembic", "-c", "alembic.ini", "current"], ROOT / "backend",
        env=dict(os.environ, DATABASE_URL=url))


def build_frontend() -> None:
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("npm was not found: the React app cannot be built.")
    run([npm, "ci", "--no-audit", "--no-fund"], ROOT / "frontend")
    run([npm, "run", "build"], ROOT / "frontend")
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        sys.exit("The frontend build did not produce frontend/dist/index.html.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-migrations", action="store_true", help="build the frontend only")
    parser.add_argument("--skip-frontend", action="store_true", help="apply migrations only")
    args = parser.parse_args()
    if not args.skip_migrations:
        migrate()
    if not args.skip_frontend:
        build_frontend()
    print("Vercel build step finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
