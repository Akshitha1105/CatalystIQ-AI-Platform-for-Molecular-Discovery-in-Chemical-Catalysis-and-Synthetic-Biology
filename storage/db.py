"""Database engine, session management, and CRUD helpers for CatalystIQ."""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from config import DATABASE_URL
from retrieval.demo_data import build_demo_candidates
from storage.schema import Base, CandidateRecord, QueryEvent

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, future=True)


def init_db() -> None:
    """Create all database tables.

    Args:
        None.

    Returns:
        None.

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If schema creation fails.
    """
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized at {}", DATABASE_URL)


def save_query_event(reaction: str, sources: list[str], count: int) -> QueryEvent:
    """Persist a query event with source metadata and result count.

    Args:
        reaction: Reaction query string.
        sources: List of source names queried.
        count: Number of records returned.

    Returns:
        Persisted QueryEvent instance with primary key.

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If transaction fails.
    """
    with SessionLocal() as session:
        event = QueryEvent(reaction=reaction, sources_queried=sources, result_count=count)
        session.add(event)
        session.commit()
        session.refresh(event)
        return event


def save_candidates(query_event_id: int, df: pd.DataFrame) -> int:
    """Persist candidate rows for a query event.

    Args:
        query_event_id: Foreign-key ID from QueryEvent.
        df: DataFrame with candidate fields.

    Returns:
        Number of records successfully saved.

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If insert transaction fails.
    """
    if df.empty:
        return 0

    records: list[CandidateRecord] = []
    for row in df.to_dict(orient="records"):
        conditions: dict[str, Any] = row.get("conditions") or {}
        raw_payload: dict[str, Any] = row.get("raw") or {}
        activity_value = row.get("activity_value")
        numeric_activity = float(activity_value) if activity_value is not None else None

        record = CandidateRecord(
            query_event_id=query_event_id,
            source=str(row.get("source", "")),
            source_id=str(row.get("source_id", "")),
            formula=str(row.get("formula", "")),
            activity_value=numeric_activity,
            activity_unit=str(row.get("activity_unit", "")),
            conditions=conditions if isinstance(conditions, dict) else {"value": conditions},
            raw_payload=raw_payload if isinstance(raw_payload, dict) else {"value": raw_payload},
        )
        records.append(record)

    with SessionLocal() as session:
        session.add_all(records)
        session.commit()
        logger.info("Saved {} candidate records for query_event_id={}", len(records), query_event_id)
        return len(records)


def seed_demo_database(minimum_records: int = 90) -> int:
    """Ensure baseline demo candidate records exist for offline testing.

    Args:
        minimum_records: Minimum candidate record count to keep in DB.

    Returns:
        Number of inserted demo candidate records.

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If insert transaction fails.
    """
    with SessionLocal() as session:
        current_count = session.execute(select(func.count(CandidateRecord.id))).scalar_one()
        if int(current_count) >= minimum_records:
            return 0

    demo_df = build_demo_candidates(limit=minimum_records)
    seed_event = save_query_event(
        reaction="demo_seed_catalog",
        sources=["Materials Project", "BRENDA", "Open Catalyst"],
        count=len(demo_df),
    )
    inserted = save_candidates(query_event_id=seed_event.id, df=demo_df)
    logger.info("Seeded {} demo records for offline test coverage.", inserted)
    return inserted
