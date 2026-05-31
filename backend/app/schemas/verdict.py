import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# Compliance vocabulary used by the AI reviewer and the API (see migration 004).
VERDICT_VALUES = r"^(compliant|flagged|rejected|needs_review)$"


class PolicyCitation(BaseModel):
    """A pointer to a specific retrieved policy chunk that informed the verdict."""

    document_id: str
    page_number: int | None = None
    section: str | None = None
    reason: str | None = None


class QuotedClause(BaseModel):
    """An exact excerpt copied from a retrieved policy chunk (no paraphrasing)."""

    document_id: str
    quote: str


class VerdictCreate(BaseModel):
    receipt_id: uuid.UUID
    verdict: str = Field(..., pattern=VERDICT_VALUES)
    reasoning: str
    confidence: Decimal = Field(..., ge=0, le=1)
    policy_citations: list[PolicyCitation] = []
    quoted_policy_clauses: list[QuotedClause] = []


class VerdictRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    receipt_id: uuid.UUID
    verdict: str
    reasoning: str
    confidence: Decimal
    policy_citations: list
    quoted_policy_clauses: list
    created_at: datetime
    # category is stored on the receipt, not the verdict row; the routes fill it
    # in from the associated receipt so a verdict response is self-contained.
    category: str | None = None


class OverrideCreate(BaseModel):
    override_verdict: str = Field(..., pattern=VERDICT_VALUES)
    reviewer_name: str = Field(..., min_length=1)
    comment: str | None = None


class OverrideRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    verdict_id: uuid.UUID
    override_verdict: str
    reviewer_name: str
    comment: str | None
    created_at: datetime


class VerdictWithOverridesRead(VerdictRead):
    """A verdict plus its human-override audit trail and effective decision."""

    overrides: list[OverrideRead] = []
    # The decision that currently stands: the latest override if any, else the AI
    # verdict. "Latest override wins" without ever mutating the original verdict.
    effective_verdict: str
