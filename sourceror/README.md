# sourceror

A CLI tool that verifies academic citations against CrossRef, Semantic Scholar, and OpenAlex. It checks whether your BibTeX entries or PDF references correspond to real publications, finds missing DOIs, detects metadata discrepancies, and optionally checks citation relevance using an LLM.

## Installation

Requires Python 3.11+.

```bash
# Core tool (BibTeX verification)
pipx install sourceror

# With PDF support
pipx install "sourceror[pdf]"

# With LLM relevance checking + secure token storage
pipx install "sourceror[llm,keyring]"

# Everything
pipx install "sourceror[all]"
```

Or with pip:

```bash
pip install sourceror
```

### Development

```bash
git clone https://github.com/SJ-Jordaan/sourceror.git
cd sourceror
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
```

## Quick Start

```bash
# Verify all .bib files in the current directory
sourceror

# Verify a specific file
sourceror references.bib

# Verify citations from a PDF
sourceror paper.pdf

# Write output to a Markdown report
sourceror -o report.md references.bib
```

## Features

### Verification Pipeline

Each citation is checked through a cascading API strategy:

1. **If DOI exists** — Verify directly via CrossRef, then Semantic Scholar, then OpenAlex
2. **If no DOI** — Fuzzy title search across all three APIs, matching on:
   - Title similarity >= 85% (via `difflib.SequenceMatcher`)
   - Author surname overlap
   - Year within ±1

Entries are classified as:
- **Verified** — Exact or near-exact match found (title similarity >= 95%)
- **Likely Match** — Good match found (85-95% similarity)
- **Not Found** — No match in any database
- **Skipped** — `@online`/`@misc` with URL only, or entries marked "Submitted"

### PDF Support

Verify citations directly from PDF files without needing BibTeX source:

```bash
sourceror paper.pdf
```

Sourceror extracts the reference list from the PDF, parses individual references, and runs the same verification pipeline. It also extracts citation contexts from the body text for relevance checking. Requires the `pdf` extra (`pipx install "sourceror[pdf]"`).

### Finding Missing DOIs

```bash
# Only check entries that are missing DOIs
sourceror --only-missing-doi

# Preview what DOIs would be added
sourceror --only-missing-doi --dry-run

# Auto-add suggested DOIs to .bib files
sourceror --only-missing-doi --fix
```

### Auto-Fix Mode

The `--fix` flag writes suggested metadata back into your .bib files:

```bash
# Preview changes without modifying files
sourceror --dry-run

# Apply changes (adds missing DOIs, pages, volume, publisher, number)
sourceror --fix
```

This only **adds** missing fields — it never modifies existing values. Metadata discrepancies (year/type mismatches) must be reviewed manually.

### LLM Relevance Checking

Optionally check whether citations are contextually relevant to how they're used. Requires the `llm` extra and an Anthropic API key.

```bash
# Store your token securely (requires keyring extra)
sourceror --set-token

# Run with relevance checking
sourceror --check-relevance
```

The token is stored in your system keychain (macOS Keychain, Windows Credential Manager, or Linux Secret Service). Alternatively, set the `ANTHROPIC_API_KEY` environment variable.

### CrossRef Polite Pool

For better rate limits, provide your email for CrossRef's polite pool:

```bash
sourceror --email you@university.edu
```

### Cache

API responses are cached in `.sourceror_cache/` with a 30-day TTL. The first run takes ~1-2 minutes per 50 entries; subsequent runs are near-instant.

```bash
sourceror --clear-cache
```

## Report Format

The Markdown report includes:

| Section | Description |
|---------|-------------|
| **Summary table** | Per-file counts of verified / likely / not found / skipped / missing DOI |
| **Not Found** | Entries that couldn't be verified in any database |
| **Metadata Discrepancies** | Year mismatches, entry type mismatches |
| **Missing DOIs** | Suggested DOIs with match confidence and source API |
| **Suggested Completions** | Missing pages, volume, number, publisher |
| **Relevance Issues** | Citations that may not match their context (if `--check-relevance`) |
| **Verified entries** | Collapsed list of all verified entries with DOIs |

## Rate Limits

| API | Requests/sec | Notes |
|-----|-------------|-------|
| CrossRef | 10 | 50 with polite pool (via `--email`) |
| Semantic Scholar | 1 | Strict rate limiting; used as fallback |
| OpenAlex | 10 | Final fallback |

All APIs use exponential backoff on 429/5xx errors with max 3 retries.
