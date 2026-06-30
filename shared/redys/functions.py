from __future__ import annotations

from redis import Redis
from shared.utils.logger import log
from shared.config import settings
from .connection import RedysConnection


class Redys:
    """
    Valkey/Redis client — singleton per process.

    Two namespaces:
      scrape:cache:<url>       — anti re-scrape flag (set by worker)
      cleaner:checkpoint       — last MongoDB _id processed by cleaner
    """

    _conn: RedysConnection | None = None

    @classmethod
    def _client(cls) -> Redis:
        if cls._conn is None:
            cls._conn = RedysConnection()
        return cls._conn.client

    # ------------------------------------------------------------------
    # Anti re-scrape cache  (namespace: scrape:cache)
    # ------------------------------------------------------------------

    @classmethod
    def cache_exists(cls, text: str, key: str = settings.valkey_key) -> bool:
        """Return True if this text has already been scraped."""
        return bool(cls._client().exists(f"{key}:{text}"))

    @classmethod
    def cache_set(cls, text: str, key: str = settings.valkey_key, ttl_seconds: int = 60 * 60 * 24 * 30) -> None:
        """Mark text as scraped. Default TTL = 30 days."""
        cls._client().set(f"{key}:{text}", "1", ex=ttl_seconds)
        log.debug("[ VALKEY ] cache_set → {}", text)

    # ------------------------------------------------------------------
    # Cleaner checkpoint  (namespace: cleaner)
    # ------------------------------------------------------------------

    @classmethod
    def get_checkpoint(cls, name: str = "cleaner") -> str | None:
        """Return last processed MongoDB _id string, or None if no checkpoint yet."""
        return cls._client().get(f"{name}:checkpoint")

    @classmethod
    def set_checkpoint(cls, mongo_id: str, name: str = "cleaner") -> None:
        """Save last processed MongoDB _id string."""
        cls._client().set(f"{name}:checkpoint", mongo_id)

    # ------------------------------------------------------------------
    # Generic raw key access (for ad-hoc use)
    # ------------------------------------------------------------------

    @classmethod
    def raw_get(cls, key: str) -> str | None:
        return cls._client().get(key)

    @classmethod
    def raw_set(cls, key: str, value: str, ttl_seconds: int | None = None) -> None:
        cls._client().set(key, value, ex=ttl_seconds)

    @classmethod
    def close(cls) -> None:
        if cls._conn:
            cls._conn.client.close()
            cls._conn = None
            log.debug("[ VALKEY ] connection closed")
