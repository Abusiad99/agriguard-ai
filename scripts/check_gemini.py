"""Check the optional Gemini configuration (GEMINI_API_KEY, GEMINI_MODEL from the backend
settings / .env) without printing the key. Makes one model-lookup request (models.get);
no content is generated. Used by scripts/check-gemini.ps1; run from backend/ with the
repo root and backend/ on PYTHONPATH.

Exit codes: 0 = key works with the model, 2 = no key configured (Gemini disabled),
1 = the request failed (invalid key, unknown model, network, quota)."""
from __future__ import annotations

import sys

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    key = settings.gemini_api_key or ""
    print(f"    MODEL     {settings.gemini_model}")
    if not key:
        print("    KEY       not set - Gemini is disabled; diagnoses and reports work without it")
        return 2
    print(f"    KEY       set ({len(key)} characters; not shown)")

    def safe(text: str) -> str:
        return str(text).replace(key, "<key hidden>")

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("    FAILED    the google-genai package is missing - run scripts\\install-backend.ps1")
        return 1
    try:
        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000)))
        model = client.models.get(model=settings.gemini_model)
    except Exception as exc:  # noqa: BLE001 - report every failure plainly, without the key
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        message = safe(getattr(exc, "message", None) or str(exc)).strip().splitlines()[0][:300]
        print(f"    FAILED    {type(exc).__name__}{f' (HTTP {code})' if code else ''}: {message}")
        return 1
    print(f"    OK        the key works and the model is available ({safe(model.name)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
