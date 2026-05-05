"""Parallel retrieval coordinator with deduplication and dataframe output."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from loguru import logger

from retrieval.base import BaseRetriever, CatalystRecord


class CatalystAggregator:
    """Run multiple retrievers in parallel and aggregate normalized output."""

    def __init__(self, retrievers: list[BaseRetriever]) -> None:
        """Initialize aggregator with retriever instances.

        Args:
            retrievers: List of source retriever objects.

        Returns:
            None.

        Raises:
            None.
        """
        self.retrievers = retrievers

    def retrieve(self, reaction: str, timeout: int = 30) -> pd.DataFrame:
        """Execute parallel source retrieval, deduplicate, and sort records.

        Args:
            reaction: User reaction string.
            timeout: Maximum wait time in seconds for all retrievers.

        Returns:
            DataFrame of deduplicated candidate records sorted by activity.

        Raises:
            None.
        """
        all_records: list[CatalystRecord] = []

        with ThreadPoolExecutor(max_workers=max(1, len(self.retrievers))) as executor:
            future_map = {executor.submit(retriever.search, reaction): retriever.source_name for retriever in self.retrievers}
            for future in as_completed(future_map, timeout=timeout):
                source = future_map[future]
                try:
                    records = future.result()
                    all_records.extend(records)
                    logger.info("Retriever '{}' completed with {} records.", source, len(records))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Retriever '{}' failed and was skipped: {}", source, exc)

        if not all_records:
            return pd.DataFrame(
                columns=[
                    "source",
                    "source_id",
                    "name",
                    "formula",
                    "reaction",
                    "activity_metric",
                    "activity_value",
                    "activity_unit",
                    "conditions",
                    "stability",
                    "raw",
                ]
            )

        deduped: dict[tuple[str, str, str], CatalystRecord] = {}
        for record in all_records:
            key = (record.formula.strip().lower(), record.reaction.strip().lower(), record.source.strip().lower())
            deduped[key] = record

        frame = pd.DataFrame([record.model_dump() for record in deduped.values()])
        if "activity_value" in frame.columns:
            frame["activity_value"] = pd.to_numeric(frame["activity_value"], errors="coerce")
            frame = frame.sort_values(by="activity_value", ascending=True, na_position="last")
        frame = frame.reset_index(drop=True)
        return frame
