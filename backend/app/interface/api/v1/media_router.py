"""Private media (scan photos, heatmaps, segmentation images) behind signed URLs — see
app/core/media_urls.py. The signature is the authorization: it is only issued inside
responses that passed the owner/admin check or a valid report share."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.media_urls import verify_media_signature
from app.infrastructure.storage.object_storage import LocalObjectStorage
from app.interface.api.v1.dependencies import get_object_storage

router = APIRouter(prefix="/media", tags=["Media"])

_MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


@router.get("/{key:path}", include_in_schema=False)
def get_media(key: str, exp: int = Query(...), sig: str = Query(..., max_length=100),
              storage: LocalObjectStorage = Depends(get_object_storage)):
    if not verify_media_signature(key, exp, sig):
        raise AuthorizationError("This image link is invalid or has expired.")
    try:
        path = storage.resolve_path(key)
    except ValueError:
        raise NotFoundError("Image not found.")
    media_type = _MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None or not path.is_file():
        raise NotFoundError("Image not found.")
    max_age = max(0, min(3600, exp - int(time.time())))
    return FileResponse(path=str(path), media_type=media_type,
                        headers={"Cache-Control": f"private, max-age={max_age}", "Referrer-Policy": "no-referrer"})
