"""Tests for data models."""

from __future__ import annotations

from sourceror.reporting.models import (
    APIResult,
    BibEntry,
    FileReport,
    MetadataIssue,
    VerificationResult,
    VerificationStatus,
)


class TestBibEntry:
    def test_should_skip_online(self):
        entry = BibEntry(key="test", entry_type="online")
        assert entry.should_skip() is True

    def test_should_skip_webpage(self):
        entry = BibEntry(key="test", entry_type="webpage")
        assert entry.should_skip() is True

    def test_should_skip_misc_url_only(self):
        entry = BibEntry(key="test", entry_type="misc", url="http://example.com")
        assert entry.should_skip() is True

    def test_should_not_skip_misc_with_title(self):
        entry = BibEntry(key="test", entry_type="misc", title="A Title", url="http://example.com")
        assert entry.should_skip() is False

    def test_should_skip_submitted(self):
        entry = BibEntry(key="test", entry_type="article", note="Submitted to journal")
        assert entry.should_skip() is True

    def test_should_not_skip_normal(self):
        entry = BibEntry(key="test", entry_type="article", title="A Paper")
        assert entry.should_skip() is False

    def test_author_surnames(self):
        entry = BibEntry(
            key="test",
            entry_type="article",
            authors=["John Smith", "Jane {Doe}"],
        )
        assert entry.author_surnames == ["smith", "doe"]

    def test_author_surnames_empty(self):
        entry = BibEntry(key="test", entry_type="article")
        assert entry.author_surnames == []

    def test_default_input_format(self):
        entry = BibEntry(key="test", entry_type="article")
        assert entry.input_format == "bibtex"
        assert entry.parse_confidence == 1.0

    def test_pdf_input_format(self):
        entry = BibEntry(key="test", entry_type="article", input_format="pdf", parse_confidence=0.5)
        assert entry.input_format == "pdf"
        assert entry.parse_confidence == 0.5


class TestVerificationResult:
    def test_has_missing_doi(self):
        entry = BibEntry(key="test", entry_type="article")
        api = APIResult(source="crossref", doi="10.1234/test")
        result = VerificationResult(entry=entry, status=VerificationStatus.VERIFIED, api_result=api)
        assert result.has_missing_doi is True
        assert result.suggested_doi == "10.1234/test"

    def test_no_missing_doi_when_present(self):
        entry = BibEntry(key="test", entry_type="article", doi="10.1234/test")
        api = APIResult(source="crossref", doi="10.1234/test")
        result = VerificationResult(entry=entry, status=VerificationStatus.VERIFIED, api_result=api)
        assert result.has_missing_doi is False
        assert result.suggested_doi is None

    def test_no_missing_doi_when_no_api(self):
        entry = BibEntry(key="test", entry_type="article")
        result = VerificationResult(entry=entry, status=VerificationStatus.NOT_FOUND)
        assert result.has_missing_doi is False


class TestFileReport:
    def _make_result(self, status: VerificationStatus) -> VerificationResult:
        return VerificationResult(
            entry=BibEntry(key="test", entry_type="article"),
            status=status,
        )

    def test_counts(self):
        report = FileReport(file_path="test.bib")
        report.results = [
            self._make_result(VerificationStatus.VERIFIED),
            self._make_result(VerificationStatus.VERIFIED),
            self._make_result(VerificationStatus.LIKELY_MATCH),
            self._make_result(VerificationStatus.NOT_FOUND),
            self._make_result(VerificationStatus.SKIPPED),
            self._make_result(VerificationStatus.ERROR),
        ]
        assert report.total == 6
        assert report.verified_count == 2
        assert report.likely_match_count == 1
        assert report.not_found_count == 1
        assert report.skipped_count == 1

    def test_empty_report(self):
        report = FileReport(file_path="test.bib")
        assert report.total == 0
        assert report.verified_count == 0
