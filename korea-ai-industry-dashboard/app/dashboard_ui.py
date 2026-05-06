from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kai_dash.data_io import load_dashboard_bundle


COUNTRY_COLORS = {
    "KOR": "#D6A84F",
    "USA": "#6CA6D9",
    "CHN": "#C76D5B",
}

COUNTRY_NAMES = {
    "KOR": "South Korea",
    "USA": "United States",
    "CHN": "China",
}

CATEGORY_ORDER = [
    "Compute and Data Centers",
    "Hardware and Semiconductors",
    "Models, Research, and Funding",
    "Adoption and Industry",
    "Talent, Public Sector, and Defense",
    "Social Readiness",
]

MASTER_INDICATORS = {
    "Compute and Data Centers": "top500_total_rmax_pflops",
    "Models, Research, and Funding": "notable_ai_models_count",
    "Adoption and Industry": "robot_density_manufacturing",
    "Talent, Public Sector, and Defense": "ai_index_fig_1_8_1_number_of_top_ai_authors_and_inventors_in_thousands",
    "Social Readiness": "ai_concern_more_than_excited_pct",
}

CURATED_INDICATORS = {
    "Compute and Data Centers": [
        "top500_total_rmax_pflops",
        "top500_system_count",
        "known_ai_gpu_cluster_count",
        "known_ai_gpu_cluster_16bit_ops",
        "public_gpu_procurement_count",
        "kisti6_peak_pflops",
        "announced_gpu_deployments_count",
    ],
    "Models, Research, and Funding": [
        "notable_ai_models_count",
        "frontier_ai_models_count",
        "large_scale_models_count",
        "ai_research_publications_count",
        "ai_patents_per_capita",
        "private_ai_investment_usd",
        "newly_funded_ai_companies_count",
    ],
    "Adoption and Industry": [
        "robot_density_manufacturing",
        "industrial_robot_installations",
        "worker_genai_work_use_pct",
        "worker_genai_any_use_pct",
        "genai_time_saved_pct",
        "genai_productivity_effect_pct",
        "smart_manufacturing_ai_projects_2026",
    ],
    "Talent, Public Sector, and Defense": [
        "ai_index_fig_1_8_1_number_of_top_ai_authors_and_inventors_in_thousands",
        "worker_retraining_intention_pct",
        "defense_unmanned_system_procurement_budget",
        "public_gpu_procurement_budget_krw",
        "ai_index_fig_8_2_1_2025",
        "ai_index_fig_8_3_2_has_nvidia",
        "ai_index_fig_7_3_19_status",
    ],
    "Social Readiness": [
        "ai_concern_more_than_excited_pct",
        "worker_positive_ai_society_pct",
        "ai_index_fig_9_1_10_using_ai_at_work",
        "ai_index_fig_9_1_10_trust_ai_at_work",
        "ai_index_fig_9_3_1_respondents",
    ],
}

NICE_NAMES = {
    "country_name": "Country",
    "country_iso3": "Country",
    "period_label": "Period",
    "display_value": "Value",
    "unit_standardized": "Unit",
    "indicator_type": "Type",
    "confidence_tier": "Confidence",
    "source_name": "Source",
}


@st.cache_data(show_spinner=False)
def load_data() -> dict[str, pd.DataFrame]:
    bundle = load_dashboard_bundle()
    for key in ["canonical", "timeseries"]:
        if not bundle[key].empty:
            bundle[key] = prepare_observations(bundle[key])
    return bundle


def prepare_observations(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["value_plot"] = pd.to_numeric(out.get("value_standardized", out.get("value_numeric", "")), errors="coerce")
    out["year_num"] = pd.to_numeric(out.get("year", ""), errors="coerce")
    out["period_date"] = pd.to_datetime(out.get("period_start", ""), errors="coerce")
    out["Country"] = out["country_iso3"].map(COUNTRY_NAMES).fillna(out.get("country_name", ""))
    out["Period"] = out.get("period_label", "").astype(str).where(out.get("period_label", "").astype(str) != "", out.get("year", ""))
    out["Value"] = out.apply(format_row_value, axis=1)
    out["Source"] = out.get("source_name", "")
    return out


def format_number(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_value >= 10_000:
        return f"{value:,.0f}"
    if abs_value >= 100:
        return f"{value:,.1f}".rstrip("0").rstrip(".")
    if abs_value >= 1:
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def format_row_value(row: pd.Series) -> str:
    value = pd.to_numeric(row.get("value_standardized", row.get("value_numeric", "")), errors="coerce")
    if pd.isna(value):
        return str(row.get("value_raw", ""))
    unit = str(row.get("unit_standardized", "") or row.get("unit", ""))
    if unit == "percent":
        return f"{format_number(value)}%"
    if unit == "USD_billion":
        return f"${format_number(value)}B"
    if unit == "USD":
        return f"${format_number(value)}"
    if unit == "KRW":
        return f"KRW {format_number(value)}"
    if unit == "count":
        return format_number(value)
    return f"{format_number(value)} {unit}".strip()


def latest_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    sorted_df = df.sort_values(["indicator_id", "country_iso3", "period_date", "year_num"], na_position="first")
    return sorted_df.groupby(["indicator_id", "country_iso3"], as_index=False).tail(1)


def category_data(df: pd.DataFrame, category: str) -> pd.DataFrame:
    return df[(df["category"] == category) & (df["country_iso3"].isin(["KOR", "USA", "CHN"]))].copy()


def korea_indicator_ids(df: pd.DataFrame, category: str) -> list[str]:
    ids = df[(df["category"] == category) & (df["country_iso3"] == "KOR")]["indicator_id"].unique().tolist()
    curated = [item for item in CURATED_INDICATORS.get(category, []) if item in ids]
    remainder = [item for item in ids if item not in curated]
    return curated + remainder


def indicator_name(df: pd.DataFrame, indicator_id: str) -> str:
    rows = df[df["indicator_id"] == indicator_id]
    if rows.empty:
        return indicator_id.replace("_", " ").title()
    return str(rows.iloc[0]["indicator_name"])


def chartable_rows(canonical: pd.DataFrame, timeseries: pd.DataFrame, indicator_id: str, countries: list[str], simple: bool) -> tuple[pd.DataFrame, str]:
    ts = timeseries[(timeseries["indicator_id"] == indicator_id) & (timeseries["country_iso3"].isin(countries))].copy()
    ts = ts.dropna(subset=["value_plot"])
    if not simple and ts["year_num"].nunique() >= 2 and "KOR" in set(ts["country_iso3"]):
        return ts.sort_values(["country_iso3", "period_date"]), "line"
    latest = latest_rows(canonical[(canonical["indicator_id"] == indicator_id) & (canonical["country_iso3"].isin(countries))].copy())
    latest = latest.dropna(subset=["value_plot"])
    return latest, "bar"


def useful_chart(df: pd.DataFrame) -> bool:
    if df.empty or "KOR" not in set(df["country_iso3"]):
        return False
    country_count = df["country_iso3"].nunique()
    period_count = df["Period"].nunique()
    return country_count > 1 or period_count > 1


def custom_hover(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["Chart hover"] = (
        "<b>" + out["Country"].astype(str) + "</b><br>"
        + "Period: " + out["Period"].astype(str) + "<br>"
        + "Value: " + out["Value"].astype(str) + "<br>"
        + "Source: " + out["Source"].astype(str)
    )
    return out


def apply_plot_style(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=20, color="#F6EBDD"), x=0.01),
        height=430,
        margin=dict(l=24, r=18, t=70, b=46),
        paper_bgcolor="#15130F",
        plot_bgcolor="#15130F",
        font=dict(family="Georgia, 'Times New Roman', serif", size=14, color="#E9DFD0"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(color="#E9DFD0"),
        ),
        hovermode="closest",
        hoverlabel=dict(
            bgcolor="rgba(18,16,13,0.78)",
            bordercolor="rgba(226,184,107,0.55)",
            font=dict(color="#FFF7EA", size=13, family="Arial"),
        ),
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        title="",
        tickfont=dict(color="#CFC3B2"),
        linecolor="#3A3328",
    )
    fig.update_yaxes(
        gridcolor="rgba(255,255,255,0.08)",
        zerolinecolor="rgba(255,255,255,0.12)",
        title="",
        tickfont=dict(color="#CFC3B2"),
    )
    return fig


def plot_indicator(df: pd.DataFrame, mode: str, title: str, simple: bool) -> go.Figure:
    df = custom_hover(df)
    if mode == "line" and not simple:
        fig = px.line(
            df,
            x="period_date",
            y="value_plot",
            color="country_iso3",
            color_discrete_map=COUNTRY_COLORS,
            markers=True,
            custom_data=["Chart hover"],
        )
        fig.update_traces(hovertemplate="%{customdata[0]}<extra></extra>", line=dict(width=3), marker=dict(size=8))
    else:
        sort_order = {"KOR": 0, "USA": 1, "CHN": 2}
        df = df.assign(country_order=df["country_iso3"].map(sort_order)).sort_values("country_order")
        fig = px.bar(
            df,
            x="Country",
            y="value_plot",
            color="country_iso3",
            color_discrete_map=COUNTRY_COLORS,
            text="Value",
            custom_data=["Chart hover"],
        )
        fig.update_traces(hovertemplate="%{customdata[0]}<extra></extra>", textposition="outside", cliponaxis=False)
    return apply_plot_style(fig, title)


def plot_master_heatmap(canonical: pd.DataFrame, category: str) -> go.Figure | None:
    ids = [
        iid
        for iid in korea_indicator_ids(canonical, category)
        if canonical[(canonical["indicator_id"] == iid) & (canonical["country_iso3"].isin(["USA", "CHN"]))].shape[0] > 0
    ][:6]
    rows = []
    labels = []
    for iid in ids:
        latest = latest_rows(canonical[canonical["indicator_id"] == iid])
        kor = latest[latest["country_iso3"] == "KOR"]
        if kor.empty:
            continue
        kor_value = pd.to_numeric(kor.iloc[0]["value_plot"], errors="coerce")
        if pd.isna(kor_value) or kor_value == 0:
            continue
        vals = []
        for iso in ["KOR", "USA", "CHN"]:
            peer = latest[latest["country_iso3"] == iso]
            if peer.empty:
                vals.append(None)
            else:
                val = pd.to_numeric(peer.iloc[0]["value_plot"], errors="coerce")
                vals.append(None if pd.isna(val) else round((val / kor_value) * 100, 1))
        rows.append(vals)
        labels.append(short_title(indicator_name(canonical, iid)))
    if not rows:
        return None
    fig = go.Figure(
        data=go.Heatmap(
            z=rows,
            x=["South Korea", "United States", "China"],
            y=labels,
            colorscale=[[0, "#211F1B"], [0.5, "#795E2B"], [1, "#D6A84F"]],
            colorbar=dict(
                title=dict(text="Korea=100", font=dict(color="#E9DFD0")),
                tickfont=dict(color="#E9DFD0"),
            ),
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.1f} (Korea=100)<extra></extra>",
        )
    )
    return apply_plot_style(fig, f"{category}: relative position across comparable indicators")


def short_title(text: str, limit: int = 58) -> str:
    text = text.replace(" by country/year", "").replace(" by country", "")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def interpretation(canonical: pd.DataFrame, timeseries: pd.DataFrame, indicator_id: str, countries: list[str]) -> str:
    rows = canonical[(canonical["indicator_id"] == indicator_id) & (canonical["country_iso3"].isin(countries))]
    kor = latest_rows(rows[rows["country_iso3"] == "KOR"])
    if kor.empty:
        return ""
    latest = kor.iloc[0]
    text = f"South Korea’s latest value is {latest['Value']} in {latest['Period']}."
    ts = timeseries[(timeseries["indicator_id"] == indicator_id) & (timeseries["country_iso3"] == "KOR")].dropna(subset=["value_plot"]).sort_values("period_date")
    if len(ts) >= 2:
        first, last = ts.iloc[0], ts.iloc[-1]
        delta = last["value_plot"] - first["value_plot"]
        direction = "rose" if delta > 0 else "fell" if delta < 0 else "was unchanged"
        text += f" Across the available time series, Korea {direction} from {first['Value']} in {first['Period']} to {last['Value']} in {last['Period']}."
    latest_all = latest_rows(rows)
    comparisons = []
    kor_val = pd.to_numeric(latest["value_plot"], errors="coerce")
    if not pd.isna(kor_val) and kor_val != 0:
        for iso in ["USA", "CHN"]:
            peer = latest_all[latest_all["country_iso3"] == iso]
            if peer.empty:
                continue
            pval = pd.to_numeric(peer.iloc[0]["value_plot"], errors="coerce")
            if not pd.isna(pval):
                comparisons.append(f"{COUNTRY_NAMES[iso]} is {pval / kor_val:.1f}x Korea")
    if comparisons:
        text += " In the latest comparable observation, " + "; ".join(comparisons) + "."
    return text


def latest_fact_cards(canonical: pd.DataFrame, category: str, limit: int = 5) -> None:
    rows = latest_rows(canonical[(canonical["category"] == category) & (canonical["country_iso3"] == "KOR")])
    rows = rows.sort_values(["year_num", "indicator_name"], ascending=[False, True]).head(limit)
    if rows.empty:
        return
    cols = st.columns(min(len(rows), 3))
    for idx, (_, row) in enumerate(rows.iterrows()):
        with cols[idx % len(cols)]:
            st.markdown(
                f"""
                <div class="fact-card">
                    <div class="fact-label">{short_title(str(row['indicator_name']), 45)}</div>
                    <div class="fact-value">{row['Value']}</div>
                    <div class="fact-period">{row['Period']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def master_takeaway(canonical: pd.DataFrame, category: str) -> str:
    rows = canonical[(canonical["category"] == category) & (canonical["country_iso3"] == "KOR")]
    comparable = 0
    for iid in rows["indicator_id"].unique():
        c = set(canonical[canonical["indicator_id"] == iid]["country_iso3"])
        if "KOR" in c and ("USA" in c or "CHN" in c):
            comparable += 1
    latest = latest_rows(rows)
    latest_year = int(pd.to_numeric(latest["year"], errors="coerce").max()) if not latest.empty else None
    return f"This section has {rows['indicator_id'].nunique()} Korea indicators, including {comparable} with at least one US or China comparison. The latest Korea observations reach {latest_year} where available."


def jpeg_bytes(df: pd.DataFrame, title: str, simple: bool) -> bytes:
    width, height = 1400, 850
    img = Image.new("RGB", (width, height), "#15130F")
    draw = ImageDraw.Draw(img)
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    title_font = ImageFont.truetype(str(font_path), 34) if font_path.exists() else ImageFont.load_default()
    label_font = ImageFont.truetype(str(font_path), 22) if font_path.exists() else ImageFont.load_default()
    small_font = ImageFont.truetype(str(font_path), 18) if font_path.exists() else ImageFont.load_default()
    draw.text((50, 36), title[:84], fill="#F6EBDD", font=title_font)
    plot = df.dropna(subset=["value_plot"]).copy()
    if plot.empty:
        draw.text((50, 150), "No numeric chart data.", fill="#F6EBDD", font=label_font)
    elif not simple and plot["Period"].nunique() > 1:
        x0, y0, x1, y1 = 90, 145, 1300, 700
        values = plot["value_plot"].astype(float)
        vmin, vmax = min(0, values.min()), values.max()
        years = sorted(plot["Period"].unique().tolist())
        x_pos = {period: x0 + (x1 - x0) * i / max(len(years) - 1, 1) for i, period in enumerate(years)}
        for iso, group in plot.groupby("country_iso3"):
            pts = []
            for _, row in group.sort_values("period_date").iterrows():
                x = x_pos[row["Period"]]
                y = y1 - ((row["value_plot"] - vmin) / max(vmax - vmin, 1e-9)) * (y1 - y0)
                pts.append((x, y))
            color = COUNTRY_COLORS.get(iso, "#D6A84F")
            if len(pts) >= 2:
                draw.line(pts, fill=color, width=5)
            for x, y in pts:
                draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color)
            draw.text((x1 - 180, y0 + 30 * list(plot.groupby("country_iso3").groups).index(iso)), COUNTRY_NAMES.get(iso, iso), fill=color, font=small_font)
    else:
        x0, y0, x1, y1 = 90, 150, 1300, 690
        plot = latest_rows(plot)
        vmax = max(plot["value_plot"].astype(float).max(), 1e-9)
        bar_w = (x1 - x0) / max(len(plot), 1) * 0.55
        for i, (_, row) in enumerate(plot.iterrows()):
            x = x0 + (x1 - x0) * (i + 0.25) / max(len(plot), 1)
            bar_h = (row["value_plot"] / vmax) * (y1 - y0)
            color = COUNTRY_COLORS.get(row["country_iso3"], "#D6A84F")
            draw.rectangle((x, y1 - bar_h, x + bar_w, y1), fill=color)
            draw.text((x, y1 + 16), row["Country"], fill="#E9DFD0", font=small_font)
            draw.text((x, y1 - bar_h - 28), row["Value"], fill="#F6EBDD", font=small_font)
    draw.text((50, 780), "South Korea AI Industry Dashboard", fill="#9E927F", font=small_font)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def render_download(df: pd.DataFrame, title: str, simple: bool, key: str) -> None:
    st.download_button(
        "Download chart as JPG",
        data=jpeg_bytes(df, title, simple),
        file_name=f"{key}.jpg",
        mime="image/jpeg",
        width="content",
    )


def render_indicator(canonical: pd.DataFrame, timeseries: pd.DataFrame, indicator_id: str, index: int) -> None:
    title = indicator_name(canonical, indicator_id)
    st.markdown(f'<div class="chart-heading">{index}. {short_title(title, 96)}</div>', unsafe_allow_html=True)
    cols = st.columns([1.3, 1, 1])
    with cols[0]:
        simple = st.toggle("Simple bar view", value=False, key=f"{indicator_id}_simple")
    with cols[1]:
        compare_usa = st.toggle("Compare United States", value=True, key=f"{indicator_id}_usa")
    with cols[2]:
        compare_china = st.toggle("Compare China", value=True, key=f"{indicator_id}_china")
    countries = ["KOR"] + (["USA"] if compare_usa else []) + (["CHN"] if compare_china else [])
    df, mode = chartable_rows(canonical, timeseries, indicator_id, countries, simple)
    if useful_chart(df):
        fig = plot_indicator(df, mode, title, simple)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": True, "displaylogo": False})
        render_download(df, title, simple, slugify(indicator_id))
    else:
        latest_fact_cards(canonical[canonical["indicator_id"] == indicator_id], canonical[canonical["indicator_id"] == indicator_id]["category"].iloc[0], limit=1)
    interp = interpretation(canonical, timeseries, indicator_id, countries)
    if interp:
        st.markdown(f'<div class="interpretation"><span>Interpretation</span>{interp}</div>', unsafe_allow_html=True)


def slugify(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def inject_css() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebarNav"] {display: none !important;}
        .block-container {max-width: 1260px; padding-top: 1.4rem; padding-bottom: 3rem;}
        header[data-testid="stHeader"] {background: rgba(17,16,14,0.72);}
        .stApp {background: #11100E;}
        h1, h2, h3, .stMarkdown {color: #F4EFE7;}
        .hero {
            border: 1px solid rgba(226,184,107,0.28);
            background: linear-gradient(180deg, #1B1813 0%, #12110F 100%);
            padding: 1.35rem 1.5rem;
            border-radius: 8px;
            margin-bottom: 1rem;
        }
        .hero-title {
            font-family: Georgia, 'Times New Roman', serif;
            font-size: 2.15rem;
            color: #F6EBDD;
            line-height: 1.12;
            margin-bottom: 0.35rem;
        }
        .hero-subtitle {
            color: #BDB09E;
            font-size: 1rem;
            max-width: 880px;
        }
        .sector-note {
            border-left: 3px solid #D6A84F;
            padding: 0.2rem 0 0.2rem 0.9rem;
            color: #D5C8B6;
            margin: 0.2rem 0 1rem;
        }
        .chart-heading {
            font-family: Georgia, 'Times New Roman', serif;
            font-size: 1.35rem;
            color: #F6EBDD;
            padding-top: 1.4rem;
            margin-top: 1.2rem;
            border-top: 1px solid rgba(226,184,107,0.18);
        }
        .interpretation {
            color: #D9CCB8;
            background: rgba(255,255,255,0.035);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 0.8rem 0.95rem;
            margin-top: 0.45rem;
            line-height: 1.45;
        }
        .interpretation span {
            color: #D6A84F;
            display: block;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 0.3rem;
        }
        .fact-card {
            background: #191713;
            border: 1px solid rgba(226,184,107,0.18);
            border-radius: 8px;
            padding: 0.9rem;
            min-height: 120px;
            margin-bottom: 0.65rem;
        }
        .fact-label {color: #B8AA96; font-size: 0.86rem; line-height: 1.25;}
        .fact-value {color: #F6EBDD; font-size: 1.55rem; margin-top: 0.4rem;}
        .fact-period {color: #D6A84F; font-size: 0.82rem; margin-top: 0.35rem;}
        div[data-testid="stTabs"] button p {font-size: 0.95rem;}
        .stDownloadButton button, .stButton button {
            border-radius: 6px;
            border-color: rgba(226,184,107,0.45);
            background: #201C16;
            color: #F6EBDD;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_category(category: str, canonical: pd.DataFrame, timeseries: pd.DataFrame) -> None:
    st.markdown(f"## {category}")
    st.markdown(f'<div class="sector-note">{master_takeaway(canonical, category)}</div>', unsafe_allow_html=True)
    master = plot_master_heatmap(canonical, category)
    if master is not None:
        st.plotly_chart(master, width="stretch", config={"displayModeBar": True, "displaylogo": False})
        st.markdown(
            '<div class="interpretation"><span>Sector takeaway</span>The master chart indexes comparable indicators to Korea = 100. Values above 100 mean the comparison country is ahead of Korea on that specific measure; values below 100 mean Korea is ahead.</div>',
            unsafe_allow_html=True,
        )
    else:
        latest_fact_cards(canonical, category, limit=5)
    ids = [
        iid
        for iid in korea_indicator_ids(canonical, category)
        if not canonical[(canonical["indicator_id"] == iid) & (canonical["country_iso3"] == "KOR")].empty
    ][:10]
    for idx, indicator_id in enumerate(ids, start=1):
        render_indicator(canonical, timeseries, indicator_id, idx)


def render_dashboard(default_category: str | None = None) -> None:
    st.set_page_config(page_title="South Korea AI Industry Dashboard", layout="wide", initial_sidebar_state="collapsed")
    inject_css()
    bundle = load_data()
    canonical = bundle["canonical"]
    timeseries = bundle["timeseries"]
    if canonical.empty:
        st.stop()
    canonical = canonical[canonical["country_iso3"].isin(["KOR", "USA", "CHN"])].copy()
    korea_categories = [
        category
        for category in CATEGORY_ORDER
        if category in set(canonical.loc[canonical["country_iso3"] == "KOR", "category"])
    ]
    if default_category in korea_categories:
        selected = default_category
    else:
        selected = korea_categories[0]

    st.markdown(
        """
        <div class="hero">
            <div class="hero-title">South Korea AI Industry Dashboard</div>
            <div class="hero-subtitle">A Korea-first research dashboard for compute, models, funding, adoption, talent, public-sector capacity, and social readiness. Each chart carries its own comparison controls and interpretation.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    selected = st.radio("Section", korea_categories, index=korea_categories.index(selected), horizontal=True, label_visibility="collapsed")
    render_category(selected, canonical, timeseries)
