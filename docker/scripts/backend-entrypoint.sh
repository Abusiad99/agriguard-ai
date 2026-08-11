#!/bin/sh
# AgriGuard AI â€” Backend container entrypoint.
#
# Runs Alembic migrations (database migration startup strategy) before the app
# starts, waiting for PostgreSQL to be reachable first (docker-compose's
# depends_on/healthcheck already gates container start order, but this adds a
# belt-and-suspenders wait since Postgres "started" and "accepting connections"
# are not the same moment). Fails loudly and exits non-zero if migrations fail,
# rather than starting an API server against an unmigrated/partially-migrated
# schema.
set -e

echo "[entrypoint] Waiting for database to accept connections..."
python - <<'PYEOF'
import sys
import time

from sqlalchemy import create_engine, text

from app.core.config import get_settings

settings = get_settings()
max_attempts = 30
for attempt in range(1, max_attempts + 1):
    try:
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[entrypoint] Database is reachable.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"[entrypoint] Database not ready (attempt {attempt}/{max_attempts}): {exc}")
        time.sleep(2)
print("[entrypoint] Database did not become reachable in time.", file=sys.stderr)
sys.exit(1)
PYEOF

echo "[entrypoint] Running Alembic migrations..."
alembic -c /app/alembic.ini upgrade head

echo "[entrypoint] Migrations complete. Starting application..."
exec "$@"
