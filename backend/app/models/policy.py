import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

EMBEDDING_DIM = 1536  # text-embedding-3-small


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )  # e.g. "policy1"
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "policy1.pdf"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    chunks: Mapped[list["PolicyChunk"]] = relationship(back_populates="document")


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("policy_documents.document_id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section: Mapped[str | None] = mapped_column(String(255))
    page_number: Mapped[int | None] = mapped_column(SmallInteger)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(Vector(EMBEDDING_DIM))
    # DB column stays "metadata" (migration + ingest script depend on it), but the
    # Python attribute must be renamed: "metadata" is reserved by SQLAlchemy's
    # Declarative API.
    meta: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="'{}'"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    document: Mapped["PolicyDocument"] = relationship(back_populates="chunks")
