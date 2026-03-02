"""Configuration defaults for cite_verify."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # Paths
    repo_root: Path = field(default_factory=lambda: Path.cwd())
    cache_dir: Path = field(default_factory=lambda: Path.cwd() / ".cite_verify_cache")
    output_file: Path | None = None

    # API settings
    crossref_email: str = ""  # For polite pool access
    crossref_rps: float = 10.0
    semantic_scholar_rps: float = 1.0
    openalex_rps: float = 10.0
    max_retries: int = 3
    request_timeout: float = 30.0

    # Cache
    cache_ttl_days: int = 30

    # Matching thresholds
    title_similarity_threshold: float = 0.85
    year_tolerance: int = 1

    # Features
    check_relevance: bool = False
    only_missing_doi: bool = False
    fix: bool = False
    dry_run: bool = False

    # LLM
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Excluded directories (relative to repo root)
    exclude_dirs: list[str] = field(
        default_factory=lambda: [".claude", "node_modules", ".git", "__pycache__"]
    )
