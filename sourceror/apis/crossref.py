"""CrossRef API client — primary source for DOI lookup and fuzzy title search."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from urllib.parse import quote

from sourceror.apis.base import APIClient
from sourceror.cache import DiskCache
from sourceror.reporting.models import APIResult

logger = logging.getLogger(__name__)


class CrossRefClient:
    """Client for the CrossRef REST API."""

    def __init__(self, cache: DiskCache, email: str = "", rps: float = 10.0, max_retries: int = 3, timeout: float = 30.0):
        headers = {}
        if email:
            headers["mailto"] = email
        self._client = APIClient(
            base_url="https://api.crossref.org",
            cache=cache,
            requests_per_second=rps,
            max_retries=max_retries,
            timeout=timeout,
            headers=headers,
        )

    async def lookup_doi(self, doi: str) -> APIResult | None:
        """Look up a work by DOI."""
        clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/")
        cache_key = f"crossref:doi:{clean_doi}"
        data = await self._client.get(f"/works/{quote(clean_doi, safe='')}", cache_key=cache_key)
        if not data:
            return None
        return self._parse_work(data.get("message", data))

    async def search_title(self, title: str, limit: int = 5) -> list[APIResult]:
        """Search for works by title."""
        clean = re.sub(r"[^\w\s]", " ", title).strip()
        if not clean:
            return []
        cache_key = f"crossref:search:{clean.lower()[:100]}"
        data = await self._client.get(
            "/works",
            params={"query.title": clean, "rows": str(limit), "select": "DOI,title,author,published-print,published-online,container-title,volume,issue,page,publisher,type"},
            cache_key=cache_key,
        )
        if not data:
            return []
        items = data.get("message", {}).get("items", [])
        return [self._parse_work(item) for item in items]

    def _parse_work(self, item: dict) -> APIResult:
        """Parse a CrossRef work item into an APIResult."""
        titles = item.get("title", [])
        title = titles[0] if titles else ""

        authors = []
        for a in item.get("author", []):
            given = a.get("given", "")
            family = a.get("family", "")
            if given and family:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)

        year = None
        for date_field in ("published-print", "published-online", "created"):
            parts = item.get(date_field, {}).get("date-parts", [[]])
            if parts and parts[0] and parts[0][0]:
                year = parts[0][0]
                break

        containers = item.get("container-title", [])
        journal = containers[0] if containers else None

        cr_type = item.get("type", "")
        entry_type = "article" if "journal" in cr_type else "inproceedings" if "proceedings" in cr_type else None

        return APIResult(
            source="crossref",
            title=title,
            authors=authors,
            year=year,
            doi=item.get("DOI"),
            journal=journal,
            volume=item.get("volume"),
            number=item.get("issue"),
            pages=item.get("page"),
            publisher=item.get("publisher"),
            entry_type=entry_type,
        )

    async def close(self) -> None:
        await self._client.close()
