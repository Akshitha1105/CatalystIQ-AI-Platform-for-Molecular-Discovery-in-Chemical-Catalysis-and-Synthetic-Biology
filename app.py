"""CatalystIQ Streamlit entrypoint orchestrating retrieval, normalization, and persistence."""

from __future__ import annotations

from collections import Counter
import sys

import pandas as pd
import streamlit as st
from loguru import logger

from config import CACHE_DB_PATH, LOG_LEVEL
from processing.cache import QueryCache
from processing.normalizer import flag_missing, normalize_units
from retrieval.aggregator import CatalystAggregator
from retrieval.base import BaseRetriever
from retrieval.brenda import BrendaRetriever
from retrieval.demo_data import demo_candidates_for_query
from retrieval.materials_project import MaterialsProjectRetriever
from retrieval.open_catalyst import OpenCatalystRetriever
from storage.db import init_db, save_candidates, save_query_event, seed_demo_database
from ui.results_page import render_results
from ui.search_page import render_search_sidebar

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)

st.set_page_config(page_title="CatalystIQ", layout="wide")


@st.cache_resource(show_spinner=False)
def get_retrievers() -> dict[str, BaseRetriever]:
    """Build retriever registry used by sidebar source selection.

    Args:
        None.

    Returns:
        Mapping from source label to retriever object.

    Raises:
        None.
    """
    cache = QueryCache(CACHE_DB_PATH)
    return {
        "Materials Project": MaterialsProjectRetriever(),
        "BRENDA": BrendaRetriever(cache=cache),
        "Open Catalyst": OpenCatalystRetriever(),
    }


@st.cache_resource(show_spinner=False)
def get_aggregator() -> CatalystAggregator:
    """Create cached aggregator instance using all retrievers.

    Args:
        None.

    Returns:
        CatalystAggregator instance.

    Raises:
        None.
    """
    retriever_map = get_retrievers()
    return CatalystAggregator(list(retriever_map.values()))


def run_retrieval(reaction: str, selected_sources: tuple[str, ...]) -> pd.DataFrame:
    """Run cached retrieval query for selected sources.

    Args:
        reaction: Reaction text query.
        selected_sources: Tuple of source labels selected by user.

    Returns:
        Retrieved candidate dataframe.

    Raises:
        None.
    """
    retrievers = get_retrievers()
    chosen = [retrievers[name] for name in selected_sources if name in retrievers]
    aggregator = CatalystAggregator(chosen)
    return aggregator.retrieve(reaction)


def _source_breakdown(df: pd.DataFrame) -> str:
    """Build readable source counts string.

    Args:
        df: Retrieved candidate dataframe.

    Returns:
        Human-readable source breakdown.

    Raises:
        None.
    """
    if df.empty or "source" not in df.columns:
        return "No sources returned records."
    counts = Counter(df["source"].astype(str).tolist())
    return ", ".join(f"{source}: {count}" for source, count in counts.items())


def _fallback_demo_results(
    reaction: str,
    selected_sources: list[str],
    filters: dict[str, object],
) -> pd.DataFrame:
    """Generate demo fallback results when live retrieval returns empty data.

    Args:
        reaction: User reaction string.
        selected_sources: Source names chosen in the sidebar.
        filters: Sidebar filter dictionary.

    Returns:
        Dataframe populated from local demo catalog.

    Raises:
        None.
    """
    temperature_range = filters.get("temperature_range", (200, 1500))
    ph_range = filters.get("ph_range", (0.0, 14.0))
    temp_bounds = (int(temperature_range[0]), int(temperature_range[1])) if isinstance(temperature_range, tuple) else (200, 1500)
    ph_bounds = (float(ph_range[0]), float(ph_range[1])) if isinstance(ph_range, tuple) else (0.0, 14.0)
    return demo_candidates_for_query(
        reaction=reaction,
        selected_sources=selected_sources,
        temperature_range=temp_bounds,
        ph_range=ph_bounds,
        limit=60,
    )


def main() -> None:
    """Run Streamlit app lifecycle and user interaction flow.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    st.title("CatalystIQ")
    st.caption("Catalyst and enzyme discovery workflow with provenance tracking.")

    init_db()
    seeded = seed_demo_database(minimum_records=120)
    if seeded > 0:
        st.info(f"Initialized local demo catalog with {seeded} records for offline testing.")
    retrievers = get_retrievers()
    reaction, selected_sources, filters, run_clicked = render_search_sidebar(retrievers)

    if not run_clicked:
        st.info("Set your query and click 'Retrieve Candidates' to begin.")
        return

    if not reaction.strip():
        st.warning("Please enter a target reaction.")
        return

    if not selected_sources:
        st.warning("Please select at least one data source.")
        return

    with st.spinner("Retrieving candidates from selected sources..."):
        df = run_retrieval(reaction=reaction.strip(), selected_sources=tuple(selected_sources))

    allow_demo_fallback = False
    if df.empty and allow_demo_fallback:
        df = _fallback_demo_results(reaction=reaction.strip(), selected_sources=selected_sources, filters=filters)
        st.warning("Live sources returned no records, so demo fallback candidates are shown.")
    elif df.empty:
        st.error("No live records returned from selected sources.")
        st.info("For hackathon live mode: keep Open Catalyst selected and query like 'N2 + H2 -> NH3' or 'CO + H2 -> methane'.")

    df = normalize_units(df)
    df = flag_missing(df)

    event = save_query_event(reaction=reaction.strip(), sources=selected_sources, count=len(df))
    saved_rows = save_candidates(query_event_id=event.id, df=df)

    st.success(f"Retrieved {len(df)} candidates. Source breakdown: {_source_breakdown(df)}")
    st.caption(f"Saved {saved_rows} records to provenance database.")
    render_results(df)


if __name__ == "__main__":
    main()
