"""Private media: scan photos and heatmaps are only reachable through signed, expiring
URLs handed out after the owner/admin check — never through a public /storage path."""
from __future__ import annotations

import io
import time
from urllib.parse import parse_qs, urlparse

from PIL import Image

from app.core.media_urls import signed_media_url, verify_media_signature
from tests.conftest import make_auth_header


def _image():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (70, 120, 50)).save(buf, format="JPEG")
    buf.seek(0)
    return ("leaf.jpg", buf, "image/jpeg")


def _scan(client, headers):
    resp = client.post("/api/v1/scans", headers=headers, files={"image": _image()})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_photo_url_is_signed_and_works_without_auth_header(client):
    owner = make_auth_header(client, email="media1@example.com")
    scan = _scan(client, owner)
    url = scan["roi_image_url"]
    assert url.startswith("/api/v1/media/scans/") and "sig=" in url and "exp=" in url
    resp = client.get(url)  # an <img src> sends no Authorization header
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["cache-control"].startswith("private")
    # the history list hands out the same kind of URL
    listing = client.get("/api/v1/diagnoses", headers=owner).json()
    assert listing["items"][0]["thumbnail_url"].startswith("/api/v1/media/scans/")


def test_old_public_storage_paths_are_closed(client):
    owner = make_auth_header(client, email="media2@example.com")
    scan = _scan(client, owner)
    key = urlparse(scan["roi_image_url"]).path.removeprefix("/api/v1/media/")
    assert client.get(f"/storage/{key}").status_code == 404


def test_tampered_expired_or_unsigned_urls_are_refused(client):
    owner = make_auth_header(client, email="media3@example.com")
    scan = _scan(client, owner)
    parsed = urlparse(scan["roi_image_url"])
    q = parse_qs(parsed.query)
    path = parsed.path
    assert client.get(path).status_code == 400  # no signature at all (request validation)
    assert client.get(f"{path}?exp={q['exp'][0]}&sig={q['sig'][0][:-2]}xx").status_code == 403
    assert client.get(f"{path}?exp={int(q['exp'][0]) + 60}&sig={q['sig'][0]}").status_code == 403
    other = path.replace(path.rsplit("/", 1)[1], "0" * 32 + ".jpg")
    assert client.get(f"{other}?exp={q['exp'][0]}&sig={q['sig'][0]}").status_code == 403  # signature is per file


def test_signing_rules():
    now = time.time()
    url = signed_media_url("scans/abc.jpg", now=now)
    q = parse_qs(urlparse(url).query)
    assert verify_media_signature("scans/abc.jpg", int(q["exp"][0]), q["sig"][0], now=now)
    assert not verify_media_signature("scans/abc.jpg", int(q["exp"][0]), q["sig"][0], now=int(q["exp"][0]) + 1)  # expired
    for key in ("reports/x.pdf", "scans/../reports/x.pdf", "scans//x.jpg", "../etc/passwd"):
        assert signed_media_url(key) is None
        assert not verify_media_signature(key, int(now) + 600, "x", now=now)
    assert signed_media_url(None) is None


def test_other_users_never_receive_a_url(client):
    owner = make_auth_header(client, email="media4@example.com")
    other = make_auth_header(client, email="media5@example.com")
    scan = _scan(client, owner)
    resp = client.get(f"/api/v1/diagnoses/{scan['diagnosis_id']}", headers=other)
    assert resp.status_code == 403 and "media" not in resp.text
