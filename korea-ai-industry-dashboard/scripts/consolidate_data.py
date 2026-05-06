from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARENT_ROOT = PROJECT_ROOT.parent
CONSOLIDATED_DIR = PROJECT_ROOT / "data" / "consolidated"
REPORTS_DIR = PROJECT_ROOT / "data" / "reports"
MANUAL_REVIEW_DIR = PROJECT_ROOT / "data" / "manual_review"
DOCS_DIR = PROJECT_ROOT / "docs"

SILVER_OBSERVATIONS = PROJECT_ROOT / "data" / "silver" / "observations.csv"
SILVER_REVIEW = PROJECT_ROOT / "data" / "silver" / "manual_review_queue.csv"
AI_INDEX_EXISTING = PARENT_ROOT / "south_korea_ai_index_dashboard_data.csv"
SOURCE_REGISTRY = PROJECT_ROOT / "sources" / "source_registry.yaml"
INDICATOR_CATALOG = PROJECT_ROOT / "sources" / "indicator_catalog.yaml"
RAW_FILE_INVENTORY = REPORTS_DIR / "raw_file_inventory.csv"

OBS_COLUMNS = [
    "observation_id",
    "indicator_id",
    "indicator_name",
    "category",
    "subcategory",
    "country_iso3",
    "country_name",
    "comparison_group",
    "period_type",
    "year",
    "period_start",
    "period_end",
    "period_label",
    "value_raw",
    "value_numeric",
    "unit",
    "unit_standardized",
    "value_standardized",
    "standardization_note",
    "indicator_type",
    "source_id",
    "source_name",
    "source_url",
    "source_file_path",
    "source_publication_date",
    "retrieved_at",
    "confidence_tier",
    "uncertainty_note",
    "is_canonical",
    "canonical_selection_reason",
    "source_priority",
    "dedupe_key",
    "normalization_method",
    "notes",
]

ALLOWED_INDICATOR_TYPES = {
    "observed_metric",
    "official_target",
    "estimate",
    "company_claim",
    "index_metric",
    "survey_metric",
    "manual_classification",
    "contextual_fact",
    "missing",
}

ALLOWED_CONFIDENCE = {
    "high",
    "medium_high",
    "medium",
    "medium_low",
    "low",
    "manual_review",
}

COUNTRY_ALIASES = {
    "south korea": ("KOR", "South Korea"),
    "republic of korea": ("KOR", "South Korea"),
    "korea, rep.": ("KOR", "South Korea"),
    "korea": ("KOR", "South Korea"),
    "rok": ("KOR", "South Korea"),
    "대한민국": ("KOR", "South Korea"),
    "kor": ("KOR", "South Korea"),
    "united states": ("USA", "United States"),
    "united states of america": ("USA", "United States"),
    "usa": ("USA", "United States"),
    "u.s.": ("USA", "United States"),
    "us": ("USA", "United States"),
    "united states america": ("USA", "United States"),
    "china": ("CHN", "China"),
    "people's republic of china": ("CHN", "China"),
    "people’s republic of china": ("CHN", "China"),
    "china (people's republic of)": ("CHN", "China"),
    "prc": ("CHN", "China"),
    "mainland china": ("CHN", "China"),
    "chn": ("CHN", "China"),
}

NORTH_KOREA_RE = re.compile(r"\b(north korea|dprk|democratic people's republic of korea|prk)\b", re.I)

CONFIDENCE_SCORE = {
    "high": 1,
    "medium_high": 2,
    "medium": 3,
    "medium_low": 4,
    "low": 5,
    "manual_review": 6,
}

TYPE_SCORE = {
    "observed_metric": 1,
    "official_target": 2,
    "index_metric": 3,
    "survey_metric": 4,
    "estimate": 5,
    "manual_classification": 6,
    "company_claim": 7,
    "contextual_fact": 8,
    "missing": 9,
}

SOURCE_TYPE_PRIORITY = {
    "official_statistics": 1,
    "official_data_portal": 1,
    "official_report": 2,
    "official_press_release": 2,
    "company_filings": 3,
    "public_api": 4,
    "data_portal": 4,
    "public_dataset": 5,
    "annual_report_data": 5,
    "public_ranked_list": 5,
    "index_data": 5,
    "press_release_report": 6,
    "report": 6,
    "company_press_release": 7,
    "market_report": 8,
    "media": 9,
}

CATEGORY_MAP = {
    "compute": "Compute and Data Centers",
    "models": "Models, Research, and Funding",
    "research": "Models, Research, and Funding",
    "funding": "Models, Research, and Funding",
    "startups": "Models, Research, and Funding",
    "semiconductors": "Hardware and Semiconductors",
    "hardware": "Hardware and Semiconductors",
    "adoption": "Adoption and Industry",
    "worker_adoption": "Adoption and Industry",
    "productivity": "Adoption and Industry",
    "talent": "Talent, Public Sector, and Defense",
    "education": "Talent, Public Sector, and Defense",
    "public_sector": "Talent, Public Sector, and Defense",
    "governance": "Talent, Public Sector, and Defense",
    "defense": "Talent, Public Sector, and Defense",
    "social_readiness": "Social Readiness",
    "Compute and data centers": "Compute and Data Centers",
    "Funding, startups, and investment": "Models, Research, and Funding",
    "Industrial adoption and deployment": "Adoption and Industry",
    "Models and research": "Models, Research, and Funding",
    "Public sector and governance context": "Talent, Public Sector, and Defense",
    "Sector deployment: medicine": "Adoption and Industry",
    "Social readiness": "Social Readiness",
    "Talent and education": "Talent, Public Sector, and Defense",
}

PAGE_BY_CATEGORY = {
    "Compute and Data Centers": "Compute and Data Centers",
    "Hardware and Semiconductors": "Hardware and Semiconductors",
    "Models, Research, and Funding": "Models, Research, and Funding",
    "Adoption and Industry": "Adoption and Industry",
    "Talent, Public Sector, and Defense": "Talent, Public Sector, and Defense",
    "Social Readiness": "Overview",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\x00", "").strip())


def slugify(text: str, max_len: int = 92) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", clean_text(text).lower()).strip("_")
    return (slug[:max_len].rstrip("_") or "unknown")


def stable_id(prefix: str, parts: list[Any], length: int = 14) -> str:
    payload = "|".join(clean_text(part) for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def parse_number(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace(",", "").replace("%", "")
    text = re.sub(r"^\$", "", text)
    try:
        return float(text)
    except ValueError:
        return None


def normalize_country(value: Any) -> tuple[str, str, str]:
    text = clean_text(value)
    if not text:
        return "UNKNOWN", "Unknown", "Country missing."
    if NORTH_KOREA_RE.search(text):
        return "UNKNOWN", text, "Country value appears to be North Korea, not South Korea."
    key = text.lower().replace("’", "'")
    key = re.sub(r"\s+", " ", key)
    if key in COUNTRY_ALIASES:
        iso, name = COUNTRY_ALIASES[key]
        return iso, name, ""
    if "south korea" in key or key == "korea":
        return "KOR", "South Korea", ""
    if "united states" in key:
        return "USA", "United States", ""
    if "china" in key and "taiwan" not in key and "hong kong" not in key:
        return "CHN", "China", ""
    if key in {"kr", "kor"}:
        return "KOR", "South Korea", ""
    if key in {"cn", "chn"}:
        return "CHN", "China", ""
    return "UNKNOWN", text, "Country could not be confidently normalized."


def normalize_category(category: Any) -> str:
    text = clean_text(category)
    return CATEGORY_MAP.get(text, CATEGORY_MAP.get(text.lower(), text.title() if text else "Uncategorized"))


def normalize_indicator_type(value: Any) -> str:
    text = clean_text(value).lower()
    return text if text in ALLOWED_INDICATOR_TYPES else "observed_metric"


def normalize_confidence(value: Any) -> str:
    text = clean_text(value).lower()
    return text if text in ALLOWED_CONFIDENCE else "manual_review"


def normalize_unit(unit: Any, indicator_name: str = "") -> tuple[str, str]:
    raw = clean_text(unit)
    key = raw.lower()
    note = ""
    mapping = {
        "percent": "percent",
        "%": "percent",
        "count": "count",
        "gpu count": "count",
        "number": "count",
        "pflop/s": "PFLOP/s",
        "petaflop/s": "PFLOP/s",
        "flop": "FLOP",
        "op/s": "OP/s",
        "h100e": "H100e",
        "mw": "MW",
        "krw": "KRW",
        "usd": "USD",
        "us$": "USD",
        "us$ billions": "USD_billion",
        "billions of u.s. dollars": "USD_billion",
        "rank": "rank",
        "index": "index",
        "score": "score",
        "source publications measure": "source_publications_measure",
        "robots per 10,000 employees": "robots_per_10000_manufacturing_workers",
        "robots per 10,000 manufacturing workers": "robots_per_10000_manufacturing_workers",
        "patents per capita": "patents_per_100000_inhabitants",
        "per 100,000 inhabitants": "per_100000_inhabitants",
        "thousands": "thousands",
    }
    if key in mapping:
        return mapping[key], note
    if "percent" in key or "%" in key:
        return "percent", note
    if "billion" in key and ("u.s. dollar" in key or "usd" in key or "us$" in key):
        return "USD_billion", note
    if "robot" in key and "10,000" in key:
        return "robots_per_10000_manufacturing_workers", note
    if "patent" in key and ("100,000" in key or "capita" in key):
        return "patents_per_100000_inhabitants", "Original unit label preserved; AI Index value appears per 100,000 inhabitants."
    if not raw and parse_number(indicator_name) is None:
        return "", "No unit supplied by source."
    return raw, note


def standardized_value(value_raw: Any, unit_raw: str, unit_std: str) -> tuple[str, str]:
    number = parse_number(value_raw)
    if number is None:
        return "", "Non-numeric value preserved in value_raw."
    raw_text = clean_text(value_raw)
    if unit_std == "percent":
        if number <= 1 and "%" not in raw_text:
            return str(number * 100), "Converted decimal share to percent."
        return str(number), "Percent value preserved."
    return str(number), "Numeric value parsed; no unit conversion applied."


def parse_period(value: Any, fallback_year: Any = "") -> tuple[str, str, str, str, str]:
    text = clean_text(value) or clean_text(fallback_year)
    if not text:
        return "", "", "", "", ""
    q_match = re.fullmatch(r"(\d{4})[- ]?Q([1-4])", text, flags=re.I) or re.fullmatch(r"Q([1-4])[- ]?(\d{4})", text, flags=re.I)
    if q_match:
        if len(q_match.group(1)) == 4:
            year, quarter = int(q_match.group(1)), int(q_match.group(2))
        else:
            quarter, year = int(q_match.group(1)), int(q_match.group(2))
        start_month = 1 + (quarter - 1) * 3
        end_month = start_month + 2
        start = date(year, start_month, 1)
        end = date(year, end_month, monthrange(year, end_month)[1])
        return "quarterly", str(year), start.isoformat(), end.isoformat(), f"{year} Q{quarter}"
    month_match = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
    if month_match:
        year, month = int(month_match.group(1)), int(month_match.group(2))
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        return "monthly", str(year), start.isoformat(), end.isoformat(), f"{year}-{month:02d}"
    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    if year_match and re.fullmatch(r"\d{4}(\.0)?", text):
        year = int(float(text))
        return "annual", str(year), f"{year}-01-01", f"{year}-12-31", str(year)
    try:
        dt = pd.to_datetime(text, errors="raise")
        if not pd.isna(dt):
            return "event", str(dt.year), dt.date().isoformat(), dt.date().isoformat(), dt.date().isoformat()
    except Exception:
        pass
    if year_match:
        year = int(year_match.group(0))
        return "annual", str(year), f"{year}-01-01", f"{year}-12-31", str(year)
    return "", "", "", "", text


def load_yaml_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return data if isinstance(data, list) else []


def load_catalog() -> dict[str, dict[str, Any]]:
    return {clean_text(row.get("indicator_id")): row for row in load_yaml_list(INDICATOR_CATALOG)}


def load_sources() -> dict[str, dict[str, Any]]:
    sources = {clean_text(row.get("source_id")): row for row in load_yaml_list(SOURCE_REGISTRY)}
    sources.setdefault(
        "south_korea_ai_index_dashboard_data",
        {
            "source_id": "south_korea_ai_index_dashboard_data",
            "publisher": "Local consolidated AI Index/OECD extract",
            "title": "South Korea AI Index dashboard data",
            "url": "",
            "source_type": "annual_report_data",
            "confidence_tier": "medium_high",
            "notes": "Previously consolidated local CSV created from AI Index public data and OECD.AI OpenAlex extract.",
        },
    )
    sources.setdefault(
        "stanford_ai_index_2026_public_data_bundle",
        {
            "source_id": "stanford_ai_index_2026_public_data_bundle",
            "publisher": "Stanford HAI",
            "title": "2026 AI Index Report public data bundle",
            "url": "https://hai.stanford.edu/ai-index",
            "source_type": "annual_report_data",
            "confidence_tier": "medium_high",
            "notes": "Local public-data bundle; individual source figure preserved in source_file_path and notes.",
        },
    )
    sources.setdefault(
        "oecd_ai_openalex_existing",
        {
            "source_id": "oecd_ai_openalex_existing",
            "publisher": "OECD.AI / OpenAlex",
            "title": "OpenAlex AI research publications extract",
            "url": "",
            "source_type": "public_dataset",
            "confidence_tier": "medium_high",
            "notes": "Local OECD.AI export based on OpenAlex.",
        },
    )
    return sources


def source_priority(source: dict[str, Any]) -> int:
    return SOURCE_TYPE_PRIORITY.get(clean_text(source.get("source_type")).lower(), 9)


def source_name(source_id: str, sources: dict[str, dict[str, Any]]) -> str:
    src = sources.get(source_id, {})
    return clean_text(src.get("title")) or clean_text(src.get("publisher")) or source_id


def dashboard_page(category: str) -> str:
    return PAGE_BY_CATEGORY.get(category, "Source Explorer")


def make_observation(row: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source_id = clean_text(row.get("source_id")) or "unknown_source"
    source = sources.get(source_id, {})
    country_iso3, country_name, country_note = normalize_country(row.get("country_iso3") or row.get("country_name") or row.get("geography"))
    if clean_text(row.get("country_iso3")).upper() in {"KOR", "USA", "CHN"}:
        country_iso3 = clean_text(row.get("country_iso3")).upper()
        country_name = {"KOR": "South Korea", "USA": "United States", "CHN": "China"}[country_iso3]
        country_note = ""
    period_type, year, period_start, period_end, period_label = parse_period(row.get("period_label") or row.get("time_period") or row.get("period") or row.get("year"), row.get("year"))
    unit_std, unit_note = normalize_unit(row.get("unit") or row.get("value_unit"), row.get("indicator_name"))
    value_raw = clean_text(row.get("value_raw") if "value_raw" in row else row.get("value"))
    value_num = parse_number(value_raw)
    value_std, std_note = standardized_value(value_raw, clean_text(row.get("unit") or row.get("value_unit")), unit_std)
    indicator_id = clean_text(row.get("indicator_id")) or slugify(f"{row.get('indicator_name')} {row.get('metric')}")
    indicator_name = clean_text(row.get("indicator_name")) or clean_text(row.get("indicator")) or indicator_id.replace("_", " ").title()
    category = normalize_category(row.get("category") or row.get("dashboard_category"))
    indicator_type = normalize_indicator_type(row.get("indicator_type"))
    confidence = normalize_confidence(row.get("confidence_tier") or source.get("confidence_tier"))
    source_path = clean_text(row.get("source_file_path") or row.get("source_csv"))
    notes = clean_text(row.get("notes"))
    extra_notes = [clean_text(row.get("relevance_note")), clean_text(row.get("dimension_values"))]
    if country_note:
        extra_notes.append(country_note)
    if unit_note:
        extra_notes.append(unit_note)
    if clean_text(row.get("original_fields_json")):
        extra_notes.append(f"Original fields: {clean_text(row.get('original_fields_json'))[:1000]}")
    merged_notes = " | ".join(part for part in [notes, *extra_notes] if part)
    obs = {
        "observation_id": "",
        "indicator_id": indicator_id,
        "indicator_name": indicator_name,
        "category": category,
        "subcategory": clean_text(row.get("subcategory") or category),
        "country_iso3": country_iso3,
        "country_name": country_name,
        "comparison_group": clean_text(row.get("comparison_group")) or ("KOR/USA/CHN" if country_iso3 in {"KOR", "USA", "CHN"} else "Other"),
        "period_type": period_type,
        "year": year,
        "period_start": period_start,
        "period_end": period_end,
        "period_label": period_label,
        "value_raw": value_raw,
        "value_numeric": "" if value_num is None else str(value_num),
        "unit": clean_text(row.get("unit") or row.get("value_unit")),
        "unit_standardized": unit_std,
        "value_standardized": value_std,
        "standardization_note": std_note,
        "indicator_type": indicator_type,
        "source_id": source_id,
        "source_name": clean_text(row.get("source_name")) or source_name(source_id, sources),
        "source_url": clean_text(row.get("source_url") or source.get("url")),
        "source_file_path": source_path,
        "source_publication_date": clean_text(row.get("source_publication_date")),
        "retrieved_at": clean_text(row.get("retrieved_at")) or now_iso(),
        "confidence_tier": confidence,
        "uncertainty_note": clean_text(row.get("uncertainty_note") or source.get("notes")),
        "is_canonical": False,
        "canonical_selection_reason": "",
        "source_priority": source_priority(source),
        "dedupe_key": "",
        "normalization_method": clean_text(row.get("normalization_method")) or "mapped_to_master_schema",
        "notes": merged_notes,
    }
    obs["dedupe_key"] = "|".join(
        [
            obs["indicator_id"],
            obs["country_iso3"],
            obs["period_start"],
            obs["period_end"],
            obs["unit_standardized"],
        ]
    )
    obs["observation_id"] = stable_id(
        "obs",
        [
            obs["indicator_id"],
            obs["country_iso3"],
            obs["period_start"],
            obs["period_end"],
            obs["value_raw"],
            obs["unit_standardized"],
            obs["source_id"],
        ],
    )
    return obs


def read_silver_observations(sources: dict[str, dict[str, Any]], catalog: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not SILVER_OBSERVATIONS.exists():
        return []
    df = pd.read_csv(SILVER_OBSERVATIONS, dtype=str, keep_default_na=False)
    records = []
    for _, row in df.iterrows():
        raw = row.to_dict()
        meta = catalog.get(clean_text(raw.get("indicator_id")), {})
        raw["indicator_name"] = clean_text(meta.get("indicator_name")) or clean_text(raw.get("indicator_id")).replace("_", " ").title()
        raw["subcategory"] = clean_text(meta.get("category")) or clean_text(raw.get("category"))
        raw["source_file_path"] = clean_text(raw.get("source_file_path"))
        records.append(make_observation(raw, sources))
    return records


def infer_ai_index_source_id(row: dict[str, Any]) -> str:
    if clean_text(row.get("source_chapter")).lower().startswith("oecd"):
        return "oecd_ai_openalex_existing"
    if clean_text(row.get("source_figure")).startswith("oecd_"):
        return "oecd_ai_openalex_existing"
    return "stanford_ai_index_2026_public_data_bundle"


def indicator_type_from_ai_index(category: str, metric: str, value_raw: str) -> str:
    cat = category.lower()
    metric_l = metric.lower()
    if "social" in cat or "respondent" in metric_l or "trust" in metric_l:
        return "survey_metric"
    if "status" in metric_l or value_raw.lower() in {"yes", "no", "legislation"}:
        return "contextual_fact"
    if "rank" in metric_l:
        return "index_metric"
    if "investment" in cat or "funding" in cat:
        return "observed_metric"
    if "governance" in cat:
        return "index_metric"
    return "observed_metric"


def read_existing_ai_index_csv(sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not AI_INDEX_EXISTING.exists():
        return []
    df = pd.read_csv(AI_INDEX_EXISTING, dtype=str, keep_default_na=False)
    records = []
    for _, row in df.iterrows():
        raw = row.to_dict()
        source_id = infer_ai_index_source_id(raw)
        source_csv = clean_text(raw.get("source_csv"))
        figure = clean_text(raw.get("source_figure"))
        metric = clean_text(raw.get("metric"))
        indicator = clean_text(raw.get("indicator")) or f"{figure} {metric}"
        indicator_id = (
            "oecd_openalex_ai_research_publications"
            if source_id == "oecd_ai_openalex_existing"
            else slugify(f"ai_index_{figure}_{metric}")
        )
        value_raw = clean_text(raw.get("value_raw"))
        country_iso3, country_name, _ = normalize_country(raw.get("geography"))
        mapped = {
            "indicator_id": indicator_id,
            "indicator_name": indicator,
            "category": raw.get("dashboard_category"),
            "subcategory": metric,
            "country_iso3": country_iso3,
            "country_name": country_name,
            "comparison_group": "KOR/USA/CHN" if country_iso3 in {"KOR", "USA", "CHN"} else "Korea only",
            "period_label": raw.get("period"),
            "year": raw.get("period"),
            "value_raw": value_raw,
            "unit": raw.get("value_unit"),
            "indicator_type": indicator_type_from_ai_index(clean_text(raw.get("dashboard_category")), metric, value_raw),
            "source_id": source_id,
            "source_name": source_name(source_id, sources),
            "source_url": sources.get(source_id, {}).get("url", ""),
            "source_file_path": source_csv or str(AI_INDEX_EXISTING.relative_to(PARENT_ROOT)),
            "retrieved_at": "",
            "confidence_tier": sources.get(source_id, {}).get("confidence_tier", "medium_high"),
            "uncertainty_note": raw.get("relevance_note"),
            "notes": f"Source figure: {figure}; source chapter: {clean_text(raw.get('source_chapter'))}",
            "relevance_note": raw.get("relevance_note"),
            "dimension_values": raw.get("dimension_values"),
            "original_fields_json": raw.get("original_fields_json"),
        }
        records.append(make_observation(mapped, sources))
    return records


def exact_duplicate_columns() -> list[str]:
    return [
        "indicator_id",
        "country_iso3",
        "period_start",
        "period_end",
        "value_numeric",
        "unit_standardized",
        "source_id",
    ]


def canonical_group_columns() -> list[str]:
    return ["indicator_id", "country_iso3", "period_start", "period_end", "unit_standardized"]


def select_canonical(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df["is_canonical"] = False
    review_items = []
    for group_key, group in df.groupby(canonical_group_columns(), dropna=False):
        sortable = group.copy()
        sortable["_source_priority"] = pd.to_numeric(sortable["source_priority"], errors="coerce").fillna(9)
        sortable["_confidence_score"] = sortable["confidence_tier"].map(CONFIDENCE_SCORE).fillna(6)
        sortable["_type_score"] = sortable["indicator_type"].map(TYPE_SCORE).fillna(9)
        sortable["_has_value"] = sortable["value_numeric"].apply(lambda x: 0 if clean_text(x) else 1)
        winner_idx = sortable.sort_values(
            ["_has_value", "_source_priority", "_confidence_score", "_type_score", "retrieved_at"],
            ascending=[True, True, True, True, False],
            kind="stable",
        ).index[0]
        df.loc[winner_idx, "is_canonical"] = True
        if len(group) == 1:
            df.loc[winner_idx, "canonical_selection_reason"] = "Only observation for indicator/country/period/unit."
        else:
            values = sorted(set(clean_text(v) for v in group["value_numeric"]))
            sources = sorted(set(clean_text(v) for v in group["source_id"]))
            df.loc[winner_idx, "canonical_selection_reason"] = (
                "Selected by source hierarchy, confidence tier, indicator type, and recency; "
                f"competed with {len(group)-1} alternative rows from {', '.join(sources)}."
            )
            review_items.append(
                {
                    "item_id": stable_id("mr", ["duplicate_conflict", *map(str, group_key)]),
                    "issue_type": "duplicate_conflict" if len(values) > 1 else "conflicting_values",
                    "indicator_id": group_key[0],
                    "country_iso3": group_key[1],
                    "year": clean_text(group["year"].iloc[0]),
                    "source_id": ";".join(sources),
                    "source_file_path": ";".join(sorted(set(clean_text(v) for v in group["source_file_path"]))),
                    "value_raw": ";".join(sorted(set(clean_text(v) for v in group["value_raw"]))),
                    "value_numeric": ";".join(values),
                    "unit": group_key[4],
                    "reason_for_review": "Competing observations share indicator/country/period/unit. Canonical selected by documented hierarchy.",
                    "recommended_action": "Review whether definitions and methods are comparable before using alternatives.",
                    "status": "open",
                    "reviewer_note": "",
                }
            )
    return df, pd.DataFrame(review_items)


def make_sources_table(sources: dict[str, dict[str, Any]], observations: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    rows = []
    used_source_ids = sorted(set(observations["source_id"]) | set(inventory.get("detected_source_id", pd.Series(dtype=str)).astype(str)))
    for source_id in used_source_ids:
        src = sources.get(source_id, {})
        raw_paths = inventory[inventory.get("detected_source_id", "") == source_id]["file_path"].tolist() if not inventory.empty else []
        rows.append(
            {
                "source_id": source_id,
                "source_name": clean_text(src.get("title")) or clean_text(src.get("publisher")) or source_id,
                "publisher": clean_text(src.get("publisher")),
                "title": clean_text(src.get("title")) or source_id,
                "url": clean_text(src.get("url")),
                "source_type": clean_text(src.get("source_type")) or "inferred_local_file",
                "access_method": clean_text(src.get("access_method")) or "local file",
                "confidence_tier": normalize_confidence(src.get("confidence_tier")) if src else "manual_review",
                "update_cadence": clean_text(src.get("update_cadence")),
                "modules": ",".join(src.get("modules", [])) if isinstance(src.get("modules"), list) else clean_text(src.get("modules")),
                "raw_file_path": ";".join(raw_paths),
                "notes": clean_text(src.get("notes")) or ("Source metadata inferred from local files; review recommended." if not src else ""),
            }
        )
    return pd.DataFrame(rows)


def preferred_chart(unit: str, time_ready: bool) -> str:
    if time_ready:
        return "line"
    if unit == "rank":
        return "bar"
    return "bar"


def make_indicators_table(observations: pd.DataFrame, catalog: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for indicator_id, group in observations.groupby("indicator_id"):
        meta = catalog.get(indicator_id, {})
        first = group.iloc[0]
        category = clean_text(first["category"])
        unit = clean_text(meta.get("unit")) or clean_text(first["unit_standardized"])
        time_ready = bool((group["period_start"].astype(str) != "").any() and (group["value_numeric"].astype(str) != "").any())
        rows.append(
            {
                "indicator_id": indicator_id,
                "indicator_name": clean_text(meta.get("indicator_name")) or clean_text(first["indicator_name"]),
                "category": category,
                "subcategory": clean_text(meta.get("category")) or clean_text(first["subcategory"]),
                "definition": clean_text(meta.get("definition")),
                "unit_standardized": unit,
                "preferred_chart_type": preferred_chart(unit, time_ready),
                "dashboard_page": dashboard_page(category),
                "comparison_required": "yes" if group["country_iso3"].isin(["KOR", "USA", "CHN"]).nunique() > 1 else "no",
                "time_series_ready": "yes" if time_ready else "no",
                "primary_source_id": clean_text(meta.get("primary_source_id")) or clean_text(first["source_id"]),
                "confidence_default": clean_text(meta.get("confidence_tier")) or clean_text(first["confidence_tier"]),
                "relevance_note": clean_text(meta.get("relevance_note")) or clean_text(first["notes"])[:400],
                "notes": clean_text(meta.get("notes")),
            }
        )
    return pd.DataFrame(rows).sort_values(["category", "indicator_name"])


def make_comparison_coverage(canonical: pd.DataFrame, indicators: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, ind in indicators.iterrows():
        indicator_id = ind["indicator_id"]
        group = canonical[canonical["indicator_id"] == indicator_id]
        countries = set(group["country_iso3"])
        years = {
            iso: pd.to_numeric(group[group["country_iso3"] == iso]["year"], errors="coerce").dropna()
            for iso in ["KOR", "USA", "CHN"]
        }
        has_kor, has_usa, has_chn = "KOR" in countries, "USA" in countries, "CHN" in countries
        if has_kor and has_usa and has_chn:
            status = "complete_kor_usa_chn"
        elif has_kor and (has_usa or has_chn):
            status = "partial_comparison"
        elif has_kor:
            status = "korea_only"
        elif not len(group):
            status = "unavailable"
        else:
            status = "partial_comparison"
        rows.append(
            {
                "indicator_id": indicator_id,
                "indicator_name": ind["indicator_name"],
                "category": ind["category"],
                "has_kor": has_kor,
                "has_usa": has_usa,
                "has_chn": has_chn,
                "latest_kor_year": "" if years["KOR"].empty else str(int(years["KOR"].max())),
                "latest_usa_year": "" if years["USA"].empty else str(int(years["USA"].max())),
                "latest_chn_year": "" if years["CHN"].empty else str(int(years["CHN"].max())),
                "comparison_status": status,
                "notes": "Coverage based on canonical observations only; source comparability still requires review." if status != "korea_only" else "",
            }
        )
    return pd.DataFrame(rows).sort_values(["category", "indicator_name"])


def make_timeseries(canonical: pd.DataFrame) -> pd.DataFrame:
    usable = canonical[
        (canonical["value_numeric"].astype(str) != "")
        & (canonical["period_start"].astype(str) != "")
        & ~((canonical["indicator_type"] == "contextual_fact") & (canonical["value_numeric"].astype(str) == ""))
        & ~canonical["confidence_tier"].isin(["low", "manual_review"])
    ].copy()
    return usable.sort_values(["indicator_id", "country_iso3", "period_start"])


def make_existing_review_queue(sources: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    if SILVER_REVIEW.exists():
        df = pd.read_csv(SILVER_REVIEW, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            issue = clean_text(row.get("issue_type"))
            mapped_issue = "missing_value" if issue in {"download_failed", "extraction_failed"} else "unclear_indicator_mapping"
            rows.append(
                {
                    "item_id": clean_text(row.get("item_id")) or stable_id("mr", row.to_dict().values()),
                    "issue_type": mapped_issue,
                    "indicator_id": clean_text(row.get("indicator_id")),
                    "country_iso3": "",
                    "year": "",
                    "source_id": clean_text(row.get("source_id")),
                    "source_file_path": "",
                    "value_raw": clean_text(row.get("claim_or_value_to_check")),
                    "value_numeric": "",
                    "unit": "",
                    "reason_for_review": clean_text(row.get("reason_for_review")) or "Existing manual review item from prior collection pass.",
                    "recommended_action": "Review source file or source URL and map into master schema if usable.",
                    "status": clean_text(row.get("status")) or "open",
                    "reviewer_note": clean_text(row.get("reviewer_note")),
                }
            )
    return pd.DataFrame(rows)


def generated_review_items(all_obs: pd.DataFrame, sources: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for _, row in all_obs.iterrows():
        if row["country_iso3"] == "UNKNOWN":
            rows.append(
                {
                    "item_id": stable_id("mr", ["ambiguous_country", row["observation_id"]]),
                    "issue_type": "ambiguous_country",
                    "indicator_id": row["indicator_id"],
                    "country_iso3": row["country_iso3"],
                    "year": row["year"],
                    "source_id": row["source_id"],
                    "source_file_path": row["source_file_path"],
                    "value_raw": row["value_raw"],
                    "value_numeric": row["value_numeric"],
                    "unit": row["unit"],
                    "reason_for_review": "Country could not be confidently mapped to KOR, USA, or CHN.",
                    "recommended_action": "Confirm country and update source mapping.",
                    "status": "open",
                    "reviewer_note": "",
                }
            )
        if row["unit_standardized"] == "" and row["value_numeric"] != "":
            rows.append(
                {
                    "item_id": stable_id("mr", ["ambiguous_unit", row["observation_id"]]),
                    "issue_type": "ambiguous_unit",
                    "indicator_id": row["indicator_id"],
                    "country_iso3": row["country_iso3"],
                    "year": row["year"],
                    "source_id": row["source_id"],
                    "source_file_path": row["source_file_path"],
                    "value_raw": row["value_raw"],
                    "value_numeric": row["value_numeric"],
                    "unit": row["unit"],
                    "reason_for_review": "Numeric value has no standardized unit.",
                    "recommended_action": "Confirm unit from source documentation before charting.",
                    "status": "open",
                    "reviewer_note": "",
                }
            )
        if row["confidence_tier"] in {"low", "manual_review"}:
            rows.append(
                {
                    "item_id": stable_id("mr", ["low_confidence", row["observation_id"]]),
                    "issue_type": "low_confidence_source",
                    "indicator_id": row["indicator_id"],
                    "country_iso3": row["country_iso3"],
                    "year": row["year"],
                    "source_id": row["source_id"],
                    "source_file_path": row["source_file_path"],
                    "value_raw": row["value_raw"],
                    "value_numeric": row["value_numeric"],
                    "unit": row["unit"],
                    "reason_for_review": "Observation is low confidence or requires manual review.",
                    "recommended_action": "Verify source and method before using as a headline value.",
                    "status": "open",
                    "reviewer_note": "",
                }
            )
    for source_id in sorted(set(all_obs["source_id"])):
        if source_id not in sources:
            rows.append(
                {
                    "item_id": stable_id("mr", ["missing_source_metadata", source_id]),
                    "issue_type": "missing_source_metadata",
                    "indicator_id": "",
                    "country_iso3": "",
                    "year": "",
                    "source_id": source_id,
                    "source_file_path": "",
                    "value_raw": "",
                    "value_numeric": "",
                    "unit": "",
                    "reason_for_review": "Source appeared in data but not in source registry.",
                    "recommended_action": "Add source metadata to source registry.",
                    "status": "open",
                    "reviewer_note": "",
                }
            )
    return pd.DataFrame(rows)


def normalization_log(input_counts: dict[str, int], all_obs: pd.DataFrame, exact_removed: pd.DataFrame, canonical: pd.DataFrame, timeseries: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "step": "input_read",
            "detail": "Read existing silver observations and previous South Korea AI Index/OECD consolidated CSV.",
            "rows_affected": sum(input_counts.values()),
            "notes": json.dumps(input_counts, sort_keys=True),
        },
        {
            "step": "country_normalization",
            "detail": "Mapped country variants to KOR, USA, CHN, or UNKNOWN; North Korea/DPRK excluded from South Korea mapping.",
            "rows_affected": len(all_obs),
            "notes": "",
        },
        {
            "step": "period_normalization",
            "detail": "Created period_type, year, period_start, period_end, and period_label for annual, quarterly, monthly, and event-style dates.",
            "rows_affected": len(all_obs),
            "notes": "",
        },
        {
            "step": "unit_normalization",
            "detail": "Standardized common units including percent, count, PFLOP/s, OP/s, H100e, MW, KRW, USD, USD_billion, ranks, and indexes.",
            "rows_affected": len(all_obs),
            "notes": "Currency values were not converted between KRW and USD.",
        },
        {
            "step": "exact_duplicate_removal",
            "detail": "Removed exact duplicates by indicator/country/period/value/unit/source.",
            "rows_affected": len(exact_removed),
            "notes": "Removed rows are preserved in duplicates_removed.csv.",
        },
        {
            "step": "canonical_selection",
            "detail": "Selected one canonical row per indicator/country/period/unit using source hierarchy, confidence, indicator type, and recency.",
            "rows_affected": len(canonical),
            "notes": "",
        },
        {
            "step": "timeseries_filter",
            "detail": "Kept numeric rows with period_start and confidence above low/manual_review for time-series table.",
            "rows_affected": len(timeseries),
            "notes": "",
        },
    ]
    return pd.DataFrame(rows)


def write_report(
    *,
    inventory: pd.DataFrame,
    input_counts: dict[str, int],
    all_obs: pd.DataFrame,
    canonical: pd.DataFrame,
    timeseries: pd.DataFrame,
    exact_removed: pd.DataFrame,
    competing_review: pd.DataFrame,
    review: pd.DataFrame,
    coverage: pd.DataFrame,
    skipped: list[str],
) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORTS_DIR / "DATA_CONSOLIDATION_REPORT.md"
    indicators_kor = canonical[canonical["country_iso3"] == "KOR"]["indicator_id"].nunique()
    indicators_usa = canonical[canonical["country_iso3"] == "USA"]["indicator_id"].nunique()
    indicators_chn = canonical[canonical["country_iso3"] == "CHN"]["indicator_id"].nunique()
    complete = coverage[coverage["comparison_status"] == "complete_kor_usa_chn"]
    if review.empty:
        review_summary = "No manual review items."
    else:
        review_summary = "\n".join(
            f"- {issue_type}: {count:,}"
            for issue_type, count in review["issue_type"].value_counts().items()
        )
    lines = [
        "# Data Consolidation Report",
        "",
        "## 1. Executive summary",
        f"Created a source-governed v0.1 consolidated dataset for the South Korea AI industry dashboard with {len(canonical):,} canonical observations and {len(timeseries):,} time-series-ready rows.",
        "",
        "## 2. Input files discovered",
        f"{len(inventory):,} input files were discovered by `scripts/inventory_data_files.py`.",
        "",
        "## 3. Datasets successfully read",
        "\n".join(f"- {name}: {count:,} rows" for name, count in input_counts.items() if count),
        "",
        "## 4. Datasets skipped and why",
        "\n".join(f"- {item}" for item in skipped) if skipped else "- None in the consolidation pass. Some raw HTML/JSON files are inventoried but not parsed into observations unless already extracted by the silver pipeline.",
        "",
        "## 5. Number of raw observations found",
        f"{sum(input_counts.values()):,}",
        "",
        "## 6. Number of cleaned observations created",
        f"{len(all_obs):,}",
        "",
        "## 7. Number of canonical observations",
        f"{len(canonical):,}",
        "",
        "## 8. Number of time-series-ready observations",
        f"{len(timeseries):,}",
        "",
        "## 9. Number of duplicates removed",
        f"{len(exact_removed):,}",
        "",
        "## 10. Number of competing duplicates",
        f"{len(competing_review):,}",
        "",
        "## 11. Normalization actions taken",
        "- Country names normalized to ISO3 for KOR, USA, and CHN; North Korea/DPRK values are not treated as South Korea.",
        "- Period fields normalized for annual, quarterly, monthly, and event-style dates.",
        "- Percent values standardized to percent units; decimal shares were converted where safe.",
        "- Currency values were not converted between KRW and USD without an exchange-rate source.",
        "- Exact duplicates were removed and logged; competing values were preserved and canonicalized.",
        "",
        "## 12. Indicators with Korea data",
        f"{indicators_kor:,}",
        "",
        "## 13. Indicators with US data",
        f"{indicators_usa:,}",
        "",
        "## 14. Indicators with China data",
        f"{indicators_chn:,}",
        "",
        "## 15. KOR/USA/CHN comparison coverage",
        f"- Complete KOR/USA/CHN indicators: {len(complete):,}",
        f"- Partial comparison indicators: {(coverage['comparison_status'] == 'partial_comparison').sum():,}",
        f"- Korea-only indicators: {(coverage['comparison_status'] == 'korea_only').sum():,}",
        "",
        "## 16. Manual review queue summary",
        review_summary,
        "",
        "## 17. Known limitations",
        "- Raw HTML/text sources are treated as evidence and inventoried; only previously extracted observations and structured consolidated inputs are mapped into the master observation table.",
        "- Market estimates, company announcements, official targets, and observed metrics are preserved as distinct observations and should not be averaged.",
        "- Some AI Index public-data rows have source-specific indicator IDs to preserve chart provenance.",
        "- Source publication dates are sparse where the original local source did not include them.",
        "",
        "## 18. Recommended next cleanup steps",
        "- Review duplicate-conflict items before using headline values.",
        "- Add exact table extraction for raw HTML sources that currently only produced manual review items.",
        "- Decide whether AI Index source-specific rows should be remapped into a smaller curated indicator taxonomy for v0.2.",
        "- Add explicit currency conversion tables only if cross-currency comparison is required.",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    for path in [CONSOLIDATED_DIR, REPORTS_DIR, MANUAL_REVIEW_DIR, DOCS_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    if not RAW_FILE_INVENTORY.exists():
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "inventory_data_files.py")], check=True)

    inventory = pd.read_csv(RAW_FILE_INVENTORY, dtype=str, keep_default_na=False) if RAW_FILE_INVENTORY.exists() else pd.DataFrame()
    sources = load_sources()
    catalog = load_catalog()
    skipped: list[str] = []

    silver_records = read_silver_observations(sources, catalog)
    ai_index_records = read_existing_ai_index_csv(sources)
    input_counts = {
        "silver_observations": len(silver_records),
        "south_korea_ai_index_dashboard_data": len(ai_index_records),
    }
    if not SILVER_OBSERVATIONS.exists():
        skipped.append(f"{SILVER_OBSERVATIONS}: missing")
    if not AI_INDEX_EXISTING.exists():
        skipped.append(f"{AI_INDEX_EXISTING}: missing")

    all_records = silver_records + ai_index_records
    all_raw = pd.DataFrame(all_records, columns=OBS_COLUMNS)
    all_raw = all_raw.fillna("")

    exact_mask = all_raw.duplicated(subset=exact_duplicate_columns(), keep="first")
    exact_removed = all_raw[exact_mask].copy()
    all_deduped = all_raw[~exact_mask].copy()
    all_with_flags, competing_review = select_canonical(all_deduped)
    canonical = all_with_flags[all_with_flags["is_canonical"]].copy()
    canonical["is_canonical"] = True
    timeseries = make_timeseries(canonical)
    sources_table = make_sources_table(sources, all_with_flags, inventory)
    indicators = make_indicators_table(all_with_flags, catalog)
    coverage = make_comparison_coverage(canonical, indicators)
    review_existing = make_existing_review_queue(sources)
    review_generated = generated_review_items(all_with_flags, sources)
    review = pd.concat([review_existing, review_generated, competing_review], ignore_index=True)
    if not review.empty:
        review = review.drop_duplicates(subset=["item_id"], keep="first")

    log = normalization_log(input_counts, all_with_flags, exact_removed, canonical, timeseries)

    all_with_flags.to_csv(CONSOLIDATED_DIR / "master_observations_all.csv", index=False, encoding="utf-8-sig")
    canonical.to_csv(CONSOLIDATED_DIR / "master_observations_canonical.csv", index=False, encoding="utf-8-sig")
    timeseries.to_csv(CONSOLIDATED_DIR / "master_observations_timeseries.csv", index=False, encoding="utf-8-sig")
    sources_table.to_csv(CONSOLIDATED_DIR / "master_sources.csv", index=False, encoding="utf-8-sig")
    indicators.to_csv(CONSOLIDATED_DIR / "master_indicators.csv", index=False, encoding="utf-8-sig")
    coverage.to_csv(CONSOLIDATED_DIR / "comparison_coverage.csv", index=False, encoding="utf-8-sig")
    exact_removed.to_csv(CONSOLIDATED_DIR / "duplicates_removed.csv", index=False, encoding="utf-8-sig")
    log.to_csv(CONSOLIDATED_DIR / "normalization_log.csv", index=False, encoding="utf-8-sig")
    review.to_csv(MANUAL_REVIEW_DIR / "data_quality_review_queue.csv", index=False, encoding="utf-8-sig")

    write_report(
        inventory=inventory,
        input_counts=input_counts,
        all_obs=all_with_flags,
        canonical=canonical,
        timeseries=timeseries,
        exact_removed=exact_removed,
        competing_review=competing_review,
        review=review,
        coverage=coverage,
        skipped=skipped,
    )

    print(f"Files successfully read: {sum(1 for count in input_counts.values() if count)}")
    print(f"Observations created: {len(all_with_flags)}")
    print(f"Canonical observations created: {len(canonical)}")
    print(f"Time-series rows created: {len(timeseries)}")
    print(f"Duplicates removed: {len(exact_removed)}")
    print(f"Indicators with complete KOR/USA/CHN comparison: {(coverage['comparison_status'] == 'complete_kor_usa_chn').sum()}")
    print(f"Indicators needing manual review: {review['indicator_id'].nunique() if not review.empty else 0}")


if __name__ == "__main__":
    main()
