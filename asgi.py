"""Entry point for Vercel (the free public demo; docs/SETUP_AND_RUN.md section 9.9).

Vercel loads the FastAPI instance named `app` from this file (pyproject.toml,
[tool.vercel] entrypoint). It is the same application as backend/app/main.py; this file
only makes the `app` package (backend/) and the `ai` package (repository root) importable.
Local development, Docker and the tests do not use it.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _path in (str(_ROOT), str(_ROOT / "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fastapi import FastAPI  # noqa: E402

from app.main import app as _agriguard_app  # noqa: E402

app: FastAPI = _agriguard_app
