# cite_verify

A CLI tool that verifies academic citations against CrossRef, Semantic Scholar, and OpenAlex. It checks whether your BibTeX entries correspond to real publications, finds missing DOIs, detects metadata discrepancies, and optionally checks citation relevance using an LLM.

## Setup

Requires Python 3.11+.

```bash
cd tools
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# For LLM-based relevance checking (optional)
pip install -e ".[llm]"
```

## Quick Start

Run from the repository root with the venv activated:

```bash
# Verify all .bib files in the repo
python -m cite_verify

# Verify a specific file
python -m cite_verify "conference submissions/EUMAS2026/references.bib"

# Write output to a Markdown report
python -m cite_verify -o report.md
```

## Features

### Verification Pipeline

Each BibTeX entry is checked through a cascading API strategy:

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

### Auto-Skipping

The following entries are automatically skipped:
- `@online` and `@webpage` entries
- `@misc` entries with only a URL
- Entries with `note = {Submitted}` (unpublished work)

### Finding Missing DOIs

```bash
# Only check entries that are missing DOIs
python -m cite_verify --only-missing-doi

# Preview what DOIs would be added
python -m cite_verify --only-missing-doi --dry-run

# Auto-add suggested DOIs to .bib files
python -m cite_verify --only-missing-doi --fix
```

### Auto-Fix Mode

The `--fix` flag writes suggested metadata back into your .bib files:

```bash
# Preview changes without modifying files
python -m cite_verify --dry-run

# Apply changes (adds missing DOIs, pages, volume, publisher, number)
python -m cite_verify --fix
```

This only **adds** missing fields — it never modifies existing values. Metadata discrepancies (year/type mismatches) must be reviewed manually.

### LLM Relevance Checking

Optionally check whether citations are contextually relevant to how they're used in your .tex files. Requires the `anthropic` package and `ANTHROPIC_API_KEY` environment variable.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python -m cite_verify --check-relevance
```

This extracts `\cite{}` contexts from .tex files, retrieves paper abstracts from Semantic Scholar, and asks Claude whether each citation is relevant to its usage context. Costs approximately $0.15 for a full repo scan using Sonnet.

### CrossRef Polite Pool

For better rate limits, provide your email for CrossRef's polite pool:

```bash
python -m cite_verify --email you@university.edu
```

### Cache

API responses are cached in `.cite_verify_cache/` with a 30-day TTL. The first run takes ~1-2 minutes per 50 entries; subsequent runs are near-instant.

```bash
# Clear the cache
python -m cite_verify --clear-cache
```

### Verbose Logging

```bash
python -m cite_verify -v
```

Shows API requests, rate limiting, retry attempts, and match details.

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

## CLI Reference

```
usage: cite_verify [-h] [-o OUTPUT] [--only-missing-doi] [--check-relevance]
                   [--fix] [--dry-run] [--email EMAIL] [--clear-cache] [-v]
                   [files ...]

Verify academic citations against CrossRef, Semantic Scholar, and OpenAlex.

positional arguments:
  files                Specific .bib files to verify (default: all in repo)

options:
  -h, --help           show this help message and exit
  -o, --output OUTPUT  Output report file path (default: stdout)
  --only-missing-doi   Only check entries missing DOIs
  --check-relevance    Enable LLM-based relevance checking
  --fix                Write suggested DOIs/metadata back to .bib files
  --dry-run            Show what would be changed without modifying files
  --email EMAIL        Email for CrossRef polite pool (recommended)
  --clear-cache        Clear the response cache and exit
  -v, --verbose        Enable verbose logging
```

## Rate Limits

| API | Requests/sec | Notes |
|-----|-------------|-------|
| CrossRef | 10 | 50 with polite pool (via `--email`) |
| Semantic Scholar | 1 | Strict rate limiting; used as fallback |
| OpenAlex | 10 | Final fallback |

All APIs use exponential backoff on 429/5xx errors with max 3 retries.

## Interpreting Results

### Metadata Discrepancies

These require manual review:

- **Entry type mismatch** (e.g., `@inproceedings` vs `@article`) — Common when a conference paper was later published in a journal. Use the type matching the version you actually cite.
- **Year mismatch** — Can occur with preprints vs published versions. Check which version you referenced.

### Not Found

Possible reasons:
- The paper is too recent, unpublished, or a preprint not indexed by any API
- The title in your .bib file has significant typos or LaTeX artifacts
- The paper is from a niche venue not well-covered by these APIs

### Missing DOIs

Suggested DOIs are based on title + author matching. Always verify before using `--fix` on critical submissions — review the match confidence percentage and source API.
