from __future__ import annotations

COUNTRIES = {
    "KOR": "South Korea",
    "USA": "United States",
    "CHN": "China",
}

OBSERVATION_COLUMNS = [
    "observation_id",
    "indicator_id",
    "category",
    "country_iso3",
    "country_name",
    "year",
    "time_period",
    "value",
    "unit",
    "source_id",
    "source_url",
    "retrieved_at",
    "source_publication_date",
    "indicator_type",
    "confidence_tier",
    "uncertainty_note",
    "notes",
]

MANUAL_REVIEW_COLUMNS = [
    "item_id",
    "indicator_id",
    "source_id",
    "source_url",
    "claim_or_value_to_check",
    "issue_type",
    "reason_for_review",
    "status",
    "reviewer_note",
]

COLLECTION_STATUS_COLUMNS = [
    "indicator_id",
    "source_id",
    "attempted",
    "success",
    "latest_year_collected",
    "countries_collected",
    "raw_file_path",
    "silver_file_path",
    "error_or_limitation",
    "needs_manual_review",
]

VALID_INDICATOR_TYPES = {
    "observed_metric",
    "official_target",
    "estimate",
    "company_claim",
    "index_metric",
    "survey_metric",
    "manual_classification",
    "contextual_fact",
    "observed_company_metric",
    "missing",
}
