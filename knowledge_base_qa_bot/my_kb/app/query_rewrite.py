"""
LLM query rewrite: normalise user query before retrieval.

Handles synonym expansion, multi-language (Chinese → English),
and informal phrasing → canonical KB terminology.
Only used as a retrieval pre-processing step; the original query
is still shown to the LLM when generating the final answer.
"""
import os

from .retrieval import _get_client

_SYSTEM = """\
You are a query-normalisation assistant for a customer-support knowledge base.
The knowledge base covers: order cancellation, refund requests, return procedures, shipping timelines, and account / password management.

Rewrite the user query into concise standard English (≤10 words) that best matches the knowledge-base vocabulary.

Rules:
- Translate non-English input to English.
- Replace informal or uncommon words with standard KB terms:
    revoke / void / undo          → cancel
    money back / get my money     → refund request
    not returnable / cannot return → non-refundable
    how long does shipping take   → shipping timeline
    how many days / how long      → processing time
- ALWAYS preserve timing and condition modifiers — they are semantically critical:
    after delivery, before shipment, within 24 hours, within N days, already shipped, etc.
    Do NOT drop these phrases even when trimming filler words.
- Strip filler words; keep only the semantic core.
- Return ONLY the rewritten query string — no quotes, no explanation."""


def rewrite(query: str) -> str:
    """Return a rewritten, normalised version of *query* for retrieval."""
    response = _get_client().chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": query},
        ],
        temperature=0,
        max_tokens=32,
        timeout=10,
    )
    return response.choices[0].message.content.strip()
