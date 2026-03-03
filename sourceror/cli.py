"""CLI interface and orchestration for sourceror."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

from tqdm import tqdm

from sourceror.apis.crossref import CrossRefClient
from sourceror.apis.openalex import OpenAlexClient
from sourceror.apis.semantic_scholar import SemanticScholarClient
from sourceror.cache import DiskCache
from sourceror.config import Config
from sourceror.parsers.bibtex import discover_bib_files, parse_bib_file
from sourceror.parsers.latex import discover_tex_files, extract_citation_contexts
from sourceror.reporting.markdown import generate_report
from sourceror.reporting.models import (
    BibEntry,
    FileReport,
    VerificationResult,
    VerificationStatus,
)
from sourceror.verification.existence import verify_entry

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sourceror",
        description="Verify academic citations against CrossRef, Semantic Scholar, and OpenAlex.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific .bib or .pdf files to verify (default: all .bib files in repo)",
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
        help="Enable LLM-based relevance checking (requires Anthropic API key)",
    )
    parser.add_argument(
        "--api-key",
        help="Anthropic API key for relevance checking (overrides env var and keyring)",
    )
    parser.add_argument(
        "--set-token",
        action="store_true",
        help="Store Anthropic API token in system keyring",
    )
    parser.add_argument(
        "--clear-token",
        action="store_true",
        help="Remove Anthropic API token from system keyring",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show current configuration including token source",
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


async def run(
    config: Config,
    parsed_inputs: list[tuple[str, list[BibEntry]]],
    citation_contexts: dict[str, list[str]],
) -> list[FileReport]:
    """Run the verification pipeline.

    Args:
        config: Verification configuration.
        parsed_inputs: List of (source_label, entries) tuples.
        citation_contexts: Pre-collected citation contexts keyed by entry key.
    """
    cache = DiskCache(config.cache_dir, ttl_days=config.cache_ttl_days)

    crossref = CrossRefClient(cache, email=config.crossref_email, rps=config.crossref_rps, max_retries=config.max_retries, timeout=config.request_timeout)
    s2 = SemanticScholarClient(cache, rps=config.semantic_scholar_rps, max_retries=config.max_retries, timeout=config.request_timeout)
    openalex = OpenAlexClient(cache, email=config.crossref_email, rps=config.openalex_rps, max_retries=config.max_retries, timeout=config.request_timeout)

    file_reports: list[FileReport] = []

    try:
        for source_label, entries in parsed_inputs:
            print(f"\nVerifying: {source_label}", file=sys.stderr)

            if config.only_missing_doi:
                entries = [e for e in entries if e.doi is None and not e.should_skip()]

            report = FileReport(file_path=source_label)

            for entry in tqdm(entries, desc=Path(source_label).name, file=sys.stderr):
                result = await verify_entry(entry, crossref, s2, openalex, config)

                # Optional relevance check
                if config.check_relevance and result.api_result:
                    from sourceror.verification.relevance import check_relevance
                    entry_contexts = citation_contexts.get(entry.key, [])
                    if entry_contexts:
                        abstract = result.api_result.abstract
                        if not abstract and result.api_result.doi:
                            abstract = await s2.fetch_abstract(result.api_result.doi)
                        if abstract:
                            result.relevance = await check_relevance(
                                entry, entry_contexts, abstract, config.anthropic_model,
                                api_key=config.api_key_override,
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

    # Token management commands
    if args.set_token:
        try:
            from sourceror.credentials import set_api_key
        except ImportError:
            print("Error: keyring extra required. Install with: pip install 'sourceror[keyring]'", file=sys.stderr)
            return 1
        from getpass import getpass
        token = getpass("Enter Anthropic API key: ")
        if not token.strip():
            print("Error: empty token provided.", file=sys.stderr)
            return 1
        set_api_key(token.strip())
        print("Token stored in system keyring.", file=sys.stderr)
        return 0

    if args.clear_token:
        try:
            from sourceror.credentials import clear_api_key
        except ImportError:
            print("Error: keyring extra required. Install with: pip install 'sourceror[keyring]'", file=sys.stderr)
            return 1
        clear_api_key()
        print("Token removed from system keyring.", file=sys.stderr)
        return 0

    if args.show_config:
        from sourceror.credentials import get_api_key, get_key_source, mask_key
        key = get_api_key(cli_override=getattr(args, "api_key", None))
        print(f"Anthropic API key: {mask_key(key) if key else 'not configured'}")
        print(f"Source: {get_key_source()}")
        return 0

    config = Config(
        crossref_email=args.email,
        check_relevance=args.check_relevance,
        only_missing_doi=args.only_missing_doi,
        fix=args.fix,
        dry_run=args.dry_run,
        api_key_override=getattr(args, "api_key", None),
    )

    if args.clear_cache:
        cache = DiskCache(config.cache_dir)
        count = cache.clear()
        print(f"Cleared {count} cached responses.")
        return 0

    # Discover or use specified files
    parsed_inputs: list[tuple[str, list[BibEntry]]] = []
    all_contexts: dict[str, list[str]] = {}
    has_pdf_inputs = False

    if args.files:
        input_files = [Path(f) for f in args.files]
        for f in input_files:
            if not f.exists():
                print(f"Error: file not found: {f}", file=sys.stderr)
                return 1

        for f in input_files:
            if f.suffix.lower() == ".pdf":
                has_pdf_inputs = True
                try:
                    from sourceror.parsers.pdf import (
                        extract_citation_contexts_from_pdf,
                        extract_references_from_pdf,
                    )
                except ImportError:
                    print("Error: PDF support requires the pdf extra. Install with: pip install 'sourceror[pdf]'", file=sys.stderr)
                    return 1
                entries = extract_references_from_pdf(f)
                if not entries:
                    print(f"Warning: no references found in {f}", file=sys.stderr)
                    continue
                parsed_inputs.append((str(f), entries))
                # Collect PDF citation contexts
                if config.check_relevance:
                    pdf_contexts = extract_citation_contexts_from_pdf(f)
                    for key, ctx_list in pdf_contexts.items():
                        all_contexts.setdefault(key, []).extend(ctx_list)
            else:
                entries = parse_bib_file(f)
                parsed_inputs.append((str(f), entries))
    else:
        bib_files = discover_bib_files(config.repo_root, config.exclude_dirs)
        if not bib_files:
            print("No .bib files found.", file=sys.stderr)
            return 1
        print(f"Found {len(bib_files)} .bib file(s):", file=sys.stderr)
        for f in bib_files:
            print(f"  {f}", file=sys.stderr)
            parsed_inputs.append((str(f), parse_bib_file(f)))

    if not parsed_inputs:
        print("No files to verify.", file=sys.stderr)
        return 1

    # Warn if --fix used with PDF inputs
    if has_pdf_inputs and (config.fix or config.dry_run):
        print("Warning: --fix/--dry-run has no effect on PDF inputs (no source .bib to modify).", file=sys.stderr)

    # Collect .tex citation contexts for BibTeX inputs
    if config.check_relevance and not has_pdf_inputs:
        tex_files = discover_tex_files(config.repo_root, config.exclude_dirs)
        for tex_path in tex_files:
            try:
                contexts = extract_citation_contexts(tex_path)
                for key, ctx_list in contexts.items():
                    all_contexts.setdefault(key, []).extend(ctx_list)
            except Exception as e:
                logger.warning("Failed to parse %s: %s", tex_path, e)

    # Run verification
    file_reports = asyncio.run(run(config, parsed_inputs, all_contexts))

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
