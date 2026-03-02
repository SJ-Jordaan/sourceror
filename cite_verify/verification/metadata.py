"""Field comparison and missing field detection."""

from __future__ import annotations

from cite_verify.reporting.models import APIResult, BibEntry, MetadataIssue


def check_metadata(entry: BibEntry, api: APIResult) -> list[MetadataIssue]:
    """Compare local BibTeX entry fields against API result, report discrepancies."""
    issues: list[MetadataIssue] = []

    # Year mismatch
    if entry.year and api.year and entry.year != api.year:
        issues.append(MetadataIssue(
            field="year",
            issue_type="mismatch",
            local_value=str(entry.year),
            api_value=str(api.year),
            message=f"Year mismatch: local {entry.year} vs API {api.year}",
        ))

    # Entry type mismatch
    if api.entry_type and entry.entry_type != api.entry_type:
        issues.append(MetadataIssue(
            field="entry_type",
            issue_type="mismatch",
            local_value=entry.entry_type,
            api_value=api.entry_type,
            message=f"Entry type mismatch: local @{entry.entry_type} vs API @{api.entry_type}",
        ))

    # Missing DOI
    if not entry.doi and api.doi:
        issues.append(MetadataIssue(
            field="doi",
            issue_type="missing",
            api_value=api.doi,
            message=f"Missing DOI — suggested: {api.doi}",
        ))

    # Missing pages
    if not entry.pages and api.pages:
        issues.append(MetadataIssue(
            field="pages",
            issue_type="suggestion",
            api_value=api.pages,
            message=f"Missing pages — suggested: {api.pages}",
        ))

    # Missing volume
    if not entry.volume and api.volume:
        issues.append(MetadataIssue(
            field="volume",
            issue_type="suggestion",
            api_value=api.volume,
            message=f"Missing volume — suggested: {api.volume}",
        ))

    # Missing number/issue
    if not entry.number and api.number:
        issues.append(MetadataIssue(
            field="number",
            issue_type="suggestion",
            api_value=api.number,
            message=f"Missing number — suggested: {api.number}",
        ))

    # Missing publisher
    if not entry.publisher and api.publisher:
        issues.append(MetadataIssue(
            field="publisher",
            issue_type="suggestion",
            api_value=api.publisher,
            message=f"Missing publisher — suggested: {api.publisher}",
        ))

    return issues
