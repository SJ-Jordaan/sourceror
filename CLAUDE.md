# tools/ — Context for Claude

## cite_verify

Citation verification tool. Checks BibTeX entries against CrossRef, Semantic Scholar, and OpenAlex.

### Setup

```bash
cd tools
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Common commands

```bash
# Verify all bib files found in the repo
python -m cite_verify

# Verify a specific file
python -m cite_verify "../conference submissions/EUMAS2026/references.bib"

# Find entries missing DOIs
python -m cite_verify --only-missing-doi

# Auto-fix (adds missing fields, never overwrites existing)
python -m cite_verify --fix

# Generate markdown report
python -m cite_verify -o report.md
```

### Architecture

```
cite_verify/
  cli.py      — CLI entry point
  config.py   — Configuration
  cache.py    — API response cache (.cite_verify_cache/, 30-day TTL)
```

### Dependencies

bibtexparser>=2.0.0b7, httpx, tqdm. Optional: anthropic (for --check-relevance).

### Cache

`.cite_verify_cache/` stores API response JSON files (hash-named, 30-day TTL). This directory is gitignored.
