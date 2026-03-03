"""Tests for existence verification logic (unit tests for matching functions)."""

from __future__ import annotations

from sourceror.config import Config
from sourceror.reporting.models import APIResult, BibEntry
from sourceror.verification.existence import _title_similarity, _author_overlap, _best_match


class TestTitleSimilarity:
    def test_identical(self):
        assert _title_similarity("Hello World", "Hello World") == 1.0

    def test_case_insensitive(self):
        sim = _title_similarity("Hello World", "hello world")
        assert sim == 1.0

    def test_latex_stripped(self):
        sim = _title_similarity(r"\textbf{Hello} World", "Hello World")
        assert sim > 0.95

    def test_different(self):
        sim = _title_similarity("Completely Different", "Not Related At All")
        assert sim < 0.5

    def test_empty_string(self):
        assert _title_similarity("", "Something") == 0.0
        assert _title_similarity("Something", "") == 0.0


class TestAuthorOverlap:
    def test_full_overlap(self):
        overlap = _author_overlap(["smith", "doe"], ["John Smith", "Jane Doe"])
        assert overlap == 1.0

    def test_partial_overlap(self):
        overlap = _author_overlap(["smith", "doe"], ["John Smith", "Bob Jones"])
        assert overlap == 0.5

    def test_no_overlap(self):
        overlap = _author_overlap(["smith"], ["Jane Doe"])
        assert overlap == 0.0

    def test_empty_entry_authors(self):
        # No authors to compare = assume match
        assert _author_overlap([], ["John Smith"]) == 1.0

    def test_empty_api_authors(self):
        assert _author_overlap(["smith"], []) == 0.0


class TestBestMatch:
    def _make_candidate(self, title: str, year: int = 2024, authors: list[str] | None = None) -> APIResult:
        return APIResult(
            source="crossref",
            title=title,
            year=year,
            authors=authors or ["John Smith"],
        )

    def test_exact_match(self):
        entry = BibEntry(key="test", entry_type="article", title="Nash Equilibrium Synthesis", year=2024, authors=["John Smith"])
        candidates = [self._make_candidate("Nash Equilibrium Synthesis")]
        config = Config()
        match = _best_match(entry, candidates, config)
        assert match is not None
        assert match.title_similarity >= 0.95

    def test_below_threshold(self):
        entry = BibEntry(key="test", entry_type="article", title="Nash Equilibrium Synthesis", year=2024)
        candidates = [self._make_candidate("Completely Different Topic")]
        config = Config()
        match = _best_match(entry, candidates, config)
        assert match is None

    def test_year_out_of_tolerance(self):
        entry = BibEntry(key="test", entry_type="article", title="Nash Equilibrium Synthesis", year=2024)
        candidates = [self._make_candidate("Nash Equilibrium Synthesis", year=2020)]
        config = Config()
        match = _best_match(entry, candidates, config)
        assert match is None

    def test_year_within_tolerance(self):
        entry = BibEntry(key="test", entry_type="article", title="Nash Equilibrium Synthesis", year=2024)
        candidates = [self._make_candidate("Nash Equilibrium Synthesis", year=2023)]
        config = Config()
        match = _best_match(entry, candidates, config)
        assert match is not None

    def test_picks_best_of_multiple(self):
        entry = BibEntry(key="test", entry_type="article", title="Nash Equilibrium Synthesis", year=2024, authors=["John Smith"])
        candidates = [
            self._make_candidate("Nash Equilibrium Overview", authors=["Jane Doe"]),
            self._make_candidate("Nash Equilibrium Synthesis", authors=["John Smith"]),
        ]
        config = Config()
        match = _best_match(entry, candidates, config)
        assert match is not None
        assert match.title == "Nash Equilibrium Synthesis"
