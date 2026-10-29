"""
Signed, expiring media URLs for private files (plant photos, attention maps,
segmentation overlays).

Previously every stored file was served by an unauthenticated StaticFiles mount at
/storage, so anyone holding (or guessing) a path could fetch other users' photos and
PDF reports. Files are now only reachable through /api/v1/media/<ref>?exp=&sig=,
where `sig` is an HMAC-SHA256 over (ref, exp) with a key derived from the server
secret. URLs are minted only by endpoints that have already checked that the caller
may see the record, and expire after `media_url_ttl_seconds` (rounded up to a
10-minute boundary so repeated requests reuse the same URL and stay cacheable).
<img> tags cannot send Authorization headers, which is why a signed URL is used
instead of bearer auth. PDF reports are NOT served this way; they keep their own
authenticated endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional
from urllib.parse import quote

from app.core.config import get_settings

ALLOWED_PREFIXES = ("scans/", "heatmaps/", "segmentation/")
_ROUND_SECONDS = 600


def _key() -> bytes:
    secret = get_settings().jwt_secret_key.encode()
    return hmac.new(secret, b"agriguard-media-url-v1", hashlib.sha256).digest()


def _signature(ref: str, exp: int) -> str:
    return hmac.new(_key(), f"{ref}\n{exp}".encode(), hashlib.sha256).hexdigest()


def is_allowed_ref(ref: str) -> bool:
    return (bool(ref) and ref.startswith(ALLOWED_PREFIXES) and ".." not in ref
            and not ref.startswith("/") and "\\" not in ref)


def sign_media_url(ref: Optional[str], now: Optional[float] = None) -> Optional[str]:
    if not ref or not is_allowed_ref(ref):
        return None
    settings = get_settings()
    now = time.time() if now is None else now
    exp = int(((now + settings.media_url_ttl_seconds) // _ROUND_SECONDS + 1) * _ROUND_SECONDS)
    return f"{settings.api_prefix}/media/{quote(ref)}?exp={exp}&sig={_signature(ref, exp)}"


def verify_media_signature(ref: str, exp: int, sig: str, now: Optional[float] = None) -> bool:
    if not is_allowed_ref(ref):
        return False
    now = time.time() if now is None else now
    if exp < now:
        return False
    return hmac.compare_digest(_signature(ref, exp), sig or "")
