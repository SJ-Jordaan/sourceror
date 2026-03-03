"""Extract references and citation contexts from PDF files."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sourceror.reporting.models import BibEntry

logger = logging.getLogger(__name__)

# Patterns for locating the reference section heading
_REF_HEADING_RE = re.compile(
    r"^#{1,3}\s*(References|Bibliography|REFERENCES|BIBLIOGRAPHY)\s*$",
    re.MULTILINE,
)
_REF_HEADING_BOLD_RE = re.compile(
    r"^\*\*(References|Bibliography|REFERENCES|BIBLIOGRAPHY)\*\*\s*$",
    re.MULTILINE,
)

# Numbered reference markers: [1], [2], etc.
_NUMBERED_REF_RE = re.compile(r"^\s*\[(\d+)\]\s*", re.MULTILINE)

# In-text numbered citations: [1], [2, 3], [1-5], [1,2,3]
_INLINE_CITE_RE = re.compile(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]")

# Year extraction
_YEAR_PAREN_RE = re.compile(r"\((\d{4})\)")
_YEAR_BARE_RE = re.compile(r"\b(19|20)\d{2}\b")


def _extract_markdown(pdf_path: Path) -> str:
    """Convert PDF to markdown using pymupdf4llm."""
    try:
        import pymupdf4llm
    except ImportError:
        raise ImportError(
            "PDF support requires the pdf extra. Install with: pip install 'sourceror[pdf]'"
        )
    return pymupdf4llm.to_markdown(str(pdf_path))


def _find_reference_section(text: str) -> str | None:
    """Locate and return the reference section text."""
    # Try markdown heading format first
    match = _REF_HEADING_RE.search(text)
    if not match:
        match = _REF_HEADING_BOLD_RE.search(text)
    if not match:
        # Last resort: look for "References" on its own line (plain text)
        plain_match = re.search(
            r"^(References|Bibliography|REFERENCES|BIBLIOGRAPHY)\s*$",
            text,
            re.MULTILINE,
        )
        if plain_match:
            match = plain_match

    if not match:
        return None

    ref_text = text[match.end() :]

    # Trim at the next major heading (Appendix, etc.) if present
    next_heading = re.search(r"^#{1,3}\s+\w", ref_text, re.MULTILINE)
    if next_heading:
        ref_text = ref_text[: next_heading.start()]

    return ref_text.strip()


def _split_numbered_references(ref_text: str) -> list[tuple[int, str]]:
    """Split reference section by [N] markers, returning (number, text) pairs."""
    markers = list(_NUMBERED_REF_RE.finditer(ref_text))
    if not markers:
        return []

    refs: list[tuple[int, str]] = []
    for i, marker in enumerate(markers):
        num = int(marker.group(1))
        start = marker.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(ref_text)
        text = ref_text[start:end].strip()
        # Clean up multiple whitespace
        text = re.sub(r"\s+", " ", text)
        if text:
            refs.append((num, text))
    return refs


def _parse_reference_string(ref_num: int, ref_str: str, source_file: str) -> BibEntry:
    """Parse a raw reference string into a BibEntry with confidence scoring."""
    confidence = 0.0

    # Extract year
    year = None
    year_match = _YEAR_PAREN_RE.search(ref_str)
    if not year_match:
        year_match = _YEAR_BARE_RE.search(ref_str)
    if year_match:
        year_str = year_match.group(0).strip("()")
        try:
            year = int(year_str)
            if 1900 <= year <= 2100:
                confidence += 0.2
            else:
                year = None
        except ValueError:
            pass

    # Try LNCS/IEEE style: Authors.: Title. In: Venue
    # Split on first colon that's after author names
    title = ""
    authors: list[str] = []

    # LNCS style: "Author, A., Author, B.: Title of paper. In: ..."
    colon_match = re.search(r":\s*(?=[A-Z])", ref_str)
    if colon_match and colon_match.start() < len(ref_str) // 2:
        author_part = ref_str[: colon_match.start()].strip()
        rest = ref_str[colon_match.end() :].strip()

        # Extract title: text up to the first period followed by a venue indicator
        # or up to the first period after 20+ characters
        title_match = re.match(r"(.{15,}?)\.\s", rest)
        if title_match:
            title = title_match.group(1).strip()
        else:
            # Take everything up to the year or end
            title = rest.split("(")[0].strip().rstrip(".,")

        # Parse authors from "Last, F., Last, F." format
        author_parts = re.split(r",\s*(?=[A-Z])", author_part)
        for part in author_parts:
            name = part.strip().rstrip(".")
            if name and len(name) > 1:
                authors.append(name)
    else:
        # APA style: "Author, A., & Author, B. (year). Title. Journal."
        if year_match:
            before_year = ref_str[: year_match.start()].strip().rstrip("(")
            after_year = ref_str[year_match.end() :].strip().lstrip(")").lstrip(".")
            after_year = after_year.strip()

            # Authors are before the year
            author_parts = re.split(r",\s*(?=&|\s[A-Z])", before_year)
            for part in author_parts:
                name = part.strip().lstrip("&").strip()
                if name and len(name) > 1:
                    authors.append(name)

            # Title is the next sentence after the year
            title_match = re.match(r"\s*(.+?)\.\s", after_year)
            if title_match:
                title = title_match.group(1).strip()
            elif after_year:
                title = after_year.split(".")[0].strip()

    # Fallback: if we got nothing, use the whole string as title
    if not title:
        title = ref_str[:200].strip()

    # Score confidence
    if title and len(title) > 10:
        confidence += 0.3
    if authors:
        confidence += 0.2
    # Bonus for having clear delimiters
    if ":" in ref_str or ("." in ref_str and year):
        confidence += 0.3

    return BibEntry(
        key=f"pdf_ref_{ref_num}",
        entry_type="article",  # Default; verification pipeline may correct this
        title=title,
        authors=authors,
        year=year,
        source_file=str(source_file),
        input_format="pdf",
        parse_confidence=min(confidence, 1.0),
    )


def extract_references_from_pdf(pdf_path: Path) -> list[BibEntry]:
    """Extract reference list from PDF and parse into BibEntry objects."""
    markdown = _extract_markdown(pdf_path)
    ref_section = _find_reference_section(markdown)

    if not ref_section:
        logger.warning("Could not locate reference section in %s", pdf_path)
        return []

    numbered_refs = _split_numbered_references(ref_section)

    if not numbered_refs:
        logger.warning(
            "No numbered references found in %s — reference section found but "
            "could not parse individual entries",
            pdf_path,
        )
        return []

    entries: list[BibEntry] = []
    for num, ref_str in numbered_refs:
        entry = _parse_reference_string(num, ref_str, str(pdf_path))
        entries.append(entry)

    logger.info("Extracted %d references from %s", len(entries), pdf_path)
    return entries


def extract_citation_contexts_from_pdf(pdf_path: Path) -> dict[str, list[str]]:
    """Extract citation contexts from PDF body text.

    Returns a dict mapping BibEntry keys (pdf_ref_N) to lists of context strings.
    """
    markdown = _extract_markdown(pdf_path)

    # Find where references start so we only look at body text
    ref_match = _REF_HEADING_RE.search(markdown)
    if not ref_match:
        ref_match = _REF_HEADING_BOLD_RE.search(markdown)
    if not ref_match:
        ref_match = re.search(
            r"^(References|Bibliography|REFERENCES|BIBLIOGRAPHY)\s*$",
            markdown,
            re.MULTILINE,
        )

    body_text = markdown[: ref_match.start()] if ref_match else markdown

    contexts: dict[str, list[str]] = {}
    context_chars = 300

    for match in _INLINE_CITE_RE.finditer(body_text):
        cite_str = match.group(1)

        # Parse citation numbers from patterns like "1", "2, 3", "1-5"
        ref_nums: list[int] = []
        for part in re.split(r"[,\s]+", cite_str):
            range_match = re.match(r"(\d+)\s*[-–]\s*(\d+)", part)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2))
                ref_nums.extend(range(start, end + 1))
            else:
                try:
                    ref_nums.append(int(part.strip()))
                except ValueError:
                    continue

        # Extract surrounding context
        start = max(0, match.start() - context_chars)
        end = min(len(body_text), match.end() + context_chars)
        surrounding = body_text[start:end].strip()
        surrounding = re.sub(r"\s+", " ", surrounding)

        for num in ref_nums:
            key = f"pdf_ref_{num}"
            contexts.setdefault(key, []).append(surrounding)

    return contexts


def discover_pdf_files(
    root: Path, exclude_dirs: list[str] | None = None
) -> list[Path]:
    """Find all .pdf files under root, excluding specified directories."""
    exclude = set(exclude_dirs or [])
    results = []
    for pdf_path in sorted(root.rglob("*.pdf")):
        if any(part in exclude for part in pdf_path.relative_to(root).parts):
            continue
        results.append(pdf_path)
    return results
