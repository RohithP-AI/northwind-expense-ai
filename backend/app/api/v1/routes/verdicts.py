import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.serializers import serialize_verdict
from app.core.database import get_db
from app.models.verdict import Override, Verdict
from app.schemas.verdict import OverrideCreate, VerdictWithOverridesRead

router = APIRouter()


@router.get("/receipts/{receipt_id}/verdict", response_model=VerdictWithOverridesRead)
async def get_receipt_verdict(
    receipt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Fetch the AI verdict (with any human overrides) for a receipt."""
    verdict = await db.scalar(
        select(Verdict)
        .where(Verdict.receipt_id == receipt_id)
        .options(selectinload(Verdict.overrides), selectinload(Verdict.receipt))
    )
    if verdict is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No verdict found for this receipt (has it been reviewed?).",
        )
    category = verdict.receipt.category if verdict.receipt else None
    return serialize_verdict(verdict, category)


@router.post("/verdicts/{verdict_id}/override", response_model=VerdictWithOverridesRead)
async def override_verdict(
    verdict_id: uuid.UUID,
    payload: OverrideCreate,
    db: AsyncSession = Depends(get_db),
):
    """Record a human override of an AI verdict.

    The original verdict row is never mutated — each override is appended to the
    overrides audit log, and the latest one becomes the effective decision.
    """
    verdict = await db.scalar(
        select(Verdict)
        .where(Verdict.id == verdict_id)
        .options(selectinload(Verdict.overrides), selectinload(Verdict.receipt))
    )
    if verdict is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verdict not found")

    override = Override(
        verdict_id=verdict.id,
        override_verdict=payload.override_verdict,
        reviewer_name=payload.reviewer_name,
        comment=payload.comment,
    )
    db.add(override)
    await db.flush()
    await db.refresh(override)
    verdict.overrides.append(override)

    category = verdict.receipt.category if verdict.receipt else None
    return serialize_verdict(verdict, category)
