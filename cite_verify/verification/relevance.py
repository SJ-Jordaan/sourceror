"""LLM-based contextual relevance checking (optional feature)."""

from __future__ import annotations

import logging

from cite_verify.reporting.models import BibEntry, RelevanceResult

logger = logging.getLogger(__name__)


async def check_relevance(
    entry: BibEntry,
    citation_contexts: list[str],
    abstract: str | None,
    model: str = "claude-sonnet-4-20250514",
) -> RelevanceResult:
    """Check if a citation is contextually relevant using the Anthropic API.

    Requires the `anthropic` package and ANTHROPIC_API_KEY environment variable.
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping relevance check")
        return RelevanceResult(relevant=True, confidence=0.0, explanation="anthropic package not installed")

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

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        import json
        text = message.content[0].text.strip()
        # Extract JSON from potential markdown code blocks
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)
        return RelevanceResult(
            relevant=data.get("relevant", True),
            confidence=data.get("confidence", 0.5),
            explanation=data.get("explanation", ""),
        )
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("Failed to parse LLM relevance response: %s", e)
        return RelevanceResult(relevant=True, confidence=0.0, explanation=f"Parse error: {e}")
