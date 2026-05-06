# South Korea AI Industry Snapshot v0.1

This project builds a first usable research dashboard for public indicators across South Korea's AI industry: compute, data centers, semiconductors, frontier models, research, startups, chaebols, funding, adoption, talent, public sector, governance context, defense, and social readiness.

It is not a complete country profile. The pipeline only plots verified collected values. Sources that are unavailable, blocked, ambiguous, or hard to parse are saved where possible and added to the manual review queue.

## Quickstart

Use Python 3.11+.

```bash
pip install -r requirements.txt
python scripts/create_indicator_workbook.py
python scripts/collect_data.py
python scripts/build_gold.py
streamlit run app/Home.py
```

The dashboard reads only from `data/gold/`.

## Key Outputs

- `docs/korea_ai_v01_indicator_plan.xlsx`
- `data/silver/observations.csv`
- `data/reports/collected_observations.csv`
- `data/reports/manual_review_queue.csv`
- `data/reports/collection_status.csv`
- `data/reports/data_coverage.csv`
- `data/gold/observations.parquet`
- `data/gold/korea_ai_dashboard.duckdb`

## Data Layers

- `data/raw/`: unedited downloaded source material plus metadata JSON.
- `data/bronze/`: lightly parsed source-specific tables.
- `data/silver/`: normalized observations.
- `data/gold/`: dashboard-ready Parquet and DuckDB files.

## Notes

Optional API keys can be set in `.env`. The project runs without paid APIs. OpenDART and UN Comtrade are conservative in v0.1 and push unclear results to manual review.
