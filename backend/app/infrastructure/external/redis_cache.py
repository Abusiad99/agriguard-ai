"""
RedisCache — optional ICache implementation backing WeatherService's freshness cache
(BR7) and available for future session/rate-limit use. The application remains fully
functional without Redis (WeatherService falls back to its in-memory cache — see
weather_client.py), so Redis connectivity failures never take down the API; this
mirrors NFR-AVAIL-2's "graceful degradation" principle applied to caching as well as
to the weather provider itself.
"""
from __future__ import annotations

import abc
import json
import logging
from typing import Optional

logger = logging.getLogger("agriguard.cache")


class ICache(abc.ABC):
    @abc.abstractmethod
    def get(self, key: str) -> Optional[str]: ...

    @abc.abstractmethod
    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...

    @abc.abstractmethod
    def delete(self, key: str) -> None: ...


class RedisCache(ICache):
    def __init__(self, redis_url: str):
        try:
            import redis
            self._client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
        except Exception as exc:  # noqa: BLE001 — Redis is optional infra; never fatal at import time
            logger.warning("Redis unavailable at %s (%s); RedisCache will no-op.", redis_url, exc)
            self._client = None

    def get(self, key: str) -> Optional[str]:
        if self._client is None:
            return None
        try:
            return self._client.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis GET failed for key=%s: %s", key, exc)
            return None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if self._client is None:
            return
        try:
            self._client.set(key, value, ex=ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis SET failed for key=%s: %s", key, exc)

    def delete(self, key: str) -> None:
        if self._client is None:
            return
        try:
            self._client.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis DELETE failed for key=%s: %s", key, exc)

    def get_json(self, key: str):
        raw = self.get(key)
        return json.loads(raw) if raw else None

    def set_json(self, key: str, value: dict, ttl_seconds: int) -> None:
        self.set(key, json.dumps(value), ttl_seconds)
