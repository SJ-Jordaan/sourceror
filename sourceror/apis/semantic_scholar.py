"""Semantic Scholar API client — fallback with abstract retrieval."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from sourceror.apis.base import APIClient
from sourceror.cache import DiskCache
from sourceror.reporting.models import APIResult

logger = logging.getLogger(__name__)

_FIELDS = "title,authors,year,externalIds,venue,publicationVenue,abstract,journal,publicationTypes"


class SemanticScholarClient:
    """Client for the Semantic Scholar Academic Graph API."""

    def __init__(self, cache: DiskCache, rps: float = 1.0, max_retries: int = 3, timeout: float = 30.0):
        self._client = APIClient(
            base_url="https://api.semanticscholar.org/graph/v1",
            cache=cache,
            requests_per_second=rps,
            max_retries=max_retries,
            timeout=timeout,
        )

    async def lookup_doi(self, doi: str) -> APIResult | None:
        """Look up a paper by DOI."""
        clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/")
        cache_key = f"s2:doi:{clean_doi}"
        data = await self._client.get(
            f"/paper/DOI:{quote(clean_doi, safe='')}",
            params={"fields": _FIELDS},
            cache_key=cache_key,
        )
        if not data:
            return None
        return self._parse_paper(data)

    async def search_title(self, title: str, limit: int = 5) -> list[APIResult]:
        """Search for papers by title."""
        clean = re.sub(r"[^\w\s]", " ", title).strip()
        if not clean:
            return []
        cache_key = f"s2:search:{clean.lower()[:100]}"
        data = await self._client.get(
            "/paper/search",
            params={"query": clean, "limit": str(limit), "fields": _FIELDS},
            cache_key=cache_key,
        )
        if not data:
            return []
        papers = data.get("data", [])
        return [self._parse_paper(p) for p in papers if p]

    def _parse_paper(self, item: dict) -> APIResult:
        """Parse a Semantic Scholar paper into an APIResult."""
        authors = []
        for a in item.get("authors", []):
            name = a.get("name", "")
            if name:
                authors.append(name)

        ext_ids = item.get("externalIds", {}) or {}
        doi = ext_ids.get("DOI")

        journal_info = item.get("journal", {}) or {}
        venue = item.get("venue", "") or ""
        journal = journal_info.get("name") or venue or None

        pub_types = item.get("publicationTypes", []) or []
        if "JournalArticle" in pub_types:
            entry_type = "article"
        elif "Conference" in pub_types:
            entry_type = "inproceedings"
        else:
            entry_type = None

        return APIResult(
            source="semantic_scholar",
            title=item.get("title", ""),
            authors=authors,
            year=item.get("year"),
            doi=doi,
            journal=journal,
            volume=journal_info.get("volume"),
            pages=journal_info.get("pages"),
            entry_type=entry_type,
            abstract=item.get("abstract"),
        )

    async def fetch_abstract(self, doi: str) -> str | None:
        """Fetch just the abstract for a paper by DOI."""
        clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/")
        cache_key = f"s2:abstract:{clean_doi}"
        data = await self._client.get(
            f"/paper/DOI:{quote(clean_doi, safe='')}",
            params={"fields": "abstract"},
            cache_key=cache_key,
        )
        if not data:
            return None
        return data.get("abstract")

    async def close(self) -> None:
        await self._client.close()
