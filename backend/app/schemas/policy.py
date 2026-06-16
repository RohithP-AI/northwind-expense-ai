import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PolicyDocumentCreate(BaseModel):
    document_id: str
    filename: str
    title: str


class PolicyDocumentRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    document_id: str
    filename: str
    title: str
    created_at: datetime


class PolicyChunkCreate(BaseModel):
    document_id: str
    section: str | None = None
    page_number: int | None = None
    chunk_text: str
    embedding: list[float] | None = None
    metadata: dict = {}


class PolicyChunkRead(BaseModel):
    # populate_by_name lets the JSON key stay "metadata" while reading the ORM
    # attribute "meta" (renamed to avoid SQLAlchemy's reserved name).
    model_config = {"from_attributes": True, "populate_by_name": True}

    id: uuid.UUID
    document_id: str
    section: str | None
    page_number: int | None
    chunk_text: str
    metadata: dict = Field(validation_alias="meta", serialization_alias="metadata")
    created_at: datetime
    # embedding intentionally omitted from API responses (large, not needed by clients)


# ── Retrieval (POST /policy/search) ──────────────────────────────────────────
class PolicySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language policy question")
    top_k: int = Field(5, ge=1, le=20, description="Number of chunks to return")


class PolicySearchResult(BaseModel):
    document_id: str
    page_number: int | None
    section: str | None
    chunk_text: str
    similarity: float
    confidence: str  # high | medium | low


class PolicySearchResponse(BaseModel):
    query: str
    confidence: str  # overall, derived from the best-matching chunk
    results: list[PolicySearchResult]


# ── Answer (POST /policy/answer) ──────────────────────────────────────────────
# The assistant-style endpoint: a single natural-language answer plus a grounded
# confidence level. Raw retrieval details stay server-side and are intentionally
# absent from the public response.
MAX_QUESTION_LENGTH = 500

Confidence = Literal["high", "medium", "low"]


class PolicyAnswerRequest(BaseModel):
    question: str = Field(
        ...,
        description="Natural-language policy question.",
    )

    @field_validator("question")
    @classmethod
    def _clean_question(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("Question must not be empty.")
        if len(cleaned) > MAX_QUESTION_LENGTH:
            raise ValueError(
                f"Question is too long (max {MAX_QUESTION_LENGTH} characters)."
            )
        return cleaned


class PolicyAnswerResponse(BaseModel):
    # Deliberately small: one human-readable answer and a coarse confidence.
    # References/citations can be added later (the service already retains the
    # source chunks internally) without changing this contract.
    answer: str
    confidence: Confidence
