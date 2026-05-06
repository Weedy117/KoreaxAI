from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader


ROOT = Path(
    r"C:\Users\ASUS\Desktop\SAIS Playground\ROKxAI"
)
BASE = ROOT / (
    r"PUBLIC DATA_ 2026 AI INDEX REPORT-20260503T023514Z-3-001"
    r"\PUBLIC DATA_ 2026 AI INDEX REPORT"
)
OUTPUT = ROOT / "south_korea_ai_index_dashboard_data.csv"

KOREA_RE = re.compile(r"\b(south korea|republic of korea|korea|korean)\b", re.I)
NORTH_KOREA_RE = re.compile(r"\b(north korea|dprk|democratic people's republic of korea|prk)\b", re.I)

COUNTRY_COL_NAMES = {
    "country",
    "country/region",
    "country or region",
    "geographic area",
    "economy",
}

DIMENSION_HINTS = (
    "year",
    "date",
    "month",
    "quarter",
    "category",
    "label",
    "group",
    "specialisation",
    "specialization",
    "trust_in",
    "code",
    "iso",
)

TEXT_MEASURE_HINTS = ("status", "initiative_type")

TITLE_OVERRIDES = {
    "fig_1.8.5": "Distribution of top AI authors and inventors by AI specialization area and country",
    "fig_8.3.5": "Private AI investment by focus area and country, 2025",
    "fig_9.1.11": "Manager-reported organizational AI readiness categories by country",
    "fig_9.1.2": 'Share agreeing that products and services using AI have more benefits than drawbacks',
    "fig_9.1.3": "Public attitudes toward AI products and services by country",
    "fig_9.1.4": "Change in public attitudes toward AI products and services by country",
    "fig_9.1.6": "Expected AI impact across life and work categories by country",
    "fig_9.1.9": "Expected AI impact across economic and social categories by country",
    "fig_9.3.2": "Trust in institutions to develop and manage AI by country",
}


def rel(path: Path) -> str:
    return str(path.relative_to(BASE))


def clean_header(name: Any) -> str:
    text = str(name).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("Unnamed: ", "Unnamed ")
    return text


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).replace("\x00", "").strip()
    return re.sub(r"\s+", " ", text)


def is_korea_text(value: Any) -> bool:
    text = clean_value(value)
    return bool(KOREA_RE.search(text)) and not bool(NORTH_KOREA_RE.search(text))


def is_year_column(column: str) -> bool:
    return bool(re.fullmatch(r"(19|20)\d{2}", clean_header(column)))


def is_text_measure_column(column: str) -> bool:
    name = clean_header(column).lower()
    return name.startswith("has_") or any(hint in name for hint in TEXT_MEASURE_HINTS)


def parse_number(value: Any) -> float | None:
    text = clean_value(value)
    if not text:
        return None
    text = text.replace(",", "")
    text = text.replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def percent_like(metric: str, indicator: str) -> bool:
    haystack = f"{metric} {indicator}".lower()
    return any(
        token in haystack
        for token in (
            "%",
            "percent",
            "share",
            "diffusion",
            "concentration",
            "response",
            "female",
            "male",
            "trust",
            "used genai",
            "agree",
        )
    )


def infer_unit(metric: str, indicator: str, raw_value: Any) -> str:
    haystack = f"{metric} {indicator}".lower()
    raw = clean_value(raw_value)
    if "%" in raw or percent_like(metric, indicator):
        return "percent"
    if "billions of u.s. dollars" in haystack or "billions of us dollars" in haystack:
        return "US$ billions"
    if "investment" in haystack and "dollar" in haystack:
        return "US$"
    if "investment" in haystack and parse_number(raw_value) is not None:
        return "US$"
    if "in thousands" in haystack or "(in thousands)" in haystack:
        return "thousands"
    if "per 100,000" in haystack:
        return "per 100,000 inhabitants"
    if "index" in haystack:
        return "index"
    if "score" in haystack:
        return "score"
    if "proximity" in haystack:
        return "proximity score"
    if "data center" in haystack or "datacenter" in haystack:
        return "count"
    if "number of" in haystack or "count" in haystack:
        return "count"
    return ""


def readable_value(metric: str, indicator: str, raw_value: Any) -> str:
    raw = clean_value(raw_value)
    if not raw:
        return ""
    number = parse_number(raw)
    if number is None:
        return raw
    if percent_like(metric, indicator) or "%" in raw:
        pct = number if number > 1 or "%" in raw else number * 100
        return f"{pct:.2f}".rstrip("0").rstrip(".") + "%"
    if abs(number) >= 1_000_000_000:
        return f"{number:,.0f}"
    if abs(number) >= 10_000:
        return f"{number:,.2f}".rstrip("0").rstrip(".")
    if abs(number) >= 100:
        return f"{number:,.2f}".rstrip("0").rstrip(".")
    if abs(number) >= 1:
        return f"{number:,.4f}".rstrip("0").rstrip(".")
    return f"{number:.4f}".rstrip("0").rstrip(".")


def title_from_pdf(pdf_path: Path | None, fig: str, df: pd.DataFrame) -> str:
    if fig in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[fig]
    if pdf_path is not None and pdf_path.exists():
        try:
            text = PdfReader(str(pdf_path)).pages[0].extract_text() or ""
            text = text.replace("di\x00usion", "diffusion").replace("\x00rst", "first")
            text = text.replace("\x00", "")
            before_source = text.split("Source:")[0].strip()
            lines = [
                re.sub(r"\s+", " ", line).strip()
                for line in before_source.splitlines()
                if re.sub(r"\s+", " ", line).strip()
            ]
            if lines:
                candidate = lines[-1]
                if len(candidate) > 12:
                    return candidate
        except Exception:
            pass
    return "; ".join(clean_header(c) for c in df.columns[:4])


def category_for(chapter: str, fig: str) -> str:
    if fig.startswith("fig_1.3"):
        return "Compute and data centers"
    if fig.startswith("fig_1.1") or fig.startswith("fig_1.7"):
        return "Models and research"
    if fig.startswith("fig_1.8") or fig.startswith("fig_7."):
        return "Talent and education"
    if fig.startswith("fig_3."):
        return "Public sector and governance context"
    if fig.startswith("fig_4.2") or fig == "fig_8.3.5":
        return "Funding, startups, and investment"
    if fig.startswith("fig_4.3") or fig.startswith("fig_4.4") or fig.startswith("fig_4.5"):
        return "Industrial adoption and deployment"
    if fig.startswith("fig_6."):
        return "Sector deployment: medicine"
    if fig.startswith("fig_8.3.2"):
        return "Compute and data centers"
    if fig.startswith("fig_8."):
        return "Public sector and governance context"
    if fig.startswith("fig_9."):
        return "Social readiness"
    return chapter


def relevance_note(category: str, indicator: str) -> str:
    notes = {
        "Compute and data centers": "Korea-specific infrastructure or data-center indicator for compute capacity context.",
        "Models and research": "Korea-specific model, patent, research, or invention indicator.",
        "Talent and education": "Korea-specific AI talent, education, graduate, or skills indicator.",
        "Public sector and governance context": "Korea-specific AI policy, governance, public-sector, or legal context indicator.",
        "Funding, startups, and investment": "Korea-specific private AI investment or company funding indicator.",
        "Industrial adoption and deployment": "Korea-specific AI diffusion, labor market, or robotics deployment indicator.",
        "Sector deployment: medicine": "Korea-specific AI medicine publication/deployment proxy.",
        "Social readiness": "Korea-specific public or worker attitude indicator.",
    }
    return notes.get(category, f"Korea-specific row selected from {indicator}.")


def country_column(df: pd.DataFrame) -> str | None:
    for column in df.columns:
        normalized = clean_header(column).lower()
        if normalized in COUNTRY_COL_NAMES:
            return column
    for column in df.columns:
        values = df[column].dropna().astype(str).head(300).tolist()
        if any(is_korea_text(v) for v in values):
            return column
    return None


def dimension_columns(df: pd.DataFrame, country_col: str | None) -> list[str]:
    dims: list[str] = []
    for column in df.columns:
        if column == country_col:
            continue
        name = clean_header(column).lower()
        if is_text_measure_column(column):
            continue
        if is_year_column(name):
            continue
        values = df[column].dropna().astype(str).head(50).tolist()
        numeric_count = sum(parse_number(v) is not None for v in values)
        text_count = len(values) - numeric_count
        if any(hint in name for hint in DIMENSION_HINTS) or text_count > numeric_count:
            dims.append(column)
    return dims


def metric_columns(df: pd.DataFrame, country_col: str | None, dims: list[str]) -> list[str]:
    dim_set = set(dims)
    metrics: list[str] = []
    for column in df.columns:
        if column == country_col or column in dim_set:
            continue
        name = clean_header(column).lower()
        if "country code" in name or name in {"country_code", "iso_code"}:
            continue
        if is_text_measure_column(column):
            metrics.append(column)
            continue
        values = df[column].dropna().astype(str).head(100).tolist()
        if is_year_column(name) or any(parse_number(v) is not None for v in values):
            metrics.append(column)
        elif any(hint in name for hint in TEXT_MEASURE_HINTS):
            metrics.append(column)
    return metrics


def dimension_json(row: pd.Series, dims: list[str]) -> str:
    payload = {}
    for column in dims:
        value = clean_value(row.get(column, ""))
        if value:
            payload[clean_header(column)] = value
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def period_from(row: pd.Series, metric: str, dims: list[str]) -> str:
    if is_year_column(metric):
        return clean_header(metric)
    for key in ("Year", "year", "date", "Date", "year_month", "qyear"):
        if key in row.index and clean_value(row.get(key, "")):
            return clean_value(row.get(key, ""))
    for column in dims:
        if "year" in clean_header(column).lower() or "date" in clean_header(column).lower():
            return clean_value(row.get(column, ""))
    return ""


def compute_rank(
    df: pd.DataFrame,
    country_col: str,
    metric: str,
    row: pd.Series,
    dims: list[str],
) -> tuple[str, str]:
    values = []
    grouping_dims = [
        column
        for column in dims
        if column in df.columns
        and not any(token in clean_header(column).lower() for token in ("code", "iso"))
    ]
    for _, candidate in df.iterrows():
        if any(clean_value(candidate.get(d, "")) != clean_value(row.get(d, "")) for d in grouping_dims):
            continue
        number = parse_number(candidate.get(metric, ""))
        country = clean_value(candidate.get(country_col, ""))
        if number is not None and country:
            values.append((country, number))
    if len(values) < 2:
        return "", ""
    values.sort(key=lambda item: item[1], reverse=True)
    for idx, (country, _) in enumerate(values, start=1):
        if is_korea_text(country):
            return str(idx), str(len(values))
    return "", str(len(values))


def add_record(
    records: list[dict[str, Any]],
    *,
    category: str,
    indicator: str,
    chapter: str,
    fig: str,
    csv_path: Path,
    pdf_path: Path | None,
    geography: str,
    period: str,
    metric: str,
    dimension_values: str,
    value_raw: Any,
    rank: str = "",
    rank_count: str = "",
    original_fields: dict[str, Any] | None = None,
) -> None:
    raw = clean_value(value_raw)
    if not raw:
        return
    unit = infer_unit(metric, indicator, raw)
    records.append(
        {
            "dashboard_category": category,
            "indicator": indicator,
            "metric": clean_header(metric),
            "geography": geography,
            "period": period,
            "dimension_values": dimension_values,
            "value_raw": raw,
            "value_readable": readable_value(metric, indicator, raw),
            "value_unit": unit,
            "rank_descending_within_source": rank,
            "source_country_count": rank_count,
            "source_chapter": chapter,
            "source_figure": fig,
            "source_csv": rel(csv_path),
            "source_chart_pdf": rel(pdf_path) if pdf_path else "",
            "relevance_note": relevance_note(category, indicator),
            "original_fields_json": json.dumps(original_fields or {}, ensure_ascii=False, sort_keys=True),
        }
    )


def process_country_column(
    records: list[dict[str, Any]],
    df: pd.DataFrame,
    country_col: str,
    *,
    category: str,
    indicator: str,
    chapter: str,
    fig: str,
    csv_path: Path,
    pdf_path: Path | None,
) -> None:
    mask = df[country_col].astype(str).map(is_korea_text)
    subset = df[mask].copy()
    if subset.empty:
        return
    dims = dimension_columns(df, country_col)
    metrics = metric_columns(df, country_col, dims)
    if not metrics:
        # Keep text-only status rows rather than dropping governance indicators.
        metrics = [
            c
            for c in df.columns
            if c != country_col
            and c not in dims
            and "code" not in clean_header(c).lower()
            and "iso" not in clean_header(c).lower()
        ]
    for _, row in subset.iterrows():
        geography = clean_value(row.get(country_col, "")) or "South Korea"
        for metric in metrics:
            rank, count = "", ""
            if parse_number(row.get(metric, "")) is not None:
                rank, count = compute_rank(df, country_col, metric, row, dims)
            add_record(
                records,
                category=category,
                indicator=indicator,
                chapter=chapter,
                fig=fig,
                csv_path=csv_path,
                pdf_path=pdf_path,
                geography=geography,
                period=period_from(row, clean_header(metric), dims),
                metric=metric,
                dimension_values=dimension_json(row, dims),
                value_raw=row.get(metric, ""),
                rank=rank,
                rank_count=count,
                original_fields={clean_header(k): clean_value(v) for k, v in row.to_dict().items()},
            )


def process_korea_column(
    records: list[dict[str, Any]],
    df: pd.DataFrame,
    korea_col: str,
    *,
    category: str,
    indicator: str,
    chapter: str,
    fig: str,
    csv_path: Path,
    pdf_path: Path | None,
) -> None:
    dims = [
        c
        for c in df.columns
        if c != korea_col and not any(is_korea_text(other) for other in [clean_header(c)])
    ]
    for _, row in df.iterrows():
        rank, count = "", ""
        number = parse_number(row.get(korea_col, ""))
        if number is not None:
            country_values = []
            for col in df.columns:
                if col in dims:
                    continue
                value = parse_number(row.get(col, ""))
                if value is not None:
                    country_values.append((clean_header(col), value))
            if len(country_values) >= 2:
                country_values.sort(key=lambda item: item[1], reverse=True)
                count = str(len(country_values))
                for idx, (country, _) in enumerate(country_values, start=1):
                    if is_korea_text(country):
                        rank = str(idx)
                        break
        add_record(
            records,
            category=category,
            indicator=indicator,
            chapter=chapter,
            fig=fig,
            csv_path=csv_path,
            pdf_path=pdf_path,
            geography="South Korea",
            period=period_from(row, clean_header(korea_col), dims),
            metric=korea_col,
            dimension_values=dimension_json(row, dims),
            value_raw=row.get(korea_col, ""),
            rank=rank,
            rank_count=count,
            original_fields={clean_header(k): clean_value(v) for k, v in row.to_dict().items()},
        )


def read_csv_with_fallback(csv_path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return pd.read_csv(
                csv_path,
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
            )
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError(f"Unable to read {csv_path}")


def main() -> None:
    records: list[dict[str, Any]] = []
    pdf_by_fig = {path.stem: path for path in BASE.rglob("Charts/*.pdf")}

    for csv_path in sorted(BASE.rglob("Data/*.csv")):
        fig = csv_path.stem.replace("(1)", "")
        try:
            df = read_csv_with_fallback(csv_path)
        except Exception:
            continue
        df.columns = [clean_header(c) for c in df.columns]
        pdf_path = pdf_by_fig.get(fig)
        chapter = csv_path.relative_to(BASE).parts[0]
        indicator = title_from_pdf(pdf_path, fig, df)
        category = category_for(chapter, fig)

        ccol = country_column(df)
        if ccol is not None and df[ccol].astype(str).map(is_korea_text).any():
            process_country_column(
                records,
                df,
                ccol,
                category=category,
                indicator=indicator,
                chapter=chapter,
                fig=fig,
                csv_path=csv_path,
                pdf_path=pdf_path,
            )
            continue

        korea_columns = [c for c in df.columns if is_korea_text(c)]
        for korea_col in korea_columns:
            process_korea_column(
                records,
                df,
                korea_col,
                category=category,
                indicator=indicator,
                chapter=chapter,
                fig=fig,
                csv_path=csv_path,
                pdf_path=pdf_path,
            )

    out_df = pd.DataFrame(records)
    if out_df.empty:
        raise RuntimeError("No South Korea records were extracted.")

    # Drop exact duplicates from duplicate CSV copies while preserving source traceability.
    sort_cols = [
        "dashboard_category",
        "source_figure",
        "indicator",
        "period",
        "metric",
        "dimension_values",
        "geography",
    ]
    out_df = out_df.drop_duplicates(
        subset=[
            "source_figure",
            "metric",
            "geography",
            "period",
            "dimension_values",
            "value_raw",
        ]
    ).sort_values(sort_cols, kind="stable")

    out_df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(out_df)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
