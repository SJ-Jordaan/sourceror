"""Extract references and citation contexts from PDF files."""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

from sourceror.reporting.models import BibEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

# Unicode ligature map (U+FB00–U+FB06)
_LIGATURE_MAP = str.maketrans({
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",  # long s + t
    "\ufb06": "st",
})

# Dash-like characters → ASCII hyphen
_DASH_MAP = str.maketrans({
    "\u2013": "-",   # en-dash
    "\u2014": "--",  # em-dash
    "\u2212": "-",   # minus sign
    "\u00ad": "",    # soft hyphen (remove)
    "\u2010": "-",   # hyphen
    "\u2011": "-",   # non-breaking hyphen
})

# Quote normalization → straight quotes
_QUOTE_MAP = str.maketrans({
    "\u2018": "'",   # left single
    "\u2019": "'",   # right single
    "\u201a": "'",   # single low-9
    "\u201c": '"',   # left double
    "\u201d": '"',   # right double
    "\u201e": '"',   # double low-9
    "\u00ab": '"',   # left guillemet
    "\u00bb": '"',   # right guillemet
})


def _normalize_text(text: str) -> str:
    """Normalize Unicode ligatures, dashes, quotes, and apply NFC normalization."""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_LIGATURE_MAP)
    text = text.translate(_DASH_MAP)
    text = text.translate(_QUOTE_MAP)
    return text


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting artifacts from extracted text."""
    # Protect escaped characters with placeholders before stripping
    _esc_map = {}
    def _protect_escape(m: re.Match) -> str:
        key = f"\x00ESC{len(_esc_map)}\x00"
        _esc_map[key] = m.group(1)
        return key
    text = re.sub(r"\\([*_`\[\]#>])", _protect_escape, text)
    # Unwrap markdown links: [text](url) → text url
    text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", r"\1 \2", text)
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}", "", text)
    text = re.sub(r"_{1,3}", "", text)
    # Remove code markers
    text = re.sub(r"`+", "", text)
    # Remove heading markers (leftover from inline text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    # Restore escaped characters
    for key, char in _esc_map.items():
        text = text.replace(key, char)
    return text


# ---------------------------------------------------------------------------
# Reference section detection
# ---------------------------------------------------------------------------

# Common reference section heading names (case-insensitive matching)
_REF_HEADING_NAMES = (
    "References",
    "Bibliography",
    "Works Cited",
    "Literature Cited",
    "Literature",
    "Cited Literature",
    "Reference List",
    "References and Notes",
    # German
    "Literatur",
    "Literaturverzeichnis",
    "Quellenverzeichnis",
    # French
    "Bibliographie",
    # Spanish
    "Referencias",
    # Italian
    "Riferimenti",
    "Riferimenti bibliografici",
)

# Build alternation pattern from names
_ref_names_pattern = "|".join(re.escape(name) for name in _REF_HEADING_NAMES)

# Matches: ## References, ## **References**, ### Bibliography, ## 7. References, etc.
_REF_HEADING_RE = re.compile(
    r"^#{1,3}\s*\*{0,2}\s*(?:\d+\.?\s+)?(" + _ref_names_pattern + r")\s*\*{0,2}\s*$",
    re.MULTILINE | re.IGNORECASE,
)
# Matches: **References** (standalone bold, no heading markers)
_REF_HEADING_BOLD_RE = re.compile(
    r"^\*\*\s*(?:\d+\.?\s+)?(" + _ref_names_pattern + r")\s*\*\*\s*$",
    re.MULTILINE | re.IGNORECASE,
)
# Matches: plain text "References" on its own line, optionally with section number
_REF_HEADING_PLAIN_RE = re.compile(
    r"^\s*(?:\d+\.?\s+)?(" + _ref_names_pattern + r")\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Sections that commonly follow the references
_POST_REF_HEADINGS = re.compile(
    r"^#{1,3}\s+(?:\d+\.?\s+)?"
    r"(?:Appendix|Appendices|Author\s+Biograph|About\s+the\s+Author|"
    r"Supplementary|Index|Vita|Curriculum\s+Vitae|Acknowledgment|"
    r"Acknowledgement|Proof\s+of\s+Theorem|Online\s+Appendix)\b",
    re.MULTILINE | re.IGNORECASE,
)
# Also match bold standalone post-ref headings
_POST_REF_BOLD = re.compile(
    r"^\*\*\s*(?:Appendix|Appendices|Author\s+Biograph|"
    r"Supplementary|Acknowledgment|Acknowledgement)\b",
    re.MULTILINE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Reference splitting patterns
# ---------------------------------------------------------------------------

# Bracketed numbered references: [1], [2], etc.
_BRACKET_NUM_RE = re.compile(r"^\s*\[(\d+)\]\s*", re.MULTILINE)

# Dot-numbered references: 1. Author..., 2. Author...
# Requires digit(s) + dot + space + capital letter (to avoid matching page numbers)
_DOT_NUM_RE = re.compile(r"^\s*(\d+)\.\s+(?=[A-Z\u00C0-\u024F])", re.MULTILINE)

# In-text numbered citations: [1], [2, 3], [1-5], [1,2,3]
_INLINE_CITE_RE = re.compile(r"\[(\d+(?:\s*[-\u2013,]\s*\d+)*)\]")

# Year extraction — more careful to avoid page ranges
_YEAR_PAREN_RE = re.compile(r"\((\d{4})[a-z]?\)")  # (2024) or (2024a)
_YEAR_BARE_RE = re.compile(r"(?<!\d)(?<![-\u2013:/.])(?:19|20)\d{2}(?![/-]?\d)")

# DOI extraction (Crossref regex, adapted)
_DOI_RE = re.compile(r"(?:doi\s*[:.]?\s*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[^\s,;\"')\]]+)", re.IGNORECASE)

# Matches the start of an author-year reference:
# "Surname, Firstname" or "Surname, F." at the beginning of a line.
# Handles lowercase particles (van, de, etc.) via optional prefix.
_AUTHOR_YEAR_START_RE = re.compile(
    r"^(?:[a-z]+\s+)?([A-Z\u00C0-\u024F][a-z\u00C0-\u024F'\u00B4`-]+,\s+[A-Z])",
    re.MULTILINE,
)

# Standalone page numbers / running headers to strip from reference text
_STANDALONE_PAGE_NUM_RE = re.compile(r"\n\s*\d{1,4}\s*\n")


# ---------------------------------------------------------------------------
# PDF markdown extraction (cached per path)
# ---------------------------------------------------------------------------

def _extract_markdown(pdf_path: Path) -> str:
    """Convert PDF to markdown using pymupdf4llm."""
    try:
        import pymupdf4llm
    except ImportError:
        raise ImportError(
            "PDF support requires the pdf extra. Install with: pip install 'sourceror[pdf]'"
        )
    return pymupdf4llm.to_markdown(str(pdf_path))


def _extract_and_cache_markdown(pdf_path: Path, *, _cache: dict[str, str] = {}) -> str:
    """Convert PDF to markdown, caching the result for repeated calls on the same file."""
    key = str(pdf_path)
    if key not in _cache:
        _cache[key] = _extract_markdown(pdf_path)
    return _cache[key]


# ---------------------------------------------------------------------------
# Reference section finding
# ---------------------------------------------------------------------------

def _find_reference_section(text: str) -> str | None:
    """Locate and return the reference section text.

    Tries heading formats in order: markdown heading, bold standalone, plain text.
    For ambiguous matches, prefers matches in the final third of the document.
    """
    candidates: list[re.Match] = []

    for pattern in (_REF_HEADING_RE, _REF_HEADING_BOLD_RE, _REF_HEADING_PLAIN_RE):
        for m in pattern.finditer(text):
            candidates.append(m)

    if not candidates:
        return None

    # Prefer the last match (most likely the actual bibliography, not a body-text mention)
    match = candidates[-1]

    ref_text = text[match.end():]

    # Trim at the next major post-reference section heading
    end_match = _POST_REF_HEADINGS.search(ref_text)
    if not end_match:
        end_match = _POST_REF_BOLD.search(ref_text)
    # Also trim at any generic markdown heading
    generic_heading = re.search(r"^#{1,3}\s+\w", ref_text, re.MULTILINE)

    # Use the earliest end marker
    end_pos = len(ref_text)
    if end_match:
        end_pos = min(end_pos, end_match.start())
    if generic_heading:
        end_pos = min(end_pos, generic_heading.start())

    ref_text = ref_text[:end_pos]
    return ref_text.strip()


# ---------------------------------------------------------------------------
# Reference splitting
# ---------------------------------------------------------------------------

def _split_numbered_references(ref_text: str, pattern: re.Pattern = _BRACKET_NUM_RE) -> list[tuple[int, str]]:
    """Split reference section by numbered markers, returning (number, text) pairs.

    Works with both [N] and N. styles via the pattern parameter.
    """
    markers = list(pattern.finditer(ref_text))
    if not markers:
        return []

    # Validate: at least 2 markers, mostly sequential
    if len(markers) < 2:
        # Allow single reference only if it's marker [1] or 1.
        if len(markers) == 1 and int(markers[0].group(1)) == 1:
            text = ref_text[markers[0].end():].strip()
            text = re.sub(r"\s+", " ", text)
            return [(1, text)] if text else []
        return []

    refs: list[tuple[int, str]] = []
    for i, marker in enumerate(markers):
        num = int(marker.group(1))
        start = marker.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(ref_text)
        text = ref_text[start:end].strip()
        # Remove standalone page numbers (header/footer artifacts)
        text = _STANDALONE_PAGE_NUM_RE.sub(" ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        if text:
            refs.append((num, text))
    return refs


def _split_author_year_references(ref_text: str) -> list[tuple[int, str]]:
    """Split reference section by author-year entries, returning (number, text) pairs.

    Detects references that start with "Surname, Firstname" at the beginning of a line.
    Handles lowercase particles (van, de, etc.).
    Each reference is assigned a sequential number.
    """
    markers = list(_AUTHOR_YEAR_START_RE.finditer(ref_text))
    if len(markers) < 2:
        return []

    refs: list[tuple[int, str]] = []
    for i, marker in enumerate(markers):
        start = marker.start()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(ref_text)
        text = ref_text[start:end].strip()
        # Remove standalone page numbers (header/footer artifacts)
        text = _STANDALONE_PAGE_NUM_RE.sub(" ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        if text and len(text) > 20:  # Skip very short fragments
            refs.append((i + 1, text))
    return refs


# ---------------------------------------------------------------------------
# DOI extraction
# ---------------------------------------------------------------------------

def _extract_doi(ref_str: str) -> str | None:
    """Extract DOI from a reference string, stripping trailing punctuation."""
    m = _DOI_RE.search(ref_str)
    if not m:
        return None
    doi = m.group(1).rstrip(".,;:)]}>")
    # Validate basic DOI structure
    if "/" not in doi or len(doi) < 8:
        return None
    return doi


# ---------------------------------------------------------------------------
# Year extraction
# ---------------------------------------------------------------------------

def _extract_year(ref_str: str) -> tuple[int | None, re.Match | None]:
    """Extract publication year from reference string.

    Tries parenthesized year first, then bare year avoiding page ranges and DOIs.
    Returns (year, match) or (None, None).
    """
    # Strategy 1: Parenthesized year — most reliable
    m = _YEAR_PAREN_RE.search(ref_str)
    if m:
        year = int(m.group(1))
        if 1900 <= year <= 2100:
            return year, m

    # Strategy 2: Bare year, but skip those inside page ranges (pp. 1945-1960)
    # and DOIs (10.1000/2024...)
    for m in _YEAR_BARE_RE.finditer(ref_str):
        year_str = m.group(0) if m.group(0) else m.group()
        pos = m.start()
        # Check if preceded by "pp." or "p." or a dash (page range)
        prefix = ref_str[max(0, pos - 10):pos]
        if re.search(r"(?:pp?\.?\s*|[-\u2013]\s*)$", prefix):
            continue
        # Check if inside a DOI (10.XXXX/...)
        if re.search(r"10\.\d{4,}/", ref_str[max(0, pos - 20):pos + 4]):
            continue
        year = int(ref_str[m.start():m.end()])
        if 1900 <= year <= 2100:
            return year, m

    return None, None


# ---------------------------------------------------------------------------
# Author name extraction
# ---------------------------------------------------------------------------

def _extract_author_names(author_part: str) -> list[str]:
    """Extract author names from an author string, handling various formats.

    Handles: "Last, First and Last, First", "Last, F. & Last, F.",
    "Last, F.M., Last, F.M.", "van der Berg, J.", "et al."
    """
    if not author_part or not author_part.strip():
        return []

    cleaned = author_part.strip()

    # Remove "et al." (including italic markdown artifacts)
    cleaned = re.sub(r"\*?et\s+al\.?\*?", "", cleaned, flags=re.IGNORECASE)
    # Remove "eds." / "ed." as standalone words — but NOT inside other words
    cleaned = re.sub(r"\b[Ee]ds?\.\s*", "", cleaned)
    # Remove "(Ed.)" or "(Eds.)" in parentheses
    cleaned = re.sub(r"\([Ee]ds?\.?\)", "", cleaned)

    # Strip trailing "and" as a whole word (not character-by-character!)
    cleaned = re.sub(r"\s+and\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip().rstrip(",").strip()

    if not cleaned:
        return []

    # Split on " and " or " & "
    parts = re.split(r"\s+(?:and|&)\s+", cleaned, flags=re.IGNORECASE)
    authors: list[str] = []
    for part in parts:
        # Further split on comma-separated authors in "Last, First, Last, First" format
        # Heuristic: split on commas followed by a capital letter that starts a new surname
        # (with optional lowercase particle like "van", "de")
        subparts = re.split(r",\s*(?=(?:[a-z]+\s+)?[A-Z\u00C0-\u024F][a-z\u00C0-\u024F'\u00B4`-]+,)", part)
        for sp in subparts:
            name = sp.strip().rstrip(".")
            # Remove trailing commas/semicolons
            name = name.rstrip(",;").strip()
            if name and len(name) > 1:
                authors.append(name)

    return authors


# ---------------------------------------------------------------------------
# Reference string parsing
# ---------------------------------------------------------------------------

def _parse_reference_string(ref_num: int, ref_str: str, source_file: str) -> BibEntry:
    """Parse a raw reference string into a BibEntry with confidence scoring."""
    # Normalize and clean
    ref_str = _normalize_text(ref_str)
    ref_str = _strip_markdown(ref_str)
    # Collapse whitespace after cleanup
    ref_str = re.sub(r"\s+", " ", ref_str).strip()

    confidence = 0.0
    strategy_used = "none"

    # Extract DOI early (most reliable field)
    doi = _extract_doi(ref_str)
    if doi:
        confidence += 0.15

    # Extract year
    year, year_match = _extract_year(ref_str)
    if year:
        confidence += 0.15

    title = ""
    authors: list[str] = []

    # Strategy 1: Quoted title — "Title Here" (IEEE/Chicago/Harvard)
    quoted_title_match = re.search(r'["\u201c](.{10,}?)["\u201d]', ref_str)
    if not quoted_title_match:
        # Try single quotes (Harvard style)
        quoted_title_match = re.search(r"'(.{10,}?)'", ref_str)
    if quoted_title_match:
        title = quoted_title_match.group(1).strip().rstrip(".")
        # Authors are everything before the quoted title or before the year
        author_end = quoted_title_match.start()
        if year_match and year_match.start() < quoted_title_match.start():
            author_end = year_match.start()
        author_part = ref_str[:author_end].strip().rstrip("(").strip()
        authors = _extract_author_names(author_part)
        confidence += 0.25
        strategy_used = "quoted_title"

    # Strategy 2: Vancouver style — "Last FM, Last FM. Title. Journal. Year;Vol(Iss):Pages."
    # Check early because the distinctive Year;Vol pattern is unambiguous
    if not title:
        # Look for the distinctive Year;Vol pattern
        vancouver_match = re.search(r"(\d{4})\s*;\s*(\d+)", ref_str)
        if vancouver_match:
            # In Vancouver style, author block ends at first ". " that's followed
            # by an uppercase letter (the title start)
            first_period = re.search(r"\.\s+(?=[A-Z])", ref_str)
            if first_period:
                author_part = ref_str[:first_period.start()].strip()
                rest = ref_str[first_period.end():].strip()
                # Title is the next sentence (up to the next ". " before the journal)
                # The journal is typically abbreviated (e.g. "Dev Psychol") and followed by Year;
                # Find where the journal/year block starts
                year_semi_pos = vancouver_match.start()
                # Title + journal is everything from rest up to year;vol
                # We need to find the title end within rest
                rest_before_year = rest[:max(0, year_semi_pos - first_period.end())].strip() if year_semi_pos > first_period.end() else rest
                # Title ends at ". " before the journal abbreviation
                title_end = re.search(r"\.\s+(?=[A-Z])", rest_before_year)
                if title_end:
                    title = rest_before_year[:title_end.start()].strip()
                else:
                    # Fallback: everything before the year;vol pattern
                    title = rest_before_year.rstrip(".").strip()
                authors = _extract_author_names(author_part)
                year = int(vancouver_match.group(1))
                if title:
                    confidence += 0.1
                    strategy_used = "vancouver"

    # Strategy 3: LNCS/Springer style — "Authors.: Title. In: Venue (Year)"
    if not title:
        # Look for ": " after the author block — LNCS uses colon after authors
        colon_match = re.search(r":\s+(?=[A-Z])", ref_str)
        if colon_match and colon_match.start() < len(ref_str) * 0.6:
            author_part = ref_str[:colon_match.start()].strip()
            rest = ref_str[colon_match.end():].strip()

            # Title ends at ". In:" or first ". " followed by a venue-like pattern
            in_match = re.search(r"\.\s+In[:\s]", rest)
            if in_match:
                title = rest[:in_match.start()].strip()
            else:
                title_match = re.match(r"(.{10,}?)\.\s", rest)
                if title_match:
                    title = title_match.group(1).strip()
                else:
                    title = rest.split("(")[0].strip().rstrip(".,")

            authors = _extract_author_names(author_part)
            if title:
                confidence += 0.15
                strategy_used = "lncs_colon"

    # Strategy 4: APA/general style — "Author (year). Title. Journal."
    if not title and year_match:
        before_year = ref_str[:year_match.start()].strip().rstrip("(").strip()
        after_year = ref_str[year_match.end():].strip().lstrip(")").lstrip(".").strip()

        authors = _extract_author_names(before_year)

        if after_year:
            # Title is the first sentence after the year
            title_match = re.match(r"\s*(.{10,}?(?<![A-Z])(?<!\.))\.\s", after_year)
            if title_match:
                title = title_match.group(1).strip()
            elif after_year:
                # Fallback: take everything up to first period or comma block
                title = re.split(r"\.\s", after_year, maxsplit=1)[0].strip()
            if title:
                confidence += 0.1
                strategy_used = "apa_year"

    # Clean title
    if title:
        title = title.strip().rstrip(".")
        # Remove any leftover markdown artifacts
        title = re.sub(r"[_*`]", "", title)

    # Fallback: if we got nothing, use the whole string as title
    if not title:
        title = ref_str[:200].strip()
        strategy_used = "fallback"

    # Score confidence based on extracted quality
    if title and len(title) > 15:
        confidence += 0.25
    elif title and len(title) > 5:
        confidence += 0.1

    if authors and len(authors) >= 1:
        # Check if author names look reasonable (contain both uppercase and lowercase)
        valid_authors = sum(1 for a in authors if re.search(r"[A-Z]", a) and len(a) > 2)
        if valid_authors >= 1:
            confidence += 0.2
        else:
            confidence += 0.05

    # Structural bonus: reference has recognizable academic structure
    has_venue = bool(re.search(r"\b(?:In[:\s]|Proc\.|Journal|Trans\.|Conf\.|Proceedings|vol\.|pp\.)", ref_str, re.IGNORECASE))
    if has_venue:
        confidence += 0.1

    # Penalty for fallback strategy
    if strategy_used == "fallback":
        confidence = min(confidence, 0.3)

    return BibEntry(
        key=f"pdf_ref_{ref_num}",
        entry_type="article",
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        source_file=str(source_file),
        input_format="pdf",
        parse_confidence=min(confidence, 1.0),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_references_from_pdf(pdf_path: Path) -> list[BibEntry]:
    """Extract reference list from PDF and parse into BibEntry objects."""
    markdown = _extract_and_cache_markdown(pdf_path)
    # Normalize the full text once
    markdown = _normalize_text(markdown)
    ref_section = _find_reference_section(markdown)

    if not ref_section:
        logger.warning("Could not locate reference section in %s", pdf_path)
        return []

    # Try splitting strategies in order of reliability:
    # 1. Bracketed numbers [1], [2] — most unambiguous
    # 2. Dot numbers 1., 2. — can false-match on numbered lists
    # 3. Author-year format — broadest fallback
    #
    # For dot-numbered, we also try author-year and pick whichever
    # finds more results (dot-numbered lists can match non-reference
    # numbered content like plagiarism declarations).
    refs = _split_numbered_references(ref_section, _BRACKET_NUM_RE)
    if not refs:
        dot_refs = _split_numbered_references(ref_section, _DOT_NUM_RE)
        ay_refs = _split_author_year_references(ref_section)
        # Validate dot-numbered: first number should be near 1,
        # and should find a reasonable number of refs
        dot_valid = (
            dot_refs
            and dot_refs[0][0] <= 3
            and len(dot_refs) >= 3
        )
        if dot_valid and len(dot_refs) >= len(ay_refs):
            refs = dot_refs
        elif ay_refs:
            refs = ay_refs
        elif dot_refs:
            refs = dot_refs

    if not refs:
        logger.warning(
            "No references found in %s -- reference section found but "
            "could not parse individual entries",
            pdf_path,
        )
        return []

    entries: list[BibEntry] = []
    for num, ref_str in refs:
        entry = _parse_reference_string(num, ref_str, str(pdf_path))
        entries.append(entry)

    logger.info("Extracted %d references from %s", len(entries), pdf_path)
    return entries


def extract_citation_contexts_from_pdf(pdf_path: Path) -> dict[str, list[str]]:
    """Extract citation contexts from PDF body text.

    Returns a dict mapping BibEntry keys (pdf_ref_N) to lists of context strings.
    """
    markdown = _extract_and_cache_markdown(pdf_path)
    markdown = _normalize_text(markdown)

    # Find where references start so we only look at body text
    ref_section_text = _find_reference_section(markdown)
    if ref_section_text:
        # Find the start of the reference section in the original text
        # Use the heading patterns to locate it
        for pattern in (_REF_HEADING_RE, _REF_HEADING_BOLD_RE, _REF_HEADING_PLAIN_RE):
            m = pattern.search(markdown)
            if m:
                body_text = markdown[:m.start()]
                break
        else:
            body_text = markdown
    else:
        body_text = markdown

    contexts: dict[str, list[str]] = {}
    context_chars = 300

    for match in _INLINE_CITE_RE.finditer(body_text):
        cite_str = match.group(1)

        # Parse citation numbers from patterns like "1", "2, 3", "1-5"
        ref_nums: list[int] = []
        for part in re.split(r"[,\s]+", cite_str):
            range_match = re.match(r"(\d+)\s*[-\u2013]\s*(\d+)", part)
            if range_match:
                start_num = int(range_match.group(1))
                end_num = int(range_match.group(2))
                ref_nums.extend(range(start_num, end_num + 1))
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
