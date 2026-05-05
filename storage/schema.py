"""SQLAlchemy ORM schema for query provenance and candidate records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    """Return UTC timestamp for default column values.

    Args:
        None.

    Returns:
        Current UTC datetime.

    Raises:
        None.
    """
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class for CatalystIQ models."""


class QueryEvent(Base):
    """Persist a single user query event and result metadata."""

    __tablename__ = "query_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reaction: Mapped[str] = mapped_column(String(512), nullable=False)
    sources_queried: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    candidates: Mapped[list["CandidateRecord"]] = relationship(
        back_populates="query_event",
        cascade="all, delete-orphan",
    )


class CandidateRecord(Base):
    """Persist normalized candidate details and raw payload provenance."""

    __tablename__ = "candidate_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_event_id: Mapped[int] = mapped_column(ForeignKey("query_events.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    formula: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    activity_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    activity_unit: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    query_event: Mapped[QueryEvent] = relationship(back_populates="candidates")
