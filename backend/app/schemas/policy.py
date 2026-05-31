import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
