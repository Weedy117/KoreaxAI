from __future__ import annotations

import pandas as pd
import streamlit as st

from .charts import bar_latest, line_by_country
from .data_io import load_gold_table, read_collection_status, read_manual_review


def load_dashboard_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    observations = load_gold_table("observations")
    indicators = load_gold_table("indicators")
    sources = load_gold_table("sources")
    return observations, indicators, sources


def page_setup(title: str) -> None:
    st.set_page_config(page_title=title, layout="wide")
    st.title(title)
    st.caption("Dashboard reads only from data/gold. Empty charts mean no verified collected value is available yet.")


def metric_strip(observations: pd.DataFrame, indicators: pd.DataFrame) -> None:
    total_obs = len(observations)
    collected_indicators = observations["indicator_id"].nunique() if not observations.empty else 0
    total_indicators = len(indicators)
    latest_year = ""
    if not observations.empty:
        years = pd.to_numeric(observations["year"], errors="coerce").dropna()
        latest_year = str(int(years.max())) if not years.empty else "n/a"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Collected observations", total_obs)
    c2.metric("Indicators with data", f"{collected_indicators}/{total_indicators}")
    c3.metric("Latest year", latest_year or "n/a")
    c4.metric("Manual review items", len(read_manual_review()))


def show_indicator_chart(observations: pd.DataFrame, indicators: pd.DataFrame, indicator_id: str, chart: str = "bar") -> None:
    meta = indicators[indicators["indicator_id"] == indicator_id]
    title = indicator_id if meta.empty else str(meta.iloc[0]["indicator_name"])
    fig = line_by_country(observations, indicator_id, title) if chart == "line" else bar_latest(observations, indicator_id, title)
    if fig.data:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"No verified collected value yet for `{indicator_id}`.")


def observations_table(observations: pd.DataFrame, category: str | None = None) -> None:
    df = observations
    if category and not observations.empty:
        df = observations[observations["category"].isin(category.split("|"))]
    st.dataframe(df, use_container_width=True, hide_index=True)


def collection_summary() -> None:
    status = read_collection_status()
    manual = read_manual_review()
    st.subheader("Collection Status")
    st.dataframe(status, use_container_width=True, hide_index=True)
    st.subheader("Manual Review Queue")
    st.dataframe(manual, use_container_width=True, hide_index=True)
