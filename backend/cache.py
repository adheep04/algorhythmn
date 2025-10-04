"""Lightweight in-memory cache utilities."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Any, Dict, Hashable, Optional

from . import config


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class InMemoryCache:
    """Simple thread-safe in-memory cache with optional TTL support."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._store: Dict[str, Dict[Hashable, _CacheEntry]] = {}

    def _namespace(self, name: str) -> Dict[Hashable, _CacheEntry]:
        if name not in self._store:
            self._store[name] = {}
        return self._store[name]

    def get(self, namespace: str, key: Hashable) -> Any:
        bucket = self._namespace(namespace)
        entry = bucket.get(key)
        if not entry:
            return None
        if entry.expires_at and entry.expires_at < monotonic():
            bucket.pop(key, None)
            return None
        return entry.value

    def set(
        self,
        namespace: str,
        key: Hashable,
        value: Any,
        ttl_seconds: Optional[float] = config.CACHE_DEFAULT_TTL_SECONDS,
    ) -> None:
        bucket = self._namespace(namespace)
        expires_at = monotonic() + ttl_seconds if ttl_seconds else 0.0
        with self._lock:
            bucket[key] = _CacheEntry(value=value, expires_at=expires_at)

    def get_or_set(
        self,
        namespace: str,
        key: Hashable,
        factory,
        ttl_seconds: Optional[float] = config.CACHE_DEFAULT_TTL_SECONDS,
    ) -> Any:
        existing = self.get(namespace, key)
        if existing is not None:
            return existing
        value = factory()
        self.set(namespace, key, value, ttl_seconds)
        return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


def build_cache_key(*parts: Hashable) -> str:
    return "::".join(str(part) for part in parts)
