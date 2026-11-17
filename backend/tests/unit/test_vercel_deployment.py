"""The free Vercel deployment (docs/SETUP_AND_RUN.md section 9.9): settings Vercel relies on,
the dependency list Vercel installs, the frontend served by the backend, the visitor address
behind Vercel's proxy, and the scan answer without a machine-learning runtime.

Code that reads environment variables at import time runs in a separate Python process here, so
the test process keeps its own settings. All data is SYNTHETIC; no network or real database."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest
from starlette.requests import Request

from app.core.config import normalize_database_url
from app.interface.middleware import security_middleware as sm
from app.interface.middleware.client_address import client_address

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
TEST_ONLY = {"pytest", "pytest-cov", "pypdf"}


def _run(code: str, extra_env: dict, cwd: Path = BACKEND) -> dict:
    """Run `code` in a fresh interpreter with a clean AgriGuard environment; it prints JSON."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AGRIGUARD_", "VERCEL")) and k not in {
               "DATABASE_URL", "LOCAL_STORAGE_DIR", "LOG_DIR", "AI_ARTIFACTS_DIR", "APP_ENV",
               "CLIENT_IP_HEADER", "FRONTEND_DIST_DIR", "JWT_SECRET_KEY"}}
    env.update({"PYTHONPATH": os.pathsep.join([str(BACKEND), str(ROOT)]), "PYTHONUTF8": "1"}, **extra_env)
    out = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=cwd, env=env,
                         capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------------ connection strings
@pytest.mark.parametrize("given", [
    "postgresql://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
    "postgres://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
    "  'postgresql://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'  ",
    "psql 'postgresql://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'",
])
def test_neon_connection_strings_are_accepted_as_copied(given):
    assert normalize_database_url(given) == (
        "postgresql+psycopg2://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")


def test_other_urls_are_left_alone():
    for url in ("sqlite:///:memory:", "postgresql+psycopg2://a:b@localhost:5432/agriguard"):
        assert normalize_database_url(url) == url


# ------------------------------------------------------------------ what Vercel installs
def _requirement_lines(text: str) -> list[str]:
    lines = [re.sub(r"\s+#.*$", "", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def test_vercel_dependencies_match_backend_requirements():
    vercel = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = vercel["project"]["dependencies"]
    backend = [r for r in _requirement_lines((BACKEND / "requirements.txt").read_text(encoding="utf-8"))
               if re.split(r"[<>=\[ ]", r, maxsplit=1)[0] not in TEST_ONLY]
    assert deps == backend, "pyproject.toml (Vercel) and backend/requirements.txt list different packages"
    assert vercel["tool"]["vercel"]["entrypoint"] == "asgi:app"
    assert not any(d.split(">")[0].split("=")[0] in {"torch", "torchvision", "timm"} for d in deps)


def test_vercel_config_points_at_the_entrypoint_and_keeps_bulky_folders_out():
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    excluded = config["functions"]["asgi.py"]["excludeFiles"]
    for folder in ("datasets/**", "frontend/node_modules/**", "backend/tests/**", "storage/**", "artifacts/**"):
        assert folder in excluded
    assert "frontend/dist" not in excluded  # the built app must stay deployable


# ------------------------------------------------------------------ settings on Vercel
def test_on_vercel_files_go_to_tmp_and_production_checks_apply():
    result = _run("""
        import json
        from app.core.config import Settings, production_config_problems
        s = Settings(_env_file=None)   # before ai.config, which loads a local .env into the environment
        from ai.config import PathConfig
        p = PathConfig()
        print(json.dumps({"env": s.app_env, "storage": s.local_storage_dir, "logs": s.log_dir,
                          "artifacts": s.ai_artifacts_dir, "ip_header": s.client_ip_header,
                          "frontend": s.frontend_dist_dir, "problems": production_config_problems(s),
                          "ai": [str(p.artifacts_dir), str(p.cache_dir), str(p.logs_dir)]}))
    """, {"VERCEL": "1"})
    assert result["env"] == "production"
    for key in ("storage", "logs", "artifacts"):
        assert Path(result[key]).as_posix().startswith("/tmp/agriguard"), result
    assert all(Path(p).as_posix().startswith("/tmp/agriguard") for p in result["ai"]), result
    assert result["ip_header"] == "x-real-ip"
    assert Path(result["frontend"]).as_posix().endswith("frontend/dist")
    joined = " ".join(result["problems"])
    assert "JWT_SECRET_KEY" in joined and "DATABASE_URL is not set" in joined


def test_outside_vercel_nothing_changes():
    result = _run("""
        import json
        from app.core.config import Settings, production_config_problems
        s = Settings(_env_file=None)
        print(json.dumps({"env": s.app_env, "storage": s.local_storage_dir, "ip_header": s.client_ip_header,
                          "frontend": s.frontend_dist_dir, "problems": production_config_problems(s)}))
    """, {})
    assert result["env"] == "development" and result["ip_header"] == "" and result["frontend"] == ""
    assert not Path(result["storage"]).as_posix().startswith("/tmp/") and result["problems"] == []


def test_a_neon_url_and_strong_secret_pass_the_vercel_checks():
    result = _run("""
        import json
        from app.core.config import Settings, production_config_problems
        print(json.dumps({"problems": production_config_problems(Settings(_env_file=None))}))
    """, {"VERCEL": "1", "JWT_SECRET_KEY": "s" * 64,
          "DATABASE_URL": "postgres://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require"})
    assert result["problems"] == []


# ------------------------------------------------------------------ the frontend served by the backend
def test_backend_serves_the_built_frontend_without_hiding_the_api(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<!doctype html><div id="root"></div>', encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('agriguard')", encoding="utf-8")
    result = _run("""
        import json
        from fastapi.testclient import TestClient
        from app.main import app
        html, js = {"Accept": "text/html"}, {"Accept": "application/json"}
        out = {}
        with TestClient(app) as c:
            for name, path, h in [("home", "/", html), ("deep", "/plants/123", html), ("asset", "/assets/app.js", {}),
                                  ("api", "/api/v1/diagnoses", js), ("unknown_api", "/api/v1/nope", js),
                                  ("health", "/health", js)]:
                r = c.get(path, headers=h)
                out[name] = [r.status_code, r.headers.get("content-type", "").split(";")[0], 'id="root"' in r.text]
        print(json.dumps(out))
    """, {"FRONTEND_DIST_DIR": str(dist), "DATABASE_URL": "sqlite:///:memory:",
          "LOCAL_STORAGE_DIR": str(tmp_path / "storage"), "LOG_DIR": str(tmp_path / "logs")})
    assert result["home"] == [200, "text/html", True]
    assert result["deep"] == [200, "text/html", True]          # the React router handles /plants/123
    assert result["asset"][:2] == [200, "application/javascript"]
    assert result["api"][:2] == [401, "application/json"]      # API routes win over the frontend
    assert result["unknown_api"][:2] == [404, "application/json"]
    assert result["health"][:2] == [200, "application/json"]


# ------------------------------------------------------------------ no ML runtime on the server
def test_scan_service_says_plainly_that_no_classifier_is_installed():
    result = _run("""
        import json, sys
        sys.modules["torch"] = None   # as on Vercel, where PyTorch is not installed
        from app.infrastructure.external.ai_pipeline_client import AiPipelineClient, AiPipelineUnavailableError
        try:
            AiPipelineClient()._get_service()
            print(json.dumps({"error": None}))
        except AiPipelineUnavailableError as exc:
            print(json.dumps({"error": str(exc)}))
    """, {"DATABASE_URL": "sqlite:///:memory:"})
    assert result["error"] and "No image classifier is installed" in result["error"]


# ------------------------------------------------------------------ the visitor's address
def _request(headers: dict, client=("10.0.0.1", 1234)) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "client": client,
                    "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]})


def test_client_address_uses_the_proxy_header_only_when_configured():
    req = _request({"x-real-ip": "203.0.113.7"})
    assert client_address(req, "x-real-ip") == "203.0.113.7"
    assert client_address(req, "") == "10.0.0.1"                # not configured: a visitor cannot pick an address
    assert client_address(_request({}), "x-real-ip") == "10.0.0.1"  # header missing: fall back
    assert client_address(_request({"x-real-ip": "198.51.100.1, 10.1.1.1"}), "x-real-ip") == "198.51.100.1"
    assert client_address(_request({}, client=None), "") == "unknown"


def test_rate_limit_counts_each_vercel_visitor_separately(client, monkeypatch):
    from tests.integration.test_rate_limit import _limiter

    limiter = _limiter(client.app)
    monkeypatch.setattr(limiter, "_client_ip_header", "x-real-ip")
    monkeypatch.setattr(sm.settings, "rate_limit_auth_per_5min", 2)
    attempt = {"email": "nobody@example.com", "password": "wrong-password"}

    def login(ip):
        return client.post("/api/v1/auth/login", json=attempt, headers={"x-real-ip": ip}).status_code

    assert [login("203.0.113.1") for _ in range(3)] == [401, 401, 429]   # visitor 1 used up the allowance
    assert login("203.0.113.2") == 401                                    # visitor 2 is unaffected
