from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.policy import (
    PolicySearchRequest,
    PolicySearchResponse,
    PolicySearchResult,
)
from app.services.retrieval import retrieval_service

router = APIRouter()


@router.post("/search", response_model=PolicySearchResponse)
async def search_policies(
    payload: PolicySearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Embed the question and return the top-K most similar policy chunks.

    Pure embedding search — no LLM answer synthesis at this stage.
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
