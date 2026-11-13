"""Rate limiter (RateLimitMiddleware): limits apply per client and route group, the table of
counters stays bounded whatever URLs are requested, and idle counters are dropped.

Before this was fixed the limiter kept one counter per client per exact URL and never
removed any: every distinct URL had its own allowance (so the default limit limited
nothing) and requesting made-up paths grew the table without bound."""
from __future__ import annotations

import time
from collections import deque
from uuid import uuid4

from app.interface.middleware import security_middleware as sm
from tests.conftest import make_auth_header


def _limiter(app) -> sm.RateLimitMiddleware:
    layer = app.middleware_stack
    while layer is not None and not isinstance(layer, sm.RateLimitMiddleware):
        layer = getattr(layer, "app", None)
    assert layer is not None, "RateLimitMiddleware is not installed"
    return layer


def test_default_limit_is_per_client_and_resource_not_per_url(client, monkeypatch):
    headers = make_auth_header(client, email="rl1@example.com")
    monkeypatch.setattr(sm.settings, "rate_limit_default_per_5min", 5)
    # seven different URLs of the same resource share one allowance of five
    codes = [client.get(f"/api/v1/diagnoses/{uuid4()}", headers=headers).status_code for _ in range(7)]
    assert codes == [404] * 5 + [429, 429]
    body = client.get(f"/api/v1/diagnoses/{uuid4()}", headers=headers).json()
    assert body["error"]["code"] == "RATE_LIMITED"
    # another resource has its own allowance
    assert client.get("/api/v1/tracked-plants", headers=headers).status_code == 200


def test_made_up_paths_share_one_counter(client):
    limiter = _limiter(client.app)
    limiter._hits.clear()
    for i in range(40):
        client.get(f"/api/v1/no-such-resource-{i}/item-{i}")
        client.get(f"/somewhere/else/{i}")
    assert list(limiter._hits) == ["testclient:other"]
    assert not {r for r in limiter._resources if r.startswith("no-such-resource")}  # junk never becomes a group
    # private media links (not in the OpenAPI schema) are still recognised as their own group
    client.get("/api/v1/media/scans/" + "0" * 32 + ".jpg?exp=1&sig=x")
    assert "testclient:media" in limiter._hits


def test_login_attempts_are_limited(client, monkeypatch):
    monkeypatch.setattr(sm.settings, "rate_limit_auth_per_5min", 3)
    attempt = {"email": "nobody@example.com", "password": "wrong-password"}
    codes = [client.post("/api/v1/auth/login", json=attempt).status_code for _ in range(5)]
    assert 429 not in codes[:3] and codes[3:] == [429, 429]
    # registration has its own counter
    ok = client.post("/api/v1/auth/register", json={"email": "rl3@example.com", "password": "Str0ngPass!", "full_name": "RL"})
    assert ok.status_code == 201


def test_idle_counters_are_dropped(client, monkeypatch):
    limiter = _limiter(client.app)
    limiter._hits.clear()
    stale = time.monotonic() - limiter._MAX_WINDOW_SECONDS - 60
    limiter._hits["203.0.113.7:diagnoses"] = deque([stale])     # a client that went away
    limiter._hits["203.0.113.8:media"] = deque()                # an emptied counter
    monkeypatch.setattr(limiter, "_PRUNE_EVERY", 3)
    limiter._since_prune = 0
    for _ in range(3):
        client.get("/health")
    assert set(limiter._hits) == {"testclient:other"}
