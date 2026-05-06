from __future__ import annotations

import pandas as pd

from .config import COUNTRIES, OBSERVATION_COLUMNS, VALID_INDICATOR_TYPES


def validate_observations(
    observations: pd.DataFrame,
    indicators: pd.DataFrame,
    sources: pd.DataFrame,
) -> list[str]:
    errors: list[str] = []
    missing_cols = [c for c in OBSERVATION_COLUMNS if c not in observations.columns]
    if missing_cols:
        errors.append(f"observations.csv missing columns: {', '.join(missing_cols)}")
        return errors

    valid_indicators = set(indicators["indicator_id"])
    valid_sources = set(sources["source_id"])

    bad_indicators = sorted(set(observations["indicator_id"].dropna()) - valid_indicators)
    if bad_indicators:
        errors.append(f"Unknown indicator_id values: {', '.join(bad_indicators)}")

    bad_sources = sorted(set(observations["source_id"].dropna()) - valid_sources)
    if bad_sources:
        errors.append(f"Unknown source_id values: {', '.join(bad_sources)}")

    bad_countries = sorted(set(observations["country_iso3"].dropna()) - set(COUNTRIES))
    if bad_countries:
        errors.append(f"Unknown country_iso3 values: {', '.join(bad_countries)}")

    bad_types = sorted(set(observations["indicator_type"].dropna()) - VALID_INDICATOR_TYPES)
    if bad_types:
        errors.append(f"Unknown indicator_type values: {', '.join(bad_types)}")

    value_as_num = pd.to_numeric(observations["value"], errors="coerce")
    value_missing = observations["value"].notna() & value_as_num.isna()
    if value_missing.any():
        errors.append("Some observations have nonnumeric values; store contextual facts in notes/manual review.")

    return errors


def coverage_table(indicators: pd.DataFrame, observations: pd.DataFrame, manual_review: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    manual_ids = set(manual_review.get("indicator_id", pd.Series(dtype=str)).dropna())
    for _, indicator in indicators.iterrows():
        iid = indicator["indicator_id"]
        obs = observations[observations["indicator_id"] == iid]
        countries = set(obs["country_iso3"].dropna()) if not obs.empty else set()
        has_kor = "KOR" in countries
        has_usa = "USA" in countries
        has_chn = "CHN" in countries
        if has_kor and has_usa and has_chn:
            status = "complete_kor_usa_chn"
        elif has_kor and len(countries) == 1:
            status = "korea_only"
        elif countries:
            status = "partial_comparison"
        else:
            status = "unavailable"
        latest_year = None
        if not obs.empty:
            years = pd.to_numeric(obs["year"], errors="coerce").dropna()
            latest_year = int(years.max()) if not years.empty else None
        rows.append(
            {
                "indicator_id": iid,
                "has_kor": has_kor,
                "has_usa": has_usa,
                "has_chn": has_chn,
                "comparison_status": status,
                "latest_year": latest_year,
                "confidence_tier": indicator.get("confidence_tier"),
                "needs_manual_review": iid in manual_ids or status == "unavailable",
            }
        )
    return pd.DataFrame(rows)
