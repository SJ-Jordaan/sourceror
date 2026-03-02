"""BibTeX parsing, normalization, and LaTeX decoding."""

from __future__ import annotations

import re
from pathlib import Path

import bibtexparser
from bibtexparser.middlewares import LatexDecodingMiddleware

from cite_verify.reporting.models import BibEntry


# Regex to strip LaTeX commands and math for comparison
_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\{([^}]*)\}")
_LATEX_MATH = re.compile(r"\$([^$]*)\$")
_BRACES = re.compile(r"[{}]")


def strip_latex(text: str) -> str:
    """Remove LaTeX commands, math delimiters, and braces for clean comparison."""
    text = _LATEX_CMD.sub(r"\1", text)
    text = _LATEX_MATH.sub(r"\1", text)
    text = _BRACES.sub("", text)
    return text.strip()


def _parse_authors(author_str: str) -> list[str]:
    """Parse BibTeX author string into individual names."""
    if not author_str:
        return []
    authors = re.split(r"\s+and\s+", author_str)
    result = []
    for author in authors:
        author = author.strip()
        if "," in author:
            parts = author.split(",", 1)
            author = f"{parts[1].strip()} {parts[0].strip()}"
        author = _BRACES.sub("", author).strip()
        if author:
            result.append(author)
    return result


def _safe_int(value: str | None) -> int | None:
    """Try to parse an integer, return None on failure."""
    if value is None:
        return None
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


def _entry_to_bib_entry(entry: bibtexparser.model.Entry, source_file: str) -> BibEntry:
    """Convert a bibtexparser Entry to our BibEntry model."""
    fields = {f.key.lower(): f.value for f in entry.fields}

    return BibEntry(
        key=entry.key,
        entry_type=entry.entry_type.lower(),
        title=strip_latex(fields.get("title", "")),
        authors=_parse_authors(fields.get("author", "")),
        year=_safe_int(fields.get("year")),
        doi=fields.get("doi"),
        journal=fields.get("journal"),
        booktitle=fields.get("booktitle"),
        volume=fields.get("volume"),
        number=fields.get("number"),
        pages=fields.get("pages"),
        publisher=fields.get("publisher") or fields.get("organization"),
        url=fields.get("url"),
        note=fields.get("note"),
        raw_fields=fields,
        source_file=source_file,
    )


def parse_bib_file(path: Path) -> list[BibEntry]:
    """Parse a .bib file and return normalized BibEntry objects."""
    library = bibtexparser.parse_file(
        str(path),
        append_middleware=[LatexDecodingMiddleware()],
    )
    entries = []
    for entry in library.entries:
        entries.append(_entry_to_bib_entry(entry, str(path)))
    return entries


def discover_bib_files(root: Path, exclude_dirs: list[str] | None = None) -> list[Path]:
    """Find all .bib files under root, excluding specified directories."""
    exclude = set(exclude_dirs or [])
    results = []
    for bib_path in sorted(root.rglob("*.bib")):
        if any(part in exclude for part in bib_path.relative_to(root).parts):
            continue
        results.append(bib_path)
    return results
