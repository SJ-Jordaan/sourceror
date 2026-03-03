"""Shared HTTP client, rate limiter, and retry logic."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from sourceror.cache import DiskCache

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token-bucket rate limiter."""

    def __init__(self, requests_per_second: float):
        self.interval = 1.0 / requests_per_second
        self._last_request = 0.0

    async def acquire(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self.interval:
            await asyncio.sleep(self.interval - elapsed)
        self._last_request = time.monotonic()


class APIClient:
    """Base HTTP client with rate limiting, caching, and retry."""

    def __init__(
        self,
        base_url: str,
        cache: DiskCache,
        requests_per_second: float = 10.0,
        max_retries: int = 3,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.cache = cache
        self.rate_limiter = RateLimiter(requests_per_second)
        self.max_retries = max_retries
        self.timeout = timeout
        default_headers = {
            "User-Agent": "sourceror/1.0 (academic citation verification tool)",
            "Accept": "application/json",
        }
        if headers:
            default_headers.update(headers)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=default_headers,
            timeout=timeout,
            follow_redirects=True,
        )

    async def get(self, path: str, params: dict | None = None, cache_key: str | None = None) -> dict | None:
        """Make a GET request with caching, rate limiting, and retry."""
        if cache_key:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        await self.rate_limiter.acquire()

        for attempt in range(self.max_retries):
            try:
                resp = await self._client.get(path, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if cache_key:
                        self.cache.set(cache_key, data)
                    return data
                if resp.status_code == 404:
                    return None
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = min(2 ** attempt * 1.0, 30.0)
                    logger.warning("API %s returned %d, retrying in %.1fs", path, resp.status_code, wait)
                    await asyncio.sleep(wait)
                    continue
                logger.warning("API %s returned %d", path, resp.status_code)
                return None
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                wait = min(2 ** attempt * 1.0, 30.0)
                logger.warning("Request to %s failed (%s), retrying in %.1fs", path, e, wait)
                await asyncio.sleep(wait)

        logger.error("All retries exhausted for %s", path)
        return None

    async def close(self) -> None:
        await self._client.aclose()
