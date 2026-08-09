"""
Alembic environment. Reads the live SQLAlchemy URL from the application's own
centralized config (app.core.config.get_settings) rather than duplicating it in
alembic.ini, so migrations always target whatever database the app is currently
configured for (NFR-MAINT-4). Supports both 'offline' (SQL script generation) and
'online' (direct DB connection) modes, per standard Alembic convention.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app` importable when Alembic is invoked from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.config import get_settings  # noqa: E402
from app.infrastructure.db.models import Base  # noqa: E402  (imports every model onto Base.metadata)

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"}, compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
