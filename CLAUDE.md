# sourceror — Code Context

## Overview

Python 3.11+. Verifies academic citations against CrossRef, Semantic Scholar, and OpenAlex.
Accepts BibTeX (`.bib`) and PDF input. Optional LLM-backed relevance checking.
This directory is a git submodule (`github.com/SJ-Jordaan/sourceror`). Commits here must be pushed separately.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"   # core + pdf + llm + keyring
```

Subset extras: `[pdf]` (pymupdf), `[llm]` (anthropic), `[keyring]` (secure token storage).

## Module map

```
sourceror/
  cli.py              — argparse entry point, orchestration loop
  config.py           — Config dataclass (API keys, cache TTL, flags)
  cache.py            — DiskCache (hash-keyed JSON, TTL-based expiry)
  credentials.py      — keyring-backed token storage
  apis/
    base.py           — shared HTTP client, retries, rate limiting
    crossref.py       — CrossRef API client
    semantic_scholar.py — Semantic Scholar API client
    openalex.py       — OpenAlex API client
  parsers/
    bibtex.py         — discover/parse .bib files
    latex.py          — extract \cite{} contexts from .tex
    pdf.py            — PDF reference extraction (pymupdf)
  verification/
    existence.py      — does this entry refer to a real publication?
    metadata.py       — compare BibTeX fields to API metadata
    relevance.py      — LLM-backed relevance check (optional)
  reporting/
    models.py         — BibEntry, VerificationResult, FileReport, status enums
    markdown.py       — Markdown report generator
```

## CLI

Entry point: `sourceror = "sourceror.cli:main"`.

```bash
sourceror                              # verify all .bib files in CWD
sourceror references.bib               # verify a specific file
sourceror paper.pdf                    # verify references extracted from a PDF
sourceror --only-missing-doi           # filter
sourceror --fix                        # add missing fields (never overwrites)
sourceror -o report.md                 # write markdown report
sourceror --check-relevance            # requires [llm] extra + Anthropic key
```

## Cache

`.sourceror_cache/` (gitignored). Hash-keyed JSON files, default 30-day TTL. Configurable via `Config`.

## Dependencies

Core: `bibtexparser>=2.0.0b7`, `httpx>=0.27`, `tqdm>=4.66`.
Optional: `pymupdf` + `pymupdf4llm` (pdf), `anthropic` (llm), `keyring` (credentials).

## Testing

```bash
pytest                # tests/ directory
```
