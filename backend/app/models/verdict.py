import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Verdict(Base):
    __tablename__ = "verdicts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    verdict: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    policy_citations: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="'[]'")
    quoted_policy_clauses: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="'[]'"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    receipt: Mapped["Receipt"] = relationship(back_populates="verdict")  # noqa: F821
    overrides: Mapped[list["Override"]] = relationship(back_populates="verdict")  # noqa: F821


class Override(Base):
    __tablename__ = "overrides"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    verdict_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verdicts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    override_verdict: Mapped[str] = mapped_column(String(30), nullable=False)
    reviewer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    verdict: Mapped["Verdict"] = relationship(back_populates="overrides")
