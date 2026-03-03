"""Tests for report generation."""

from __future__ import annotations

from sourceror.reporting.markdown import generate_report
from sourceror.reporting.models import (
    APIResult,
    BibEntry,
    FileReport,
    RelevanceResult,
    VerificationResult,
    VerificationStatus,
)


class TestGenerateReport:
    def test_empty_report(self):
        report = generate_report([], check_relevance=False)
        assert "Citation Verification Report" in report
        assert "Total entries: 0" in report

    def test_basic_report(self):
        entry = BibEntry(key="smith2024", entry_type="article", title="A Paper")
        result = VerificationResult(entry=entry, status=VerificationStatus.VERIFIED)
        fr = FileReport(file_path="test.bib", results=[result])
        report = generate_report([fr])
        assert "test.bib" in report
        assert "1" in report  # total count

    def test_not_found_section(self):
        entry = BibEntry(key="missing2024", entry_type="article", title="Missing Paper", authors=["John Smith"], year=2024)
        result = VerificationResult(entry=entry, status=VerificationStatus.NOT_FOUND)
        fr = FileReport(file_path="test.bib", results=[result])
        report = generate_report([fr])
        assert "Not Found" in report
        assert "missing2024" in report

    def test_low_confidence_pdf_section(self):
        entry = BibEntry(
            key="pdf_ref_1", entry_type="article", title="Some Paper",
            input_format="pdf", parse_confidence=0.3,
        )
        result = VerificationResult(entry=entry, status=VerificationStatus.NOT_FOUND)
        fr = FileReport(file_path="paper.pdf", results=[result])
        report = generate_report([fr])
        assert "Low-Confidence" in report
        assert "pdf_ref_1" in report

    def test_no_low_confidence_for_bibtex(self):
        entry = BibEntry(key="test", entry_type="article", title="A Paper")
        result = VerificationResult(entry=entry, status=VerificationStatus.VERIFIED)
        fr = FileReport(file_path="test.bib", results=[result])
        report = generate_report([fr])
        assert "Low-Confidence" not in report

    def test_relevance_issues_shown(self):
        entry = BibEntry(key="irrelevant", entry_type="article", title="Wrong Paper")
        relevance = RelevanceResult(relevant=False, confidence=0.9, explanation="Not related")
        result = VerificationResult(
            entry=entry, status=VerificationStatus.VERIFIED,
            relevance=relevance,
        )
        fr = FileReport(file_path="test.bib", results=[result])
        report = generate_report([fr], check_relevance=True)
        assert "Relevance Issues" in report
        assert "Not related" in report

    def test_missing_doi_section(self):
        entry = BibEntry(key="nodoi", entry_type="article", title="No DOI Paper")
        api = APIResult(source="crossref", doi="10.1234/suggested", title_similarity=0.98)
        result = VerificationResult(
            entry=entry, status=VerificationStatus.VERIFIED, api_result=api,
        )
        fr = FileReport(file_path="test.bib", results=[result])
        report = generate_report([fr])
        assert "Missing DOIs" in report
        assert "10.1234/suggested" in report
