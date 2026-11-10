"""
Short-lived signed URLs for private media: scan photos, Grad-CAM heatmaps and
segmentation images.

These files used to be served from public `/storage/...` paths, protected only by an
unguessable file name. Now the API hands out a URL like

    /api/v1/media/scans/<file>.jpg?exp=<unix time>&sig=<HMAC>

and only inside a response that already passed the owner/admin check (or a valid
report share). The signature binds the exact file and the expiry, so a URL can't be
altered to reach another file and stops working after `MEDIA_URL_TTL_SECONDS`. It
works in a plain <img src> (no Authorization header), so the API fields keep their
names and clients keep working.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Optional

from app.core.config import get_settings

# Only these storage folders can be reached through a media URL (never reports/).
MEDIA_PREFIXES = ("scans/", "heatmaps/", "segmentations/")
MAX_TTL_SECONDS = 7 * 24 * 3600


def _signing_key() -> bytes:
    # Derived from the JWT secret with a fixed label, so the two uses never share a key.
    return hmac.new(get_settings().jwt_secret_key.encode(), b"agriguard-media-url-v1", hashlib.sha256).digest()


def _signature(key: str, exp: int) -> str:
    mac = hmac.new(_signing_key(), f"{key}\n{exp}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def is_media_key(key: str) -> bool:
    parts = key.split("/")
    return key.startswith(MEDIA_PREFIXES) and "" not in parts and ".." not in parts and "\\" not in key


def signed_media_url(key: Optional[str], ttl_seconds: Optional[int] = None, now: Optional[float] = None) -> Optional[str]:
    """URL for a storage key, or None when there is no file. The expiry is rounded up to
    a quarter of the TTL so the same image keeps the same URL for a while (browser cache)."""
    if not key or not is_media_key(key):
        return None
    settings = get_settings()
    ttl = min(MAX_TTL_SECONDS, ttl_seconds or settings.media_url_ttl_seconds)
    step = max(60, ttl // 4)
    exp = ((int(now if now is not None else time.time()) + ttl) // step + 1) * step
    return f"{settings.api_prefix}/media/{key}?exp={exp}&sig={_signature(key, exp)}"


def verify_media_signature(key: str, exp: int, sig: str, now: Optional[float] = None) -> bool:
    current = now if now is not None else time.time()
    if not is_media_key(key) or exp < current or exp > current + MAX_TTL_SECONDS + 3600:
        return False
    return hmac.compare_digest(_signature(key, exp), sig)
