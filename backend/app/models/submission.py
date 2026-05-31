import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    employee_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("employees.employee_id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    folder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trip_purpose: Mapped[str] = mapped_column(Text, nullable=False)
    trip_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    trip_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow
    )

    employee: Mapped["Employee"] = relationship(back_populates="submissions")  # noqa: F821
    receipts: Mapped[list["Receipt"]] = relationship(back_populates="submission")  # noqa: F821
