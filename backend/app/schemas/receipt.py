import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ReceiptCreate(BaseModel):
    submission_id: uuid.UUID
    original_filename: str
    file_path: str
    merchant: str | None = None
    transaction_date: date | None = None
    amount: Decimal | None = Field(None, gt=0)
    currency: str = Field("USD", pattern=r"^[A-Z]{3}$")
    category: str | None = Field(
        None,
        pattern=r"^(flight|hotel|transport|meal|registration|other)$",
    )
    raw_extracted_text: str | None = None


class ReceiptUpdate(BaseModel):
    merchant: str | None = None
    transaction_date: date | None = None
    amount: Decimal | None = Field(None, gt=0)
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    category: str | None = Field(
        None,
        pattern=r"^(flight|hotel|transport|meal|registration|other)$",
    )
    raw_extracted_text: str | None = None


class ReceiptRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    submission_id: uuid.UUID
    original_filename: str
    file_path: str
    merchant: str | None
    transaction_date: date | None
    amount: Decimal | None
    currency: str
    category: str | None
    created_at: datetime


class ReceiptUploadResponse(BaseModel):
    """Result of uploading one or more receipt files to a submission."""

    submission_id: uuid.UUID
    receipts: list[ReceiptRead]
    # Non-fatal notes, e.g. an image uploaded without ANTHROPIC_API_KEY so its
    # fields could not be extracted. The file is still saved and recorded.
    warnings: list[str] = []
