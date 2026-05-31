"""
Claude-powered per-receipt expense review.

For one receipt the engine:
  1. Builds a retrieval query from the receipt + trip context.
  2. Pulls the top policy chunks via the existing RetrievalService (pgvector).
  3. Asks Claude — with a schema-constrained tool call — to return a verdict.
  4. Defensively validates the model's citations/quotes against the retrieved
     chunks so nothing is fabricated.

Guardrails:
  * Quotes must be exact substrings of a retrieved chunk; fabricated quotes are
    dropped.
  * Citations must reference a retrieved document_id; fabricated ones are dropped.
  * If retrieval is weak/empty or policy is unclear, the verdict is needs_review.
  * Missing ANTHROPIC_API_KEY raises AnthropicNotConfigured (→ 503 at the route).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.employee import Employee
from app.models.receipt import Receipt
from app.models.submission import Submission
from app.services.anthropic_client import extract_tool_use, get_anthropic_client
from app.services.retrieval import RetrievedChunk, retrieval_service

log = logging.getLogger("ai_reviewer")

VERDICT_VALUES = ["compliant", "flagged", "rejected", "needs_review"]
CATEGORIES = ["flight", "hotel", "transport", "meal", "registration", "other"]

# How many policy chunks to put in front of the model.
TOP_K = 6

_REVIEW_TOOL = {
    "name": "record_verdict",
    "description": (
        "Record the compliance verdict for a single expense receipt, citing only "
        "the policy chunks provided in the prompt."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": VERDICT_VALUES,
                "description": (
                    "compliant = clearly allowed; flagged = allowed but unusual / "
                    "needs a closer human look; rejected = clearly violates policy; "
                    "needs_review = policy unclear or retrieved context insufficient."
                ),
            },
            "category": {
                "type": "string",
                "enum": CATEGORIES,
                "description": "Best-fit expense category for this receipt.",
            },
            "reasoning": {
                "type": "string",
                "description": "Concise explanation grounded in the cited policy text.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Your calibrated confidence in this verdict.",
            },
            "policy_citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "page_number": {"type": ["integer", "null"]},
                        "section": {"type": ["string", "null"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["document_id", "reason"],
                },
            },
            "quoted_policy_clauses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "quote": {
                            "type": "string",
                            "description": "Exact text copied verbatim from a provided policy chunk.",
                        },
                    },
                    "required": ["document_id", "quote"],
                },
            },
        },
        "required": ["verdict", "category", "reasoning", "confidence"],
    },
}


@dataclass
class ReviewResult:
    verdict: str
    category: str | None
    reasoning: str
    confidence: Decimal
    policy_citations: list[dict] = field(default_factory=list)
    quoted_policy_clauses: list[dict] = field(default_factory=list)


def _normalize(text: str) -> str:
    """Collapse whitespace for tolerant substring matching of quotes."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _build_query(submission: Submission, receipt: Receipt) -> str:
    parts = [
        receipt.category or "",
        receipt.merchant or "",
        f"${receipt.amount}" if receipt.amount is not None else "",
        submission.trip_purpose or "",
    ]
    base = " ".join(p for p in parts if p).strip()
    return base or (receipt.raw_extracted_text or "expense receipt")[:300]


def _render_chunks(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(no policy chunks were retrieved)"
    blocks = []
    for i, c in enumerate(chunks, 1):
        header = f"[chunk {i}] document_id={c.document_id}"
        if c.section:
            header += f" section={c.section!r}"
        if c.page_number is not None:
            header += f" page={c.page_number}"
        header += f" similarity={c.similarity}"
        blocks.append(f"{header}\n{c.chunk_text}")
    return "\n\n".join(blocks)


def _build_prompt(
    employee: Employee | None,
    submission: Submission,
    receipt: Receipt,
    chunks: list[RetrievedChunk],
) -> str:
    emp = (
        f"{employee.name} — grade {employee.grade}, {employee.title}, "
        f"{employee.department}, home base {employee.home_base}"
        if employee
        else f"employee_id {submission.employee_id} (details unavailable)"
    )
    return f"""You are a corporate travel & expense policy auditor for Northwind Logistics.
Decide whether the following receipt complies with company policy, using ONLY the
policy chunks provided below. Do not rely on outside knowledge of "typical" policy.

EMPLOYEE
{emp}

TRIP
purpose: {submission.trip_purpose}
dates: {submission.trip_start_date} to {submission.trip_end_date}

RECEIPT
merchant: {receipt.merchant or "(unknown)"}
date: {receipt.transaction_date or "(unknown)"}
amount: {receipt.amount if receipt.amount is not None else "(unknown)"} {receipt.currency}
category: {receipt.category or "(unknown)"}
raw extracted text:
\"\"\"
{(receipt.raw_extracted_text or "(none)")[:4000]}
\"\"\"

RETRIEVED POLICY CHUNKS
{_render_chunks(chunks)}

RULES
- Cite only the document_ids shown above. Never invent a citation.
- Every quoted clause must be copied verbatim from one of the chunks above.
- If the retrieved chunks do not actually address this expense, or policy is
  ambiguous, return verdict "needs_review" with low confidence rather than guessing.
- Call the record_verdict tool with your decision."""


def _validate_against_chunks(
    result_data: dict, chunks: list[RetrievedChunk]
) -> tuple[list[dict], list[dict]]:
    """Drop any citation/quote that isn't grounded in the retrieved chunks."""
    valid_docs = {c.document_id for c in chunks}
    chunk_texts = [_normalize(c.chunk_text) for c in chunks]

    citations = []
    for c in result_data.get("policy_citations") or []:
        if isinstance(c, dict) and c.get("document_id") in valid_docs:
            citations.append(
                {
                    "document_id": c["document_id"],
                    "page_number": c.get("page_number"),
                    "section": c.get("section"),
                    "reason": c.get("reason"),
                }
            )
        else:
            log.debug("Dropping ungrounded citation: %r", c)

    quotes = []
    for q in result_data.get("quoted_policy_clauses") or []:
        if not isinstance(q, dict):
            continue
        quote_text = q.get("quote") or ""
        norm = _normalize(quote_text)
        doc_ok = q.get("document_id") in valid_docs
        text_ok = bool(norm) and any(norm in ct for ct in chunk_texts)
        if doc_ok and text_ok:
            quotes.append({"document_id": q["document_id"], "quote": quote_text})
        else:
            log.debug("Dropping ungrounded quote: %r", q)

    return citations, quotes


class AIReviewerService:
    """Uses Claude to analyse a single receipt against retrieved policy chunks."""

    async def review_receipt(
        self,
        db: AsyncSession,
        submission: Submission,
        receipt: Receipt,
        employee: Employee | None = None,
    ) -> ReviewResult:
        # 1. Retrieve policy context. Retrieval needs OPENAI_API_KEY; if it's
        #    unavailable we proceed with no chunks (the model must then
        #    return needs_review per the rules).
        chunks: list[RetrievedChunk] = []
        try:
            query = _build_query(submission, receipt)
            chunks = await retrieval_service.search(db, query, top_k=TOP_K)
        except RuntimeError as exc:
            log.warning("Policy retrieval unavailable (%s); reviewing without context.", exc)

        # 2. Ask Claude (raises AnthropicNotConfigured if no key → 503 at route).
        client = get_anthropic_client()
        resp = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            tools=[_REVIEW_TOOL],
            tool_choice={"type": "tool", "name": "record_verdict"},
            messages=[
                {
                    "role": "user",
                    "content": _build_prompt(employee, submission, receipt, chunks),
                }
            ],
        )
        data = extract_tool_use(resp, "record_verdict")

        # 3. Validate / ground the citations and quotes.
        citations, quotes = _validate_against_chunks(data, chunks)

        verdict = data.get("verdict")
        if verdict not in VERDICT_VALUES:
            verdict = "needs_review"

        # If there were no policy chunks to ground a decision, don't let a
        # confident compliant/rejected stand — downgrade to needs_review.
        if not chunks and verdict in ("compliant", "rejected"):
            log.info("No policy context for receipt %s; downgrading to needs_review.", receipt.id)
            verdict = "needs_review"

        try:
            confidence = Decimal(str(data.get("confidence", 0))).quantize(Decimal("0.001"))
        except (ValueError, ArithmeticError):
            confidence = Decimal("0.000")
        confidence = max(Decimal("0.000"), min(Decimal("1.000"), confidence))

        category = data.get("category")
        if category not in CATEGORIES:
            category = receipt.category

        return ReviewResult(
            verdict=verdict,
            category=category,
            reasoning=data.get("reasoning") or "No reasoning provided.",
            confidence=confidence,
            policy_citations=citations,
            quoted_policy_clauses=quotes,
        )


# Module-level singleton (the Anthropic client inside is created on first use).
ai_reviewer = AIReviewerService()
