"""Streamlit search sidebar for reaction input, sources, filters, and health status."""

from __future__ import annotations

from typing import Any

import streamlit as st

from retrieval.base import BaseRetriever

PRESET_FILTERS: dict[str, tuple[tuple[int, int], tuple[float, float]]] = {
    "Recommended (Balanced)": ((280, 900), (4.0, 10.0)),
    "Low Temperature": ((220, 500), (5.0, 9.0)),
    "High Temperature": ((600, 1300), (3.0, 11.0)),
    "Near Neutral pH": ((280, 850), (6.0, 8.0)),
    "Broad Screen": ((200, 1500), (0.0, 14.0)),
}


def render_search_sidebar(retrievers: dict[str, BaseRetriever]) -> tuple[str, list[str], dict[str, Any], bool]:
    """Render sidebar controls and return user search selections.

    Args:
        retrievers: Mapping from source label to retriever instance.

    Returns:
        Tuple of reaction string, selected source labels, filter dict, and run trigger flag.

    Raises:
        None.
    """
    st.sidebar.header("CatalystIQ Search")
    reaction = st.sidebar.text_input(
        "Target Reaction",
        placeholder="CO2 + H2 → methanol",
    )

    source_names = list(retrievers.keys())
    selected_sources = st.sidebar.multiselect(
        "Data Sources",
        options=source_names,
        default=source_names,
    )

    selected_preset = st.sidebar.selectbox("Filter Preset", options=list(PRESET_FILTERS.keys()), index=0)
    default_temp, default_ph = PRESET_FILTERS[selected_preset]

    with st.sidebar.expander("Advanced Filters", expanded=False):
        temperature_range = st.slider("Temperature Range (K)", min_value=200, max_value=1500, value=default_temp)
        ph_range = st.slider("pH Range", min_value=0.0, max_value=14.0, value=default_ph, step=0.1)
        st.caption("Tip: Keep Broad Screen while validating setup to avoid over-filtering.")
        allow_demo_fallback = st.checkbox("Allow demo fallback (disabled in live mode)", value=False, help="Currently overridden to OFF for hackathon live runs.")

    st.sidebar.markdown("**Quick reaction examples**")
    st.sidebar.caption("Fe + O2 -> Fe2O3 | CO2 + H2 -> methanol | glucose + ATP -> glucose-6-phosphate + ADP")
    st.sidebar.caption("Enable demo fallback only when live sources are unavailable.")

    st.sidebar.subheader("Source Health")
    for source_name, retriever in retrievers.items():
        healthy = retriever.health_check()
        status = "✅" if healthy else "❌"
        st.sidebar.write(f"{status} {source_name}")

    run_clicked = st.sidebar.button("🔍 Retrieve Candidates", type="primary", use_container_width=True)
    filters: dict[str, Any] = {
        "preset": selected_preset,
        "temperature_range": temperature_range,
        "ph_range": ph_range,
        "allow_demo_fallback": allow_demo_fallback,
    }

    return reaction, selected_sources, filters, run_clicked
