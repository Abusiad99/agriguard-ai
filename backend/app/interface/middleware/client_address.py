"""The visitor's address, for rate limits and request logs."""
from __future__ import annotations

from starlette.requests import Request


def client_address(request: Request, header: str = "") -> str:
    """`header` names a request header set by a proxy that overwrites what the visitor sends
    (Vercel: x-real-ip); its first address is used when present. Otherwise the address of the
    connection, which behind NGINX uvicorn has already set to the visitor's (FORWARDED_ALLOW_IPS).
    Never configure a header that visitors can set themselves: they could pick any address."""
    if header:
        value = request.headers.get(header, "").split(",")[0].strip()
        if value:
            return value
    return request.client.host if request.client else "unknown"
