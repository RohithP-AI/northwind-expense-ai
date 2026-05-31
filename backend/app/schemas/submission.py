import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.employee import EmployeeRead
from app.schemas.receipt import ReceiptRead
from app.schemas.verdict import VerdictWithOverridesRead

SUBMISSION_STATUS_VALUES = (
    r"^(pending|under_review|compliant|flagged|rejected|needs_review)$"
)


class SubmissionCreate(BaseModel):
    employee_id: str = Field(..., pattern=r"^NW-\d{5}$")
    trip_purpose: str = Field(..., min_length=1)
    trip_start_date: date
    trip_end_date: date
    # Optional: defaults to a generated label if the caller doesn't supply one
    # (the /submissions folder name is only meaningful for the seeded samples).
    folder_name: str | None = None

    @model_validator(mode="after")
    def end_after_start(self) -> "SubmissionCreate":
        if self.trip_end_date < self.trip_start_date:
            raise ValueError("trip_end_date must be on or after trip_start_date")
        return self


class SubmissionUpdate(BaseModel):
    status: str | None = Field(None, pattern=SUBMISSION_STATUS_VALUES)


class SubmissionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    employee_id: str
    folder_name: str
    trip_purpose: str
    trip_start_date: date
    trip_end_date: date
    status: str
    created_at: datetime
    updated_at: datetime


class ReceiptWithVerdictRead(ReceiptRead):
    """A receipt together with its AI verdict (and override trail), if reviewed."""

    raw_extracted_text: str | None = None
    verdict: VerdictWithOverridesRead | None = None


class SubmissionDetailRead(SubmissionRead):
    """Full submission view: employee context plus receipts, verdicts, overrides."""

    employee: EmployeeRead | None = None
    receipts: list[ReceiptWithVerdictRead] = []
