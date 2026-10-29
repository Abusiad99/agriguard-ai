"""Signed media URLs: valid only for the exact ref, until expiry, for allowed prefixes."""
from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from app.infrastructure.security.media_signer import sign_media_url, verify_media_signature


def _parts(url: str):
    parsed = urlparse(url)
    ref = unquote(parsed.path.split("/media/", 1)[1])
    q = parse_qs(parsed.query)
    return ref, int(q["exp"][0]), q["sig"][0]


def test_round_trip_verifies():
    url = sign_media_url("scans/abc.jpg", now=1_000_000)
    ref, exp, sig = _parts(url)
    assert ref == "scans/abc.jpg"
    assert exp > 1_000_000
    assert verify_media_signature(ref, exp, sig, now=1_000_000)


def test_tampering_and_expiry_are_rejected():
    ref, exp, sig = _parts(sign_media_url("scans/abc.jpg", now=1_000_000))
    assert not verify_media_signature("scans/other.jpg", exp, sig, now=1_000_000)
    assert not verify_media_signature(ref, exp + 600, sig, now=1_000_000)
    assert not verify_media_signature(ref, exp, "0" * 64, now=1_000_000)
    assert not verify_media_signature(ref, exp, sig, now=exp + 1)


def test_reports_and_traversal_refs_are_never_signed():
    assert sign_media_url("reports/x.pdf") is None
    assert sign_media_url("scans/../reports/x.pdf") is None
    assert sign_media_url("/etc/passwd") is None
    assert sign_media_url(None) is None
    assert not verify_media_signature("reports/x.pdf", 10**12, "0" * 64)
