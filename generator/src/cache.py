"""Tiny cache wrapper. v1 = no-op (REDIS_URL empty). v2 = real Redis."""
from typing import Optional

from . import config


class Cache:
    def __init__(self):
        self.enabled = bool(config.REDIS_URL)
        self._client = None
        if self.enabled:
            import redis  # local import so v1 doesn't require redis in runtime path
            self._client = redis.from_url(config.REDIS_URL, decode_responses=True)

    def get(self, key: str) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            return self._client.get(key)
        except Exception:
            return None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if not self.enabled:
            return
        try:
            self._client.setex(key, ttl_seconds, value)
        except Exception:
            pass

    def delete(self, *keys: str) -> None:
        if not self.enabled or not keys:
            return
        try:
            self._client.delete(*keys)
        except Exception:
            pass
