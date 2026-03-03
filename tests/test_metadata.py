"""Tests for metadata verification."""

from __future__ import annotations

from sourceror.reporting.models import APIResult, BibEntry
from sourceror.verification.metadata import check_metadata


class TestCheckMetadata:
    def _entry(self, **kwargs) -> BibEntry:
        defaults = {"key": "test", "entry_type": "article", "title": "Test"}
        defaults.update(kwargs)
        return BibEntry(**defaults)

    def _api(self, **kwargs) -> APIResult:
        defaults = {"source": "crossref"}
        defaults.update(kwargs)
        return APIResult(**defaults)

    def test_year_mismatch(self):
        entry = self._entry(year=2024)
        api = self._api(year=2023)
        issues = check_metadata(entry, api)
        year_issues = [i for i in issues if i.field == "year"]
        assert len(year_issues) == 1
        assert year_issues[0].issue_type == "mismatch"

    def test_year_match_no_issue(self):
        entry = self._entry(year=2024)
        api = self._api(year=2024)
        issues = check_metadata(entry, api)
        year_issues = [i for i in issues if i.field == "year"]
        assert len(year_issues) == 0

    def test_entry_type_mismatch(self):
        entry = self._entry(entry_type="article")
        api = self._api(entry_type="inproceedings")
        issues = check_metadata(entry, api)
        type_issues = [i for i in issues if i.field == "entry_type"]
        assert len(type_issues) == 1

    def test_missing_doi(self):
        entry = self._entry()
        api = self._api(doi="10.1234/test")
        issues = check_metadata(entry, api)
        doi_issues = [i for i in issues if i.field == "doi"]
        assert len(doi_issues) == 1
        assert doi_issues[0].issue_type == "missing"
        assert doi_issues[0].api_value == "10.1234/test"

    def test_no_missing_doi_when_present(self):
        entry = self._entry(doi="10.1234/test")
        api = self._api(doi="10.1234/test")
        issues = check_metadata(entry, api)
        doi_issues = [i for i in issues if i.field == "doi"]
        assert len(doi_issues) == 0

    def test_suggested_pages(self):
        entry = self._entry()
        api = self._api(pages="1-15")
        issues = check_metadata(entry, api)
        page_issues = [i for i in issues if i.field == "pages"]
        assert len(page_issues) == 1
        assert page_issues[0].issue_type == "suggestion"

    def test_suggested_volume(self):
        entry = self._entry()
        api = self._api(volume="42")
        issues = check_metadata(entry, api)
        vol_issues = [i for i in issues if i.field == "volume"]
        assert len(vol_issues) == 1

    def test_suggested_publisher(self):
        entry = self._entry()
        api = self._api(publisher="Springer")
        issues = check_metadata(entry, api)
        pub_issues = [i for i in issues if i.field == "publisher"]
        assert len(pub_issues) == 1

    def test_no_issues_when_complete(self):
        entry = self._entry(
            year=2024, doi="10.1234/test", pages="1-15",
            volume="42", number="3", publisher="Springer",
        )
        api = self._api(
            year=2024, entry_type="article", doi="10.1234/test",
            pages="1-15", volume="42", number="3", publisher="Springer",
        )
        issues = check_metadata(entry, api)
        assert len(issues) == 0
