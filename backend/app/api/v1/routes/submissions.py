import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.serializers import serialize_submission_detail
from app.core.database import get_db
from app.models.employee import Employee
from app.models.receipt import Receipt
from app.models.submission import Submission
from app.models.verdict import Verdict
from app.schemas.submission import (
    SubmissionCreate,
    SubmissionDetailRead,
    SubmissionRead,
)

router = APIRouter()


@router.post("/", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new expense submission for an employee."""
    employee = await db.scalar(
        select(Employee).where(Employee.employee_id == payload.employee_id)
    )
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee {payload.employee_id} not found",
        )

    folder_name = payload.folder_name or (
        f"{payload.employee_id}_{payload.trip_start_date.isoformat()}"
    )
    submission = Submission(
        employee_id=payload.employee_id,
        folder_name=folder_name,
        trip_purpose=payload.trip_purpose,
        trip_start_date=payload.trip_start_date,
        trip_end_date=payload.trip_end_date,
        status="pending",
    )
    db.add(submission)
    await db.flush()
    await db.refresh(submission)
    return submission


@router.get("/", response_model=list[SubmissionRead])
async def list_submissions(
    employee_id: str | None = Query(None, description="Filter by employee business key"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    date_from: date | None = Query(None, description="trip_start_date on or after this date"),
    date_to: date | None = Query(None, description="trip_start_date on or before this date"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List submissions, newest trip first, with optional filters."""
    stmt = select(Submission).order_by(Submission.trip_start_date.desc())
    if employee_id:
        stmt = stmt.where(Submission.employee_id == employee_id)
    if status_filter:
        stmt = stmt.where(Submission.status == status_filter)
    if date_from:
        stmt = stmt.where(Submission.trip_start_date >= date_from)
    if date_to:
        stmt = stmt.where(Submission.trip_start_date <= date_to)
    stmt = stmt.offset(skip).limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{submission_id}", response_model=SubmissionDetailRead)
async def get_submission(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return one submission with its employee, receipts, verdicts and overrides."""
    stmt = (
        select(Submission)
        .where(Submission.id == submission_id)
        .options(
            selectinload(Submission.employee),
            selectinload(Submission.receipts)
            .selectinload(Receipt.verdict)
            .selectinload(Verdict.overrides),
        )
    )
    submission = await db.scalar(stmt)
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    return serialize_submission_detail(submission)
