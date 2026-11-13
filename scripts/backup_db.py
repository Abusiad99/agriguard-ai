"""Back up the PostgreSQL database in DATABASE_URL (backend settings / .env) to one file and
check that the file is a readable archive. Read-only for the database. Used by
scripts/backup-db.ps1; run from the backend/ directory with the repo root and backend/ on
PYTHONPATH.

The password is passed to pg_dump through the PGPASSWORD environment variable of the child
process only; it is never printed or written to the backup's name.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings

REPO_ROOT = Path(__file__).resolve().parent.parent


def _find_tool(name: str) -> str | None:
    """pg_dump / pg_restore from PATH, or from a standard Windows PostgreSQL installation."""
    found = shutil.which(name)
    if found:
        return found

    def version(path: Path) -> float:
        try:
            return float(path.parent.name)
        except ValueError:
            return 0.0

    bins = sorted(Path(os.environ.get("ProgramFiles", r"C:\Program Files"), "PostgreSQL").glob("*/bin"),
                  key=version, reverse=True)
    for folder in bins:
        candidate = folder / f"{name}.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _run(args, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(args, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _fail(message: str) -> int:
    print("    FAILED    " + message)
    return 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the application database (read-only).")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--container", default="", help="Docker container running PostgreSQL (pg_dump runs inside it)")
    args = parser.parse_args()

    url = make_url(get_settings().database_url)
    print("    URL       " + url.render_as_string(hide_password=True))
    if url.get_backend_name() != "postgresql":
        return _fail("DATABASE_URL is not a PostgreSQL database.")

    out_dir = Path(args.out_dir).expanduser().resolve()
    if out_dir == REPO_ROOT or REPO_ROOT in out_dir.parents:
        return _fail("Choose a folder outside the repository, so a backup can never be committed.")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Current migration revision, for the file name (a read-only query).
    try:
        with create_engine(url, connect_args={"connect_timeout": 5}).connect() as conn:
            revision = (conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                        if inspect(conn).has_table("alembic_version") else None) or "none"
            server = conn.execute(text("SHOW server_version")).scalar()
    except Exception as exc:  # noqa: BLE001 - report any connection failure plainly
        return _fail("cannot connect: " + str(exc).strip().splitlines()[0])
    print(f"    SERVER    PostgreSQL {server}, schema revision {revision}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    name = f"{url.database}-rev{revision}-{stamp}.dump"
    target = out_dir / name

    if args.container:
        docker = shutil.which("docker")
        if not docker:
            return _fail("docker was not found on PATH.")
        inside = f"/tmp/{name}"
        dump = _run([docker, "exec", args.container, "pg_dump", "-U", url.username, "-d", url.database,
                     "--format=custom", "--file", inside])
        if dump.returncode != 0:
            return _fail("pg_dump in the container failed: " + (dump.stderr or dump.stdout).strip())
        try:
            listing = _run([docker, "exec", args.container, "pg_restore", "--list", inside])
            copied = _run([docker, "cp", f"{args.container}:{inside}", str(target)])
            inside_hash = _run([docker, "exec", args.container, "sha256sum", inside])
        finally:
            _run([docker, "exec", args.container, "rm", "-f", inside])
        if copied.returncode != 0 or not target.is_file():
            return _fail("could not copy the backup out of the container: " + copied.stderr.strip())
        if inside_hash.returncode == 0 and inside_hash.stdout.split()[0] != _sha256(target):
            target.unlink()
            return _fail("the copied file differs from the one written in the container.")
    else:
        pg_dump, pg_restore = _find_tool("pg_dump"), _find_tool("pg_restore")
        if not pg_dump or not pg_restore:
            return _fail("pg_dump / pg_restore not found. Add PostgreSQL's bin folder to PATH, or pass "
                         "-Container <name> when the database runs in Docker.")
        env = dict(os.environ)
        if url.password:
            env["PGPASSWORD"] = url.password
        dump = _run([pg_dump, "--format=custom", "--no-password", "--file", str(target), "-h", url.host or "127.0.0.1",
                     "-p", str(url.port or 5432), "-U", url.username, url.database], env=env)
        if dump.returncode != 0:
            target.unlink(missing_ok=True)
            return _fail("pg_dump failed: " + (dump.stderr or dump.stdout).strip())
        listing = _run([pg_restore, "--list", str(target)])

    # Verify: the archive must be readable and list the data of every table.
    if listing.returncode != 0:
        return _fail("the backup file is not a readable archive: " + listing.stderr.strip())
    tables = sum(1 for line in listing.stdout.splitlines() if " TABLE DATA " in line)
    if target.stat().st_size == 0 or tables == 0:
        return _fail("the backup contains no table data.")
    sha = _sha256(target)
    Path(str(target) + ".sha256").write_text(f"{sha}  {name}\n", encoding="ascii")

    print(f"    BACKUP    {target}")
    print(f"    SIZE      {target.stat().st_size:,} bytes, data of {tables} tables")
    print(f"    SHA256    {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
