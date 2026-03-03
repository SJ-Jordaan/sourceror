"""Core verification pipeline with cascading API strategy."""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from sourceror.apis.crossref import CrossRefClient
from sourceror.apis.openalex import OpenAlexClient
from sourceror.apis.semantic_scholar import SemanticScholarClient
from sourceror.config import Config
from sourceror.parsers.bibtex import strip_latex
from sourceror.reporting.models import (
    APIResult,
    BibEntry,
    VerificationResult,
    VerificationStatus,
)
from sourceror.verification.metadata import check_metadata

logger = logging.getLogger(__name__)


def _title_similarity(a: str, b: str) -> float:
    """Compute title similarity after normalization."""
    a_clean = strip_latex(a).lower().strip()
    b_clean = strip_latex(b).lower().strip()
    if not a_clean or not b_clean:
        return 0.0
    return SequenceMatcher(None, a_clean, b_clean).ratio()


def _author_overlap(entry_surnames: list[str], api_authors: list[str]) -> float:
    """Compute fraction of entry author surnames found in API authors."""
    if not entry_surnames:
        return 1.0  # No authors to compare
    api_surnames = set()
    for author in api_authors:
        parts = author.strip().split()
        if parts:
            api_surnames.add(parts[-1].lower())
    if not api_surnames:
        return 0.0
    matches = sum(1 for s in entry_surnames if s in api_surnames)
    return matches / len(entry_surnames)


def _best_match(entry: BibEntry, candidates: list[APIResult], config: Config) -> APIResult | None:
    """Find the best matching API result for an entry."""
    best = None
    best_score = 0.0

    for candidate in candidates:
        title_sim = _title_similarity(entry.title, candidate.title)
        candidate.title_similarity = title_sim

        if title_sim < config.title_similarity_threshold:
            continue

        author_ovlp = _author_overlap(entry.author_surnames, candidate.authors)
        candidate.author_overlap = author_ovlp

        # Year check: must be within tolerance
        if entry.year and candidate.year:
            if abs(entry.year - candidate.year) > config.year_tolerance:
                continue

        score = title_sim * 0.6 + author_ovlp * 0.4
        if score > best_score:
            best_score = score
            best = candidate

    return best


async def verify_entry(
    entry: BibEntry,
    crossref: CrossRefClient,
    s2: SemanticScholarClient,
    openalex: OpenAlexClient,
    config: Config,
) -> VerificationResult:
    """Verify a single BibTeX entry against academic APIs."""
    if entry.should_skip():
        return VerificationResult(entry=entry, status=VerificationStatus.SKIPPED)

    try:
        # If DOI exists, verify directly
        if entry.doi:
            result = await _verify_by_doi(entry, crossref, s2, openalex, config)
            if result:
                return result

        # No DOI or DOI verification failed — search by title
        return await _verify_by_title(entry, crossref, s2, openalex, config)

    except Exception as e:
        logger.error("Error verifying %s: %s", entry.key, e)
        return VerificationResult(
            entry=entry,
            status=VerificationStatus.ERROR,
            error_message=str(e),
        )


async def _verify_by_doi(
    entry: BibEntry,
    crossref: CrossRefClient,
    s2: SemanticScholarClient,
    openalex: OpenAlexClient,
    config: Config,
) -> VerificationResult | None:
    """Try to verify an entry by its DOI."""
    for name, client in [("crossref", crossref), ("s2", s2), ("openalex", openalex)]:
        api_result = await client.lookup_doi(entry.doi)
        if api_result:
            title_sim = _title_similarity(entry.title, api_result.title)
            api_result.title_similarity = title_sim
            api_result.author_overlap = _author_overlap(entry.author_surnames, api_result.authors)

            if title_sim >= config.title_similarity_threshold:
                issues = check_metadata(entry, api_result)
                return VerificationResult(
                    entry=entry,
                    status=VerificationStatus.VERIFIED,
                    api_result=api_result,
                    metadata_issues=issues,
                )
            else:
                logger.warning(
                    "%s: DOI %s resolves but title mismatch (%.2f): '%s' vs '%s'",
                    entry.key, entry.doi, title_sim, entry.title, api_result.title,
                )
    return None


async def _verify_by_title(
    entry: BibEntry,
    crossref: CrossRefClient,
    s2: SemanticScholarClient,
    openalex: OpenAlexClient,
    config: Config,
) -> VerificationResult:
    """Try to verify an entry by title search across APIs."""
    if not entry.title:
        return VerificationResult(entry=entry, status=VerificationStatus.NOT_FOUND)

    # Cascade through APIs
    for name, client in [("CrossRef", crossref), ("Semantic Scholar", s2), ("OpenAlex", openalex)]:
        candidates = await client.search_title(entry.title)
        match = _best_match(entry, candidates, config)
        if match:
            issues = check_metadata(entry, match)
            status = VerificationStatus.VERIFIED if match.title_similarity >= 0.95 else VerificationStatus.LIKELY_MATCH
            return VerificationResult(
                entry=entry,
                status=status,
                api_result=match,
                metadata_issues=issues,
            )

    return VerificationResult(entry=entry, status=VerificationStatus.NOT_FOUND)
