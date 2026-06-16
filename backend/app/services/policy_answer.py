"""
Claude-powered policy Q&A (assistant-style).

Given a natural-language policy question this service:
  1. Retrieves the most relevant policy chunks via the existing RetrievalService
     (OpenAI embeddings + pgvector cosine search).
  2. De-duplicates and trims the chunks into a compact, token-bounded context.
  3. Asks Claude — with a schema-constrained tool call — to produce ONE direct,
     natural-language answer grounded only in that context.
  4. Derives a coarse High / Medium / Low confidence from *retrieval quality and
     answer grounding* (not Claude's unsupported self-confidence).

Design notes:
  * The public API returns only {answer, confidence}. This service returns a
    richer dataclass (it keeps the source chunks) so references can be surfaced
    later without a rewrite — but references are never sent to Claude or the
    client today, to keep token usage and the response small.
  * No retrieval/embedding/similarity terminology is ever exposed to the user.
  * Honest fallbacks: if retrieval is weak or Claude cannot answer from the
    context, we return a "contact the policy team" message at Low confidence
    rather than inventing policy. Conflicting policy is flagged for human review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.anthropic_client import extract_tool_use, get_anthropic_client
from app.services.retrieval import (
    HIGH_SIMILARITY,
    MEDIUM_SIMILARITY,
    RetrievedChunk,
    retrieval_service,
)

log = logging.getLogger("policy_answer")

# ── Token-budget controls ─────────────────────────────────────────────────────
# Retrieve a small number of high-quality chunks and bound the context size so a
# single answer call stays cheap. These are deliberately conservative.
TOP_K = 5
MAX_CHUNK_CHARS = 1200          # truncate any single oversized chunk
MAX_CONTEXT_CHARS = 6000        # hard cap across all chunks combined

# Standard, user-facing fallbacks (no internal/RAG terminology).
NO_ANSWER_MESSAGE = (
    "I could not find enough information in the available company policies to "
    "answer this confidently. Please contact the finance or travel-policy team."
)
CONFLICT_SUFFIX = (
    " The available policy information also appears inconsistent on this point, "
    "so please confirm with the finance or travel-policy team."
)

_ANSWER_TOOL = {
    "name": "record_answer",
    "description": (
        "Record a single, direct answer to the employee's expense-policy "
        "question, using ONLY the policy context provided in the prompt."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "answer_found": {
                "type": "boolean",
                "description": (
                    "True only if the provided policy context actually contains "
                    "enough information to answer the question. False if the "
                    "context is missing, off-topic, or insufficient."
                ),
            },
            "answer": {
                "type": "string",
                "description": (
                    "The direct, natural-language answer in one or a few short "
                    "sentences, grounded only in the provided policy context. If "
                    "answer_found is false, briefly state that the policies do "
                    "not cover this."
                ),
            },
            "requires_combining": {
                "type": "boolean",
                "description": (
                    "True if answering required interpreting or combining "
                    "multiple separate policy passages rather than reading one "
                    "clear statement."
                ),
            },
            "conflicting": {
                "type": "boolean",
                "description": (
                    "True if the provided policy passages give conflicting or "
                    "inconsistent guidance on the question."
                ),
            },
        },
        "required": ["answer_found", "answer"],
    },
}


@dataclass
class PolicyAnswer:
    """Internal result. The route exposes only `answer` and `confidence`."""

    answer: str
    confidence: str  # high | medium | low
    # Retained for future reference surfacing; never sent to Claude or the client.
    source_chunks: list[RetrievedChunk] = field(default_factory=list)


def _dedupe_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Drop chunks with identical text (keeps the first/best-ranked occurrence)."""
    seen: set[str] = set()
    unique: list[RetrievedChunk] = []
    for c in chunks:
        key = c.chunk_text.strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _build_context(chunks: list[RetrievedChunk]) -> str:
    """
    Render only the policy text (no document ids, pages, sections, or scores) as a
    compact, token-bounded block. Metadata is intentionally excluded to keep the
    prompt small and to avoid the model leaking source references.
    """
    blocks: list[str] = []
    total = 0
    for c in chunks:
        text = " ".join((c.chunk_text or "").split())
        if not text:
            continue
        if len(text) > MAX_CHUNK_CHARS:
            text = text[:MAX_CHUNK_CHARS].rstrip() + "…"
        if total + len(text) > MAX_CONTEXT_CHARS:
            remaining = MAX_CONTEXT_CHARS - total
            if remaining <= 0:
                break
            text = text[:remaining].rstrip() + "…"
        blocks.append(f"- {text}")
        total += len(text)
        if total >= MAX_CONTEXT_CHARS:
            break
    return "\n".join(blocks)


def _build_prompt(question: str, context: str) -> str:
    return f"""You are a corporate travel & expense policy assistant for Northwind Logistics.
Answer the employee's question using ONLY the company policy excerpts provided below.

RULES
- Use only the policy excerpts below. Do not rely on outside or "typical" policy knowledge.
- Do not invent or assume any rule, limit, approval requirement, or exception that is not
  stated in the excerpts.
- If the excerpts do not contain enough information to answer, set answer_found to false and
  say plainly that the company policies do not appear to cover this.
- If the excerpts give conflicting guidance, set conflicting to true.
- Write in natural, concise language a normal employee can understand.
- Do NOT mention documents, sources, sections, pages, excerpts, chunks, embeddings,
  retrieval, similarity, confidence scores, or any internal implementation detail.
- Call the record_answer tool with your result.

POLICY EXCERPTS
{context if context else "(no relevant policy excerpts were found)"}

QUESTION
{question}"""


def _derive_confidence(
    *,
    chunks: list[RetrievedChunk],
    answer_found: bool,
    requires_combining: bool,
    conflicting: bool,
) -> str:
    """
    Grounded confidence from retrieval quality + answer grounding.

    * low    — no/weak context, the model couldn't answer, or sources conflict
    * medium — relevant info exists but is moderate, or combining sections was needed
    * high   — at least one strongly relevant passage clearly answers the question
    """
    if not chunks or not answer_found or conflicting:
        return "low"

    best = chunks[0].similarity  # chunks are ordered best-first
    if best >= HIGH_SIMILARITY and not requires_combining:
        return "high"
    if best >= MEDIUM_SIMILARITY or requires_combining:
        return "medium"
    return "low"


class PolicyAnswerService:
    """Synthesises one grounded answer over the retrieved policy corpus."""

    async def answer(self, db: AsyncSession, question: str) -> PolicyAnswer:
        # 1. Retrieve policy context (raises RuntimeError if OPENAI_API_KEY missing,
        #    or a DB error if the query fails — both handled at the route).
        chunks = await retrieval_service.search(db, question, top_k=TOP_K)
        chunks = _dedupe_chunks(chunks)

        # If nothing relevant was retrieved, answer honestly without calling Claude.
        if not chunks:
            return PolicyAnswer(answer=NO_ANSWER_MESSAGE, confidence="low")

        context = _build_context(chunks)

        # 2. Ask Claude for one grounded answer (raises AnthropicNotConfigured if no
        #    key → 503 at the route).
        client = get_anthropic_client()
        resp = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            tools=[_ANSWER_TOOL],
            tool_choice={"type": "tool", "name": "record_answer"},
            messages=[{"role": "user", "content": _build_prompt(question, context)}],
        )
        data = extract_tool_use(resp, "record_answer")

        answer_found = bool(data.get("answer_found"))
        requires_combining = bool(data.get("requires_combining"))
        conflicting = bool(data.get("conflicting"))
        model_answer = (data.get("answer") or "").strip()

        confidence = _derive_confidence(
            chunks=chunks,
            answer_found=answer_found,
            requires_combining=requires_combining,
            conflicting=conflicting,
        )

        # 3. Honest fallbacks. Never surface a confident-sounding answer the
        #    context can't support.
        if not answer_found or not model_answer:
            answer_text = NO_ANSWER_MESSAGE
        elif conflicting:
            answer_text = model_answer + CONFLICT_SUFFIX
        else:
            answer_text = model_answer

        return PolicyAnswer(
            answer=answer_text,
            confidence=confidence,
            source_chunks=chunks,
        )


# Module-level singleton (the underlying clients are created on first use).
policy_answer_service = PolicyAnswerService()
