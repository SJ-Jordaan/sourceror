"""LLM-based contextual relevance checking (optional feature)."""

from __future__ import annotations

import logging

from sourceror.reporting.models import BibEntry, RelevanceResult

logger = logging.getLogger(__name__)


async def check_relevance(
    entry: BibEntry,
    citation_contexts: list[str],
    abstract: str | None,
    model: str = "claude-sonnet-4-20250514",
    api_key: str | None = None,
) -> RelevanceResult:
    """Check if a citation is contextually relevant using the Anthropic API.

    Requires the `anthropic` package and an Anthropic API key
    (via --api-key, ANTHROPIC_API_KEY env var, or system keyring).
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping relevance check")
        return RelevanceResult(relevant=True, confidence=0.0, explanation="anthropic package not installed")

    from sourceror.credentials import get_api_key
    resolved_key = get_api_key(cli_override=api_key)
    if not resolved_key:
        return RelevanceResult(
            relevant=True, confidence=0.0,
            explanation="No Anthropic API key configured (use --set-token or ANTHROPIC_API_KEY)",
        )

    if not citation_contexts:
        return RelevanceResult(relevant=True, confidence=0.0, explanation="No citation contexts found")

    if not abstract:
        return RelevanceResult(relevant=True, confidence=0.0, explanation="No abstract available for comparison")

    contexts_text = "\n---\n".join(citation_contexts[:3])  # Limit to 3 contexts

    prompt = f"""Evaluate whether the following academic citation is relevant to how it's being used.

CITED PAPER:
Title: {entry.title}
Authors: {', '.join(entry.authors)}
Abstract: {abstract}

CITATION CONTEXTS (surrounding text where this paper is cited):
{contexts_text}

Respond with a JSON object:
{{"relevant": true/false, "confidence": 0.0-1.0, "explanation": "brief reason"}}

Consider: Is the cited paper's topic genuinely related to the point being made? A citation doesn't need to be a perfect match, but it should be defensible."""

    import asyncio
    import json

    client = anthropic.Anthropic(api_key=resolved_key, timeout=30.0)

    try:
        message = await asyncio.to_thread(
            client.messages.create,
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        logger.warning("Invalid Anthropic API key — skipping relevance checks")
        return RelevanceResult(relevant=True, confidence=0.0, explanation="Invalid API key")
    except (anthropic.APIError, anthropic.APITimeoutError) as e:
        logger.warning("Anthropic API error: %s", e)
        return RelevanceResult(relevant=True, confidence=0.0, explanation=f"API error: {e}")

    try:
        text = message.content[0].text.strip()
        # Extract JSON from potential markdown code blocks
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 3:
                inner = parts[1]
            else:
                inner = parts[1]
            # Strip language tag (e.g. "json\n")
            inner = inner.split("\n", 1)[-1] if "\n" in inner else inner
            text = inner.strip()
        data = json.loads(text)
        return RelevanceResult(
            relevant=data.get("relevant", True),
            confidence=data.get("confidence", 0.5),
            explanation=data.get("explanation", ""),
        )
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Failed to parse LLM relevance response: %s", e)
        return RelevanceResult(relevant=True, confidence=0.0, explanation=f"Parse error: {e}")
