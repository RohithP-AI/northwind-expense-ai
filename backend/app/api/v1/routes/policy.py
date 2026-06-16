import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.policy import (
    PolicyAnswerRequest,
    PolicyAnswerResponse,
    PolicySearchRequest,
    PolicySearchResponse,
    PolicySearchResult,
)
from app.services.anthropic_client import AnthropicNotConfigured
from app.services.policy_answer import policy_answer_service
from app.services.retrieval import retrieval_service

log = logging.getLogger("policy_route")

router = APIRouter()


@router.post("/search", response_model=PolicySearchResponse)
async def search_policies(
    payload: PolicySearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Embed the question and return the top-K most similar policy chunks.

    Pure embedding search — no LLM answer synthesis. Retained for tooling /
    debugging; the user-facing assistant uses POST /policy/answer instead.
    """
    try:
        chunks = await retrieval_service.search(db, payload.query, top_k=payload.top_k)
    except RuntimeError as exc:
        # e.g. OPENAI_API_KEY missing
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    # Overall confidence is taken from the best-matching chunk (first result).
    overall = chunks[0].confidence if chunks else "low"

    return PolicySearchResponse(
        query=payload.query,
        confidence=overall,
        results=[
            PolicySearchResult(
                document_id=c.document_id,
                page_number=c.page_number,
                section=c.section,
                chunk_text=c.chunk_text,
                similarity=c.similarity,
                confidence=c.confidence,
            )
            for c in chunks
        ],
    )


@router.post("/answer", response_model=PolicyAnswerResponse)
async def answer_policy_question(
    payload: PolicyAnswerRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Assistant-style policy Q&A.

    Retrieves relevant policy passages internally, asks Claude for one direct,
    grounded answer, and returns only the answer plus a coarse confidence level.
    Raw retrieval results, citations, and similarity scores are never exposed.
    """
    try:
        result = await policy_answer_service.answer(db, payload.question)
    except AnthropicNotConfigured:
        # Claude key missing — feature genuinely unavailable.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The policy assistant is temporarily unavailable.",
        ) from None
    except RuntimeError:
        # Retrieval unavailable (e.g. embeddings key missing).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The policy assistant is temporarily unavailable.",
        ) from None
    except Exception:
        # Anything else (AI provider error, DB/retrieval failure, …). Log the
        # real cause server-side; never leak internals (stack traces, prompts,
        # keys, DB details) to the client.
        log.exception("Policy answer generation failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate an answer right now. Please try again later.",
        ) from None

    return PolicyAnswerResponse(answer=result.answer, confidence=result.confidence)
