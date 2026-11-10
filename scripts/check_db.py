"""Report whether the database in DATABASE_URL (backend settings / .env) is reachable,
its server version and its Alembic revision. Read-only. Used by scripts/check-db.ps1;
run from the backend/ directory with the repo root and backend/ on PYTHONPATH."""
from __future__ import annotations

import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings


def main() -> int:
    url = make_url(get_settings().database_url)
    print("    URL       " + url.render_as_string(hide_password=True))
    is_postgres = url.get_backend_name() == "postgresql"
    if not is_postgres:
        print("    WARNING   not a PostgreSQL URL; the app and its migrations target PostgreSQL")
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 5} if is_postgres else {})
        with engine.connect() as conn:
            if is_postgres:
                print("    SERVER    PostgreSQL " + conn.execute(text("SHOW server_version")).scalar())
                user, database = conn.execute(text("SELECT current_user, current_database()")).one()
                print(f"    LOGIN     user={user} database={database}")
            if inspect(conn).has_table("alembic_version"):
                revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                print(f"    SCHEMA    migrated to revision {revision}")
            else:
                print("    SCHEMA    not migrated yet - run scripts\\migrate.ps1")
    except Exception as exc:  # noqa: BLE001 - report any connection failure plainly
        print("    FAILED    " + str(exc).strip().splitlines()[0])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
