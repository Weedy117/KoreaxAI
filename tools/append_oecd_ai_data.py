from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(r"C:\Users\ASUS\Desktop\SAIS Playground\ROKxAI")
CONSOLIDATED = ROOT / "south_korea_ai_index_dashboard_data.csv"
OECD_DIR = ROOT / "oecd-ai-data"
OECD_CSV = OECD_DIR / "data.csv"
OECD_METADATA = OECD_DIR / "metadata.txt"

SOURCE_FIGURE = "oecd_openalex_ai_research_publications"
INDICATOR = "OECD.AI OpenAlex AI research publications by country, 2000-2026"


def clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", "").strip()
    return " ".join(text.split())


def parse_number(value: Any) -> float | None:
    text = clean_value(value).replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def readable_number(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return clean_value(value)
    return f"{number:,.4f}".rstrip("0").rstrip(".")


def rank_for_year(df: pd.DataFrame, year: str) -> tuple[str, str]:
    year_df = df[df["year"].astype(str) == str(year)].copy()
    values: list[tuple[str, float]] = []
    for _, row in year_df.iterrows():
        number = parse_number(row.get("publications", ""))
        country = clean_value(row.get("Country/territory", ""))
        if number is not None and country:
            values.append((country, number))
    values.sort(key=lambda item: item[1], reverse=True)
    for idx, (country, _) in enumerate(values, start=1):
        if country == "KOR":
            return str(idx), str(len(values))
    return "", str(len(values)) if values else ""


def main() -> None:
    existing = pd.read_csv(CONSOLIDATED, dtype=str, keep_default_na=False)
    source = pd.read_csv(OECD_CSV, dtype=str, keep_default_na=False)
    metadata = OECD_METADATA.read_text(encoding="utf-8", errors="replace").strip()

    korea = source[
        (source["Country/territory"].astype(str) == "KOR")
        | (source["Country/territory_label"].astype(str).str.lower() == "korea")
    ].copy()
    if korea.empty:
        raise RuntimeError("No Korea rows found in OECD source data.")

    new_rows: list[dict[str, str]] = []
    for _, row in korea.iterrows():
        rank, count = rank_for_year(source, clean_value(row.get("year", "")))
        original_fields = {col: clean_value(row.get(col, "")) for col in source.columns}
        original_fields["metadata"] = metadata
        new_rows.append(
            {
                "dashboard_category": "Models and research",
                "indicator": INDICATOR,
                "metric": "AI research publications",
                "geography": "South Korea",
                "period": clean_value(row.get("year", "")),
                "dimension_values": json.dumps(
                    {
                        "ai_concept": clean_value(row.get("ai_concept", "")),
                        "impact_level": clean_value(row.get("impact_level", "")),
                        "pub_type": clean_value(row.get("pub_type", "")),
                        "country_code": "KOR",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "value_raw": clean_value(row.get("publications", "")),
                "value_readable": readable_number(row.get("publications", "")),
                "value_unit": "source publications measure",
                "rank_descending_within_source": rank,
                "source_country_count": count,
                "source_chapter": "OECD.AI OpenAlex data",
                "source_figure": SOURCE_FIGURE,
                "source_csv": str(OECD_CSV.relative_to(ROOT)),
                "source_chart_pdf": "",
                "relevance_note": (
                    "South Korea AI research publication time series from the OECD.AI "
                    "OpenAlex extract; useful for research output trends."
                ),
                "original_fields_json": json.dumps(
                    original_fields, ensure_ascii=False, sort_keys=True
                ),
            }
        )

    appended = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
    appended = appended.drop_duplicates(
        subset=[
            "source_figure",
            "metric",
            "geography",
            "period",
            "dimension_values",
            "value_raw",
        ],
        keep="last",
    )
    appended = appended.sort_values(
        [
            "dashboard_category",
            "source_chapter",
            "source_figure",
            "indicator",
            "period",
            "metric",
            "dimension_values",
        ],
        kind="stable",
    )
    appended.to_csv(CONSOLIDATED, index=False, encoding="utf-8-sig")
    print(f"Appended {len(new_rows)} OECD rows; consolidated file now has {len(appended)} rows.")


if __name__ == "__main__":
    main()
