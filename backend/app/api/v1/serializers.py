"""Helpers that assemble ORM rows into the nested API response schemas."""

from __future__ import annotations

from app.models.receipt import Receipt
from app.models.submission import Submission
from app.models.verdict import Verdict
from app.schemas.submission import ReceiptWithVerdictRead, SubmissionDetailRead
from app.schemas.verdict import OverrideRead, VerdictWithOverridesRead


def serialize_verdict(verdict: Verdict, category: str | None) -> VerdictWithOverridesRead:
    """Build a verdict view with its override audit trail and effective decision.

    The original AI verdict is never mutated; "latest override wins" is computed
    here by taking the most recent override row (if any).
    """
    overrides = sorted(verdict.overrides, key=lambda o: o.created_at)
    effective = overrides[-1].override_verdict if overrides else verdict.verdict
    return VerdictWithOverridesRead(
        id=verdict.id,
        receipt_id=verdict.receipt_id,
        verdict=verdict.verdict,
        reasoning=verdict.reasoning,
        confidence=verdict.confidence,
        policy_citations=verdict.policy_citations,
        quoted_policy_clauses=verdict.quoted_policy_clauses,
        created_at=verdict.created_at,
        category=category,
        overrides=[OverrideRead.model_validate(o) for o in overrides],
        effective_verdict=effective,
    )


def serialize_receipt(receipt: Receipt) -> ReceiptWithVerdictRead:
    verdict_view = (
        serialize_verdict(receipt.verdict, receipt.category) if receipt.verdict else None
    )
    return ReceiptWithVerdictRead(
        id=receipt.id,
        submission_id=receipt.submission_id,
        original_filename=receipt.original_filename,
        file_path=receipt.file_path,
        merchant=receipt.merchant,
        transaction_date=receipt.transaction_date,
        amount=receipt.amount,
        currency=receipt.currency,
        category=receipt.category,
        created_at=receipt.created_at,
        raw_extracted_text=receipt.raw_extracted_text,
        verdict=verdict_view,
    )


def serialize_submission_detail(submission: Submission) -> SubmissionDetailRead:
    receipts = sorted(submission.receipts, key=lambda r: r.created_at)
    employee = getattr(submission, "employee", None)
    return SubmissionDetailRead(
        id=submission.id,
        employee_id=submission.employee_id,
        folder_name=submission.folder_name,
        trip_purpose=submission.trip_purpose,
        trip_start_date=submission.trip_start_date,
        trip_end_date=submission.trip_end_date,
        status=submission.status,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
        employee=employee,
        receipts=[serialize_receipt(r) for r in receipts],
    )
