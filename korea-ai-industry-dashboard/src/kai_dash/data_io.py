from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .config import COLLECTION_STATUS_COLUMNS, MANUAL_REVIEW_COLUMNS, OBSERVATION_COLUMNS
from .paths import CONSOLIDATED_DIR, GOLD_DIR, MANUAL_REVIEW_DIR, REPORTS_DIR, SILVER_DIR, SOURCES_DIR


def read_yaml(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}")
    return data


def load_indicators() -> list[dict[str, Any]]:
    return read_yaml(SOURCES_DIR / "indicator_catalog.yaml")


def load_sources() -> list[dict[str, Any]]:
    return read_yaml(SOURCES_DIR / "source_registry.yaml")


def indicators_df() -> pd.DataFrame:
    return pd.DataFrame(load_indicators())


def sources_df() -> pd.DataFrame:
    return pd.DataFrame(load_sources())


def read_observations(path: Path | None = None) -> pd.DataFrame:
    path = path or SILVER_DIR / "observations.csv"
    if not path.exists():
        return pd.DataFrame(columns=OBSERVATION_COLUMNS)
    return pd.read_csv(path)


def read_manual_review(path: Path | None = None) -> pd.DataFrame:
    path = path or MANUAL_REVIEW_DIR / "data_quality_review_queue.csv"
    if not path.exists():
        path = REPORTS_DIR / "manual_review_queue.csv"
    if not path.exists():
        path = SILVER_DIR / "manual_review_queue.csv"
    if not path.exists():
        return pd.DataFrame(columns=MANUAL_REVIEW_COLUMNS)
    return pd.read_csv(path)


def read_collection_status(path: Path | None = None) -> pd.DataFrame:
    path = path or REPORTS_DIR / "collection_status.csv"
    if not path.exists():
        return pd.DataFrame(columns=COLLECTION_STATUS_COLUMNS)
    return pd.read_csv(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_gold_table(name: str) -> pd.DataFrame:
    path = GOLD_DIR / f"{name}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def load_consolidated_table(name: str) -> pd.DataFrame:
    parquet_path = GOLD_DIR / f"{name}.parquet"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    csv_path = CONSOLIDATED_DIR / f"{name}.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    return pd.DataFrame()


def load_dashboard_bundle() -> dict[str, pd.DataFrame]:
    return {
        "canonical": load_consolidated_table("master_observations_canonical"),
        "timeseries": load_consolidated_table("master_observations_timeseries"),
        "indicators": load_consolidated_table("master_indicators"),
        "sources": load_consolidated_table("master_sources"),
        "coverage": load_consolidated_table("comparison_coverage"),
        "review": read_manual_review(),
    }
