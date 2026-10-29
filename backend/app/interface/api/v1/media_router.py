"""Signed media delivery (see app/infrastructure/security/media_signer.py)."""
from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.core.exceptions import AuthorizationError, NotFoundError
from app.infrastructure.security.media_signer import verify_media_signature
from app.infrastructure.storage.object_storage import LocalObjectStorage
from app.interface.api.v1.dependencies import get_object_storage

router = APIRouter(prefix="/media", tags=["Media"])

_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.get("/{ref:path}")
def get_media(
    ref: str,
    exp: int = Query(...),
    sig: str = Query(..., min_length=64, max_length=64),
    storage: LocalObjectStorage = Depends(get_object_storage),
):
    if not verify_media_signature(ref, exp, sig):
        raise AuthorizationError("This media link is invalid or has expired.")
    try:
        path = storage.resolve_path(ref)
    except ValueError:
        raise AuthorizationError("This media link is invalid or has expired.")
    if not path.is_file():
        raise NotFoundError("Media not found.")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if media_type not in _ALLOWED_TYPES:
        raise NotFoundError("Media not found.")
    return FileResponse(
        path=str(path), media_type=media_type,
        headers={"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff"},
    )
