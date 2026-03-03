"""Extract \\cite{} contexts from .tex files."""

from __future__ import annotations

import re
from pathlib import Path

# Match \cite{key1,key2} and variants like \citep, \citet, \citeauthor
_CITE_RE = re.compile(r"\\cite[tp]?\*?\{([^}]+)\}")


def extract_citation_contexts(tex_path: Path, context_chars: int = 300) -> dict[str, list[str]]:
    """Extract surrounding text for each \\cite{key} in a .tex file.

    Returns a dict mapping citation keys to lists of context strings
    (a key may be cited multiple times).
    """
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    contexts: dict[str, list[str]] = {}

    for match in _CITE_RE.finditer(text):
        keys_str = match.group(1)
        keys = [k.strip() for k in keys_str.split(",")]

        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)
        surrounding = text[start:end].strip()
        # Clean up LaTeX noise for readability
        surrounding = re.sub(r"\s+", " ", surrounding)

        for key in keys:
            if key:
                contexts.setdefault(key, []).append(surrounding)

    return contexts


def discover_tex_files(root: Path, exclude_dirs: list[str] | None = None) -> list[Path]:
    """Find all .tex files under root, excluding specified directories."""
    exclude = set(exclude_dirs or [])
    results = []
    for tex_path in sorted(root.rglob("*.tex")):
        if any(part in exclude for part in tex_path.relative_to(root).parts):
            continue
        results.append(tex_path)
    return results
