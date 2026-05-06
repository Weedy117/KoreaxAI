# Methodology

This v0.1 dashboard uses a conservative public-source pipeline.

The collector downloads source pages, CSVs, JSON, ZIPs, or spreadsheets into `data/raw/{source_id}/{YYYY-MM-DD}/` and writes a metadata JSON with source ID, URL, retrieval time, status code, file path, content type, and notes.

Only values that are clearly stated in the source text or machine-readable source files are written to `data/silver/observations.csv`. The Streamlit app reads only from `data/gold/` outputs created by `scripts/build_gold.py`.

OpenAlex publication counts use a first-pass works API query with concept `C154945302` (Artificial intelligence) and an authorship institution country filter for `KR`, `US`, and `CN`, for years 2020-2026. This is transparent and reproducible, but it is a proxy rather than a full bibliometric methodology.

UN Comtrade, when accessible, uses HS 8542 as a narrow first-pass semiconductor proxy. That does not represent the full semiconductor trade universe and should be expanded in later versions.

Official targets, company claims, estimates, survey metrics, and observed metrics are stored with separate `indicator_type` values. They should not be interpreted as interchangeable evidence.
