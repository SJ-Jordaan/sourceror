"""Markdown report generation."""

from __future__ import annotations

from datetime import datetime

from sourceror.reporting.models import (
    FileReport,
    MetadataIssue,
    VerificationResult,
    VerificationStatus,
)


def generate_report(file_reports: list[FileReport], check_relevance: bool = False) -> str:
    """Generate a full Markdown verification report."""
    lines: list[str] = []
    lines.append("# Citation Verification Report")
    lines.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

    # Summary table
    lines.append("## Summary\n")
    lines.append("| File | Total | Verified | Likely | Not Found | Skipped | Missing DOI |")
    lines.append("|------|------:|--------:|-------:|----------:|--------:|------------:|")

    total_all = 0
    for fr in file_reports:
        total_all += fr.total
        lines.append(
            f"| `{fr.file_path}` | {fr.total} | {fr.verified_count} | "
            f"{fr.likely_match_count} | {fr.not_found_count} | "
            f"{fr.skipped_count} | {fr.missing_doi_count} |"
        )

    lines.append(f"\n**Total entries: {total_all}**\n")

    # Per-file detailed results
    for fr in file_reports:
        lines.append(f"---\n## {fr.file_path}\n")

        not_found = [r for r in fr.results if r.status == VerificationStatus.NOT_FOUND]
        mismatches = [r for r in fr.results if r.metadata_issues and any(i.issue_type == "mismatch" for i in r.metadata_issues)]
        missing_dois = [r for r in fr.results if r.has_missing_doi]
        suggestions = [r for r in fr.results if r.metadata_issues and any(i.issue_type == "suggestion" for i in r.metadata_issues)]
        errors = [r for r in fr.results if r.status == VerificationStatus.ERROR]
        relevance_issues = [r for r in fr.results if r.relevance and not r.relevance.relevant] if check_relevance else []

        # Low-confidence PDF-parsed references
        low_confidence = [r for r in fr.results if r.entry.input_format == "pdf" and r.entry.parse_confidence < 0.7]
        if low_confidence:
            lines.append("### Low-Confidence Parsed References\n")
            lines.append("These references were extracted from PDF with low confidence and may be parsed incorrectly:\n")
            for r in low_confidence:
                lines.append(f"- **`{r.entry.key}`**: {r.entry.title}")
                lines.append(f"  - Parse confidence: {r.entry.parse_confidence:.0%}")
            lines.append("")

        if not_found:
            lines.append("### Not Found\n")
            lines.append("These entries could not be verified in any academic database:\n")
            for r in not_found:
                lines.append(f"- **`{r.entry.key}`**: {r.entry.title}")
                if r.entry.authors:
                    lines.append(f"  - Authors: {', '.join(r.entry.authors)}")
                if r.entry.year:
                    lines.append(f"  - Year: {r.entry.year}")
            lines.append("")

        if mismatches:
            lines.append("### Metadata Discrepancies\n")
            for r in mismatches:
                lines.append(f"- **`{r.entry.key}`**: {r.entry.title}")
                for issue in r.metadata_issues:
                    if issue.issue_type == "mismatch":
                        lines.append(f"  - {issue.message}")
            lines.append("")

        if missing_dois:
            lines.append("### Missing DOIs\n")
            lines.append("These entries are missing DOIs. Suggested DOIs from API matches:\n")
            for r in missing_dois:
                lines.append(f"- **`{r.entry.key}`**: {r.entry.title}")
                lines.append(f"  - Suggested DOI: `{r.suggested_doi}`")
                if r.api_result:
                    lines.append(f"  - Match confidence: {r.api_result.title_similarity:.0%} (via {r.api_result.source})")
            lines.append("")

        if suggestions:
            lines.append("### Suggested Completions\n")
            for r in suggestions:
                suggestion_issues = [i for i in r.metadata_issues if i.issue_type == "suggestion"]
                if suggestion_issues:
                    lines.append(f"- **`{r.entry.key}`**: {r.entry.title}")
                    for issue in suggestion_issues:
                        lines.append(f"  - {issue.message}")
            lines.append("")

        if relevance_issues:
            lines.append("### Relevance Issues\n")
            for r in relevance_issues:
                lines.append(f"- **`{r.entry.key}`**: {r.entry.title}")
                lines.append(f"  - {r.relevance.explanation}")
                lines.append(f"  - Confidence: {r.relevance.confidence:.0%}")
            lines.append("")

        if errors:
            lines.append("### Errors\n")
            for r in errors:
                lines.append(f"- **`{r.entry.key}`**: {r.error_message}")
            lines.append("")

        # Verified entries (collapsed)
        verified = [r for r in fr.results if r.status in (VerificationStatus.VERIFIED, VerificationStatus.LIKELY_MATCH)]
        if verified:
            lines.append("<details>")
            lines.append(f"<summary>Verified entries ({len(verified)})</summary>\n")
            for r in verified:
                status_icon = "+" if r.status == VerificationStatus.VERIFIED else "~"
                doi_info = f" — DOI: {r.api_result.doi}" if r.api_result and r.api_result.doi else ""
                lines.append(f"- [{status_icon}] `{r.entry.key}`: {r.entry.title}{doi_info}")
            lines.append("\n</details>\n")

    return "\n".join(lines)
