import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.serializers import serialize_verdict
from app.core.database import get_db
from app.models.receipt import Receipt
from app.models.submission import Submission
from app.models.verdict import Verdict
from app.schemas.verdict import VerdictWithOverridesRead
from app.services.ai_reviewer import ai_reviewer
from app.services.anthropic_client import AnthropicNotConfigured

router = APIRouter()


class ReviewResponse(BaseModel):
    submission_id: uuid.UUID
    status: str
    reviewed: int  # number of receipts newly reviewed in this call
    verdicts: list[VerdictWithOverridesRead]


# Submission status precedence, most-blocking first. A rejected receipt is the
# strongest signal; flagged and needs_review both want a human but rank below it;
# compliant only stands when every receipt is compliant.
_STATUS_PRECEDENCE = ["rejected", "flagged", "needs_review", "compliant"]


def _rollup_status(verdicts: list[str]) -> str:
    if not verdicts:
        return "pending"
    for level in _STATUS_PRECEDENCE:
        if level in verdicts:
            return level
    return "needs_review"


@router.post("/{submission_id}/review", response_model=ReviewResponse)
async def review_submission(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Run the AI reviewer over every not-yet-reviewed receipt in a submission.

    Existing verdicts are left untouched. The submission status is rolled up from
    all receipt verdicts once review completes.
    """
    submission = await db.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(
            selectinload(Submission.employee),
            selectinload(Submission.receipts)
            .selectinload(Receipt.verdict)
            .selectinload(Verdict.overrides),
        )
    )
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    if not submission.receipts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Submission has no receipts to review. Upload receipts first.",
        )

    reviewed = 0
    try:
        for receipt in submission.receipts:
            if receipt.verdict is not None:
                continue
            result = await ai_reviewer.review_receipt(
                db, submission, receipt, employee=submission.employee
            )
            verdict = Verdict(
                receipt_id=receipt.id,
                verdict=result.verdict,
                reasoning=result.reasoning,
                confidence=result.confidence,
                policy_citations=result.policy_citations,
                quoted_policy_clauses=result.quoted_policy_clauses,
            )
            verdict.overrides = []
            receipt.verdict = verdict  # populate both sides for serialization
            db.add(verdict)
            # Backfill the receipt category from the model if it wasn't extracted.
            if not receipt.category and result.category:
                receipt.category = result.category
            reviewed += 1
    except AnthropicNotConfigured as exc:
        # Roll back any partial verdicts by letting get_db handle the exception.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    await db.flush()

    all_verdicts = [r.verdict.verdict for r in submission.receipts if r.verdict]
    submission.status = _rollup_status(all_verdicts)
    await db.flush()
    await db.refresh(submission)

    verdict_views = [
        serialize_verdict(r.verdict, r.category)
        for r in sorted(submission.receipts, key=lambda r: r.created_at)
        if r.verdict
    ]

    return ReviewResponse(
        submission_id=submission.id,
        status=submission.status,
        reviewed=reviewed,
        verdicts=verdict_views,
    )
