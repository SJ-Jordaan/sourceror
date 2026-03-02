"""CLI interface and orchestration for cite_verify."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

from tqdm import tqdm

from cite_verify.apis.crossref import CrossRefClient
from cite_verify.apis.openalex import OpenAlexClient
from cite_verify.apis.semantic_scholar import SemanticScholarClient
from cite_verify.cache import DiskCache
from cite_verify.config import Config
from cite_verify.parsers.bibtex import discover_bib_files, parse_bib_file
from cite_verify.parsers.latex import discover_tex_files, extract_citation_contexts
from cite_verify.reporting.markdown import generate_report
from cite_verify.reporting.models import (
    BibEntry,
    FileReport,
    VerificationResult,
    VerificationStatus,
)
from cite_verify.verification.existence import verify_entry

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cite_verify",
        description="Verify academic citations against CrossRef, Semantic Scholar, and OpenAlex.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific .bib files to verify (default: all .bib files in repo)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output report file path (default: stdout)",
    )
    parser.add_argument(
        "--only-missing-doi",
        action="store_true",
        help="Only check entries missing DOIs",
    )
    parser.add_argument(
        "--check-relevance",
        action="store_true",
        help="Enable LLM-based relevance checking (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Write suggested DOIs/metadata back to .bib files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files",
    )
    parser.add_argument(
        "--email",
        default="",
        help="Email for CrossRef polite pool (recommended)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the response cache and exit",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser


async def run(config: Config, bib_files: list[Path]) -> list[FileReport]:
    """Run the verification pipeline."""
    cache = DiskCache(config.cache_dir, ttl_days=config.cache_ttl_days)

    crossref = CrossRefClient(cache, email=config.crossref_email, rps=config.crossref_rps, max_retries=config.max_retries, timeout=config.request_timeout)
    s2 = SemanticScholarClient(cache, rps=config.semantic_scholar_rps, max_retries=config.max_retries, timeout=config.request_timeout)
    openalex = OpenAlexClient(cache, email=config.crossref_email, rps=config.openalex_rps, max_retries=config.max_retries, timeout=config.request_timeout)

    # Collect citation contexts if relevance checking
    all_contexts: dict[str, list[str]] = {}
    if config.check_relevance:
        tex_files = discover_tex_files(config.repo_root, config.exclude_dirs)
        for tex_path in tex_files:
            try:
                contexts = extract_citation_contexts(tex_path)
                for key, ctx_list in contexts.items():
                    all_contexts.setdefault(key, []).extend(ctx_list)
            except Exception as e:
                logger.warning("Failed to parse %s: %s", tex_path, e)

    file_reports: list[FileReport] = []

    try:
        for bib_path in bib_files:
            print(f"\nVerifying: {bib_path}", file=sys.stderr)
            entries = parse_bib_file(bib_path)

            if config.only_missing_doi:
                entries = [e for e in entries if e.doi is None and not e.should_skip()]

            report = FileReport(file_path=str(bib_path))

            for entry in tqdm(entries, desc=str(bib_path.name), file=sys.stderr):
                result = await verify_entry(entry, crossref, s2, openalex, config)

                # Optional relevance check
                if config.check_relevance and result.api_result:
                    from cite_verify.verification.relevance import check_relevance
                    entry_contexts = all_contexts.get(entry.key, [])
                    if entry_contexts:
                        # Fetch abstract from S2 if we don't have one yet
                        abstract = result.api_result.abstract
                        if not abstract and result.api_result.doi:
                            abstract = await s2.fetch_abstract(result.api_result.doi)
                        if abstract:
                            result.relevance = await check_relevance(
                                entry, entry_contexts, abstract, config.anthropic_model
                            )

                report.results.append(result)

            file_reports.append(report)

    finally:
        await crossref.close()
        await s2.close()
        await openalex.close()

    return file_reports


def apply_fixes(file_reports: list[FileReport], dry_run: bool = False) -> list[str]:
    """Apply suggested DOIs and metadata back to .bib files."""
    changes: list[str] = []

    # Group results by source file
    by_file: dict[str, list[VerificationResult]] = {}
    for fr in file_reports:
        for result in fr.results:
            if result.metadata_issues:
                by_file.setdefault(result.entry.source_file, []).append(result)

    for file_path, results in by_file.items():
        path = Path(file_path)
        if not path.exists():
            continue

        content = path.read_text(encoding="utf-8")
        original = content

        for result in results:
            for issue in result.metadata_issues:
                if issue.issue_type in ("missing", "suggestion") and issue.api_value:
                    # Find the entry block and add the field before the closing brace
                    entry_pattern = re.compile(
                        rf"(@\w+\{{{re.escape(result.entry.key)}\s*,.*?)\n\s*\}}",
                        re.DOTALL,
                    )
                    match = entry_pattern.search(content)
                    if match:
                        field_name = issue.field
                        # Check the field isn't already there
                        if not re.search(rf"^\s*{field_name}\s*=", match.group(1), re.MULTILINE):
                            value = issue.api_value
                            insertion = f",\n  {field_name:<12s} = {{{value}}}"
                            content = content[:match.end(1)] + insertion + content[match.end(1):]
                            changes.append(f"  {file_path}: {result.entry.key} — added {field_name} = {{{value}}}")

        if content != original:
            if dry_run:
                changes.insert(0, f"[DRY RUN] Would modify: {file_path}")
            else:
                path.write_text(content, encoding="utf-8")
                changes.insert(0, f"Modified: {file_path}")

    return changes


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    config = Config(
        crossref_email=args.email,
        check_relevance=args.check_relevance,
        only_missing_doi=args.only_missing_doi,
        fix=args.fix,
        dry_run=args.dry_run,
    )

    if args.clear_cache:
        cache = DiskCache(config.cache_dir)
        count = cache.clear()
        print(f"Cleared {count} cached responses.")
        return 0

    # Discover or use specified .bib files
    if args.files:
        bib_files = [Path(f) for f in args.files]
        for f in bib_files:
            if not f.exists():
                print(f"Error: file not found: {f}", file=sys.stderr)
                return 1
    else:
        bib_files = discover_bib_files(config.repo_root, config.exclude_dirs)
        if not bib_files:
            print("No .bib files found.", file=sys.stderr)
            return 1
        print(f"Found {len(bib_files)} .bib file(s):", file=sys.stderr)
        for f in bib_files:
            print(f"  {f}", file=sys.stderr)

    # Run verification
    file_reports = asyncio.run(run(config, bib_files))

    # Generate report
    report = generate_report(file_reports, check_relevance=config.check_relevance)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nReport written to: {args.output}", file=sys.stderr)
    else:
        print(report)

    # Apply fixes if requested
    if config.fix or config.dry_run:
        changes = apply_fixes(file_reports, dry_run=config.dry_run)
        if changes:
            print("\nChanges:", file=sys.stderr)
            for change in changes:
                print(change, file=sys.stderr)
        else:
            print("\nNo changes to apply.", file=sys.stderr)

    # Summary
    total = sum(fr.total for fr in file_reports)
    verified = sum(fr.verified_count for fr in file_reports)
    likely = sum(fr.likely_match_count for fr in file_reports)
    not_found = sum(fr.not_found_count for fr in file_reports)
    print(f"\nSummary: {verified} verified, {likely} likely matches, {not_found} not found (of {total} total)", file=sys.stderr)

    return 0
