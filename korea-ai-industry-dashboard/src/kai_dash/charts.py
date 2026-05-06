from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def latest_by_indicator(observations: pd.DataFrame) -> pd.DataFrame:
    if observations.empty:
        return observations
    df = observations.copy()
    df["year_num"] = pd.to_numeric(df["year"], errors="coerce")
    value_col = "value_standardized" if "value_standardized" in df.columns else "value"
    df["value_num"] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.sort_values(["indicator_id", "country_iso3", "year_num"], na_position="first")
    return df.groupby(["indicator_id", "country_iso3"], as_index=False).tail(1)


def bar_latest(observations: pd.DataFrame, indicator_id: str, title: str | None = None) -> go.Figure:
    df = latest_by_indicator(observations[observations["indicator_id"] == indicator_id])
    if df.empty:
        return go.Figure()
    hover_cols = [c for c in ["year", "unit_standardized", "unit", "source_id", "notes"] if c in df.columns]
    fig = px.bar(
        df,
        x="country_name",
        y="value_num",
        color="country_iso3",
        hover_data=hover_cols,
        title=title or indicator_id,
        text_auto=".3s",
    )
    fig.update_layout(showlegend=False, margin=dict(l=20, r=20, t=60, b=30))
    return fig


def line_by_country(observations: pd.DataFrame, indicator_id: str, title: str | None = None) -> go.Figure:
    df = observations[observations["indicator_id"] == indicator_id].copy()
    if df.empty:
        return go.Figure()
    df["year_num"] = pd.to_numeric(df["year"], errors="coerce")
    value_col = "value_standardized" if "value_standardized" in df.columns else "value"
    df["value_num"] = pd.to_numeric(df[value_col], errors="coerce")
    hover_cols = [c for c in ["unit_standardized", "unit", "source_id", "notes"] if c in df.columns]
    fig = px.line(
        df.sort_values("year_num"),
        x="year_num",
        y="value_num",
        color="country_name",
        markers=True,
        hover_data=hover_cols,
        title=title or indicator_id,
    )
    fig.update_layout(margin=dict(l=20, r=20, t=60, b=30), xaxis_title="Year")
    return fig
