"""OpenAlex API client — comprehensive fallback."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from cite_verify.apis.base import APIClient
from cite_verify.cache import DiskCache
from cite_verify.reporting.models import APIResult

logger = logging.getLogger(__name__)


class OpenAlexClient:
    """Client for the OpenAlex API."""

    def __init__(self, cache: DiskCache, email: str = "", rps: float = 10.0, max_retries: int = 3, timeout: float = 30.0):
        headers = {}
        if email:
            headers["mailto"] = email
        self._client = APIClient(
            base_url="https://api.openalex.org",
            cache=cache,
            requests_per_second=rps,
            max_retries=max_retries,
            timeout=timeout,
            headers=headers,
        )

    async def lookup_doi(self, doi: str) -> APIResult | None:
        """Look up a work by DOI."""
        clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/")
        cache_key = f"openalex:doi:{clean_doi}"
        data = await self._client.get(
            f"/works/https://doi.org/{quote(clean_doi, safe='')}",
            cache_key=cache_key,
        )
        if not data:
            return None
        return self._parse_work(data)

    async def search_title(self, title: str, limit: int = 5) -> list[APIResult]:
        """Search for works by title."""
        clean = re.sub(r"[^\w\s]", " ", title).strip()
        if not clean:
            return []
        cache_key = f"openalex:search:{clean.lower()[:100]}"
        data = await self._client.get(
            "/works",
            params={"search": clean, "per_page": str(limit)},
            cache_key=cache_key,
        )
        if not data:
            return []
        results = data.get("results", [])
        return [self._parse_work(w) for w in results if w]

    def _parse_work(self, item: dict) -> APIResult:
        """Parse an OpenAlex work into an APIResult."""
        authors = []
        for authorship in item.get("authorships", []):
            author = authorship.get("author", {})
            name = author.get("display_name", "")
            if name:
                authors.append(name)

        doi = item.get("doi", "")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi.removeprefix("https://doi.org/")
        elif not doi:
            doi = None

        biblio = item.get("biblio", {}) or {}

        # Determine venue/journal
        primary_location = item.get("primary_location", {}) or {}
        source = primary_location.get("source", {}) or {}
        journal = source.get("display_name")

        work_type = item.get("type", "")
        if work_type in ("journal-article", "article"):
            entry_type = "article"
        elif work_type in ("proceedings-article",):
            entry_type = "inproceedings"
        else:
            entry_type = None

        return APIResult(
            source="openalex",
            title=item.get("title", "") or "",
            authors=authors,
            year=item.get("publication_year"),
            doi=doi,
            journal=journal,
            volume=biblio.get("volume"),
            number=biblio.get("issue"),
            pages=f"{biblio.get('first_page', '')}-{biblio.get('last_page', '')}"
            if biblio.get("first_page")
            else None,
            publisher=source.get("host_organization_name"),
            entry_type=entry_type,
        )

    async def close(self) -> None:
        await self._client.close()
