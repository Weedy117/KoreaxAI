from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONSOLIDATED_DIR = PROJECT_ROOT / "data" / "consolidated"
GOLD_DIR = PROJECT_ROOT / "data" / "gold"


def main() -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    canonical_path = CONSOLIDATED_DIR / "master_observations_canonical.csv"
    timeseries_path = CONSOLIDATED_DIR / "master_observations_timeseries.csv"
    sources_path = CONSOLIDATED_DIR / "master_sources.csv"
    indicators_path = CONSOLIDATED_DIR / "master_indicators.csv"
    coverage_path = CONSOLIDATED_DIR / "comparison_coverage.csv"

    required = [canonical_path, timeseries_path, sources_path, indicators_path, coverage_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing consolidated CSVs. Run `make consolidate` first:\n" + "\n".join(missing))

    canonical = pd.read_csv(canonical_path, dtype=str, keep_default_na=False)
    timeseries = pd.read_csv(timeseries_path, dtype=str, keep_default_na=False)
    sources = pd.read_csv(sources_path, dtype=str, keep_default_na=False)
    indicators = pd.read_csv(indicators_path, dtype=str, keep_default_na=False)
    coverage = pd.read_csv(coverage_path, dtype=str, keep_default_na=False)

    parquet_ok = True
    try:
        canonical.to_parquet(GOLD_DIR / "master_observations_canonical.parquet", index=False)
        timeseries.to_parquet(GOLD_DIR / "master_observations_timeseries.parquet", index=False)
    except Exception as exc:
        parquet_ok = False
        print(f"Parquet output skipped: {exc}")

    duckdb_ok = True
    try:
        import duckdb

        db_path = GOLD_DIR / "korea_ai_dashboard.duckdb"
        if db_path.exists():
            db_path.unlink()
        con = duckdb.connect(str(db_path))
        tables = {
            "master_observations_canonical": canonical,
            "master_observations_timeseries": timeseries,
            "master_sources": sources,
            "master_indicators": indicators,
            "comparison_coverage": coverage,
        }
        for name, df in tables.items():
            con.register(f"{name}_df", df)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}_df")
        con.close()
    except Exception as exc:
        duckdb_ok = False
        print(f"DuckDB output skipped: {exc}")

    print(f"Gold canonical rows: {len(canonical)}")
    print(f"Gold time-series rows: {len(timeseries)}")
    print(f"Parquet written: {parquet_ok}")
    print(f"DuckDB written: {duckdb_ok}")


if __name__ == "__main__":
    main()
