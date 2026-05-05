"""Streamlit results renderer with candidates table, chart comparison, and provenance."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st


def render_results(df: pd.DataFrame) -> None:
    """Render retrieval results across candidate, comparison, and provenance tabs.

    Args:
        df: Candidate dataframe produced by aggregator.

    Returns:
        None.

    Raises:
        None.
    """
    if df.empty:
        st.info("No candidates found for the current query.")
        return

    tab_candidates, tab_comparison, tab_provenance = st.tabs(["Candidates", "Comparison", "Provenance"])

    with tab_candidates:
        display_df = df.copy()
        display_df["source_badge"] = display_df["source"].astype(str).map(lambda s: f"[{s}]")
        ordered_columns = [
            "source_badge",
            "source_id",
            "name",
            "formula",
            "reaction",
            "activity_metric",
            "activity_value",
            "activity_unit",
            "stability",
            "data_quality",
        ]
        columns = [col for col in ordered_columns if col in display_df.columns]
        st.dataframe(display_df[columns], use_container_width=True, hide_index=True)

    with tab_comparison:
        chart_df = df.copy()
        chart_df["formula"] = chart_df["formula"].replace("", "N/A")
        fig = px.bar(
            chart_df,
            x="formula",
            y="activity_value",
            color="source",
            hover_data=["activity_metric", "activity_unit", "source_id"],
            title="Activity Comparison by Formula and Source",
        )
        fig.update_layout(xaxis_title="Formula", yaxis_title="Activity Value")
        st.plotly_chart(fig, use_container_width=True)

    with tab_provenance:
        provenance = df[["source", "source_id", "raw"]].to_dict(orient="records") if "raw" in df.columns else []
        st.json(provenance, expanded=False)
