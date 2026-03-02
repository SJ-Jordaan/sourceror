"""Disk-based response cache with TTL."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class DiskCache:
    """Simple file-based cache with TTL support."""

    def __init__(self, cache_dir: Path, ttl_days: int = 30):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_days * 86400
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str) -> Path:
        hashed = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / f"{hashed}.json"

    def get(self, key: str) -> dict | None:
        """Get a cached value, or None if missing/expired."""
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            if time.time() - data.get("timestamp", 0) > self.ttl_seconds:
                path.unlink(missing_ok=True)
                return None
            return data.get("value")
        except (json.JSONDecodeError, KeyError):
            path.unlink(missing_ok=True)
            return None

    def set(self, key: str, value: dict) -> None:
        """Store a value in the cache."""
        path = self._key_to_path(key)
        data = {"timestamp": time.time(), "value": value}
        path.write_text(json.dumps(data))

    def clear(self) -> int:
        """Remove all cache entries. Returns count of removed files."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count
