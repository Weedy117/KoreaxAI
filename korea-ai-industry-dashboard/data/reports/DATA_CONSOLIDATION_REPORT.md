# Data Consolidation Report

## 1. Executive summary
Created a source-governed v0.1 consolidated dataset for the South Korea AI industry dashboard with 713 canonical observations and 650 time-series-ready rows.

## 2. Input files discovered
110 input files were discovered by `scripts/inventory_data_files.py`.

## 3. Datasets successfully read
- silver_observations: 242 rows
- south_korea_ai_index_dashboard_data: 598 rows

## 4. Datasets skipped and why
- None in the consolidation pass. Some raw HTML/JSON files are inventoried but not parsed into observations unless already extracted by the silver pipeline.

## 5. Number of raw observations found
840

## 6. Number of cleaned observations created
836

## 7. Number of canonical observations
713

## 8. Number of time-series-ready observations
650

## 9. Number of duplicates removed
4

## 10. Number of competing duplicates
30

## 11. Normalization actions taken
- Country names normalized to ISO3 for KOR, USA, and CHN; North Korea/DPRK values are not treated as South Korea.
- Period fields normalized for annual, quarterly, monthly, and event-style dates.
- Percent values standardized to percent units; decimal shares were converted where safe.
- Currency values were not converted between KRW and USD without an exchange-rate source.
- Exact duplicates were removed and logged; competing values were preserved and canonicalized.

## 12. Indicators with Korea data
117

## 13. Indicators with US data
14

## 14. Indicators with China data
14

## 15. KOR/USA/CHN comparison coverage
- Complete KOR/USA/CHN indicators: 12
- Partial comparison indicators: 2
- Korea-only indicators: 105

## 16. Manual review queue summary
- duplicate_conflict: 30
- unclear_indicator_mapping: 27
- missing_value: 10
- ambiguous_unit: 10

## 17. Known limitations
- Raw HTML/text sources are treated as evidence and inventoried; only previously extracted observations and structured consolidated inputs are mapped into the master observation table.
- Market estimates, company announcements, official targets, and observed metrics are preserved as distinct observations and should not be averaged.
- Some AI Index public-data rows have source-specific indicator IDs to preserve chart provenance.
- Source publication dates are sparse where the original local source did not include them.

## 18. Recommended next cleanup steps
- Review duplicate-conflict items before using headline values.
- Add exact table extraction for raw HTML sources that currently only produced manual review items.
- Decide whether AI Index source-specific rows should be remapped into a smaller curated indicator taxonomy for v0.2.
- Add explicit currency conversion tables only if cross-currency comparison is required.