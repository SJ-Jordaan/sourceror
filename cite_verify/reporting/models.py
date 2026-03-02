"""Data models for citation verification results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VerificationStatus(Enum):
    VERIFIED = "verified"
    LIKELY_MATCH = "likely_match"
    NOT_FOUND = "not_found"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class BibEntry:
    """A parsed BibTeX entry with normalized fields."""

    key: str
    entry_type: str  # article, inproceedings, etc.
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    booktitle: Optional[str] = None
    volume: Optional[str] = None
    number: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    url: Optional[str] = None
    note: Optional[str] = None
    raw_fields: dict[str, str] = field(default_factory=dict)
    source_file: str = ""

    def should_skip(self) -> bool:
        """Check if this entry should be skipped during verification."""
        if self.entry_type in ("online", "webpage"):
            return True
        if self.entry_type == "misc" and self.url and not self.title:
            return True
        if self.note and "submitted" in self.note.lower():
            return True
        return False

    @property
    def author_surnames(self) -> list[str]:
        """Extract last names from author list."""
        surnames = []
        for author in self.authors:
            parts = author.strip().split()
            if parts:
                surname = parts[-1].strip("{}")
                surnames.append(surname.lower())
        return surnames


@dataclass
class APIResult:
    """Result from an academic API lookup."""

    source: str  # "crossref", "semantic_scholar", "openalex"
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    number: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    entry_type: Optional[str] = None
    abstract: Optional[str] = None
    title_similarity: float = 0.0
    author_overlap: float = 0.0


@dataclass
class MetadataIssue:
    """A detected metadata discrepancy or missing field."""

    field: str
    issue_type: str  # "mismatch", "missing", "suggestion"
    local_value: Optional[str] = None
    api_value: Optional[str] = None
    message: str = ""


@dataclass
class RelevanceResult:
    """Result of LLM-based relevance check."""

    relevant: bool = True
    confidence: float = 1.0
    explanation: str = ""


@dataclass
class VerificationResult:
    """Complete verification result for a single BibTeX entry."""

    entry: BibEntry
    status: VerificationStatus
    api_result: Optional[APIResult] = None
    metadata_issues: list[MetadataIssue] = field(default_factory=list)
    relevance: Optional[RelevanceResult] = None
    error_message: Optional[str] = None

    @property
    def has_missing_doi(self) -> bool:
        return self.entry.doi is None and self.api_result is not None and self.api_result.doi is not None

    @property
    def suggested_doi(self) -> Optional[str]:
        if self.has_missing_doi:
            return self.api_result.doi
        return None


@dataclass
class FileReport:
    """Verification report for a single .bib file."""

    file_path: str
    results: list[VerificationResult] = field(default_factory=list)

    @property
    def verified_count(self) -> int:
        return sum(1 for r in self.results if r.status == VerificationStatus.VERIFIED)

    @property
    def likely_match_count(self) -> int:
        return sum(1 for r in self.results if r.status == VerificationStatus.LIKELY_MATCH)

    @property
    def not_found_count(self) -> int:
        return sum(1 for r in self.results if r.status == VerificationStatus.NOT_FOUND)

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.results if r.status == VerificationStatus.SKIPPED)

    @property
    def missing_doi_count(self) -> int:
        return sum(1 for r in self.results if r.has_missing_doi)

    @property
    def total(self) -> int:
        return len(self.results)
