from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = PROJECT_ROOT / "app"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
CONSOLIDATED_DIR = DATA_DIR / "consolidated"
GOLD_DIR = DATA_DIR / "gold"
REPORTS_DIR = DATA_DIR / "reports"
MANUAL_REVIEW_DIR = DATA_DIR / "manual_review"
SOURCES_DIR = PROJECT_ROOT / "sources"
DOCS_DIR = PROJECT_ROOT / "docs"


def ensure_dirs() -> None:
    for path in [
        RAW_DIR,
        BRONZE_DIR,
        SILVER_DIR,
        CONSOLIDATED_DIR,
        GOLD_DIR,
        REPORTS_DIR,
        MANUAL_REVIEW_DIR,
        SOURCES_DIR,
        DOCS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
