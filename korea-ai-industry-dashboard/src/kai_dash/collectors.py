from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .config import COUNTRIES, MANUAL_REVIEW_COLUMNS, OBSERVATION_COLUMNS
from .data_io import load_indicators, load_sources, write_json
from .paths import BRONZE_DIR, MANUAL_REVIEW_DIR, RAW_DIR, REPORTS_DIR, SILVER_DIR, PROJECT_ROOT, ensure_dirs


SESSION_TIMEOUT = 30
COUNTRY_ALIASES = {
    "KOR": ["South Korea", "Republic of Korea", "Korea"],
    "USA": ["United States", "U.S.", "USA"],
    "CHN": ["China"],
}

SOURCE_URL_OVERRIDES = {
    "mss_venture": "https://www.mss.go.kr/site/eng/ex/bbs/View.do?bcIdx=1067804&cbIdx=244",
    "ifr_robotics_installations": "https://ifr.org/ifr-press-releases/news/global-robot-demand-in-factories-doubles-over-10-years",
}


@dataclass
class RawDownload:
    source_id: str
    url: str
    retrieved_at: str
    status_code: int | None
    file_path: Path | None
    content_type: str | None = None
    notes: str = ""


class CollectionState:
    def __init__(self, indicators: list[dict[str, Any]], sources: list[dict[str, Any]]) -> None:
        self.indicators = {row["indicator_id"]: row for row in indicators}
        self.sources = {row["source_id"]: row for row in sources}
        self.observations: list[dict[str, Any]] = []
        self.manual: list[dict[str, Any]] = []
        self.raw_files: dict[str, list[str]] = {}
        self.errors: dict[str, str] = {}

    def source_url(self, source_id: str) -> str:
        return self.sources[source_id]["url"]

    def indicator(self, indicator_id: str) -> dict[str, Any]:
        return self.indicators[indicator_id]

    def add_raw(self, source_id: str, path: Path | None) -> None:
        if path:
            self.raw_files.setdefault(source_id, []).append(str(path))

    def add_observation(
        self,
        indicator_id: str,
        country_iso3: str,
        year: int | None,
        value: float | int,
        source_id: str,
        source_url: str | None = None,
        time_period: str | None = None,
        source_publication_date: str | None = None,
        notes: str = "",
        indicator_type: str | None = None,
        confidence_tier: str | None = None,
        unit: str | None = None,
        retrieved_at: str | None = None,
    ) -> None:
        meta = self.indicator(indicator_id)
        source_url = source_url or self.source_url(source_id)
        year_part = "" if year is None else str(year)
        key = f"{indicator_id}|{country_iso3}|{year_part}|{value}|{source_id}|{notes}"
        observation_id = "obs_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:14]
        self.observations.append(
            {
                "observation_id": observation_id,
                "indicator_id": indicator_id,
                "category": meta.get("category"),
                "country_iso3": country_iso3,
                "country_name": COUNTRIES.get(country_iso3, country_iso3),
                "year": year,
                "time_period": time_period or (str(year) if year else ""),
                "value": value,
                "unit": unit or meta.get("unit"),
                "source_id": source_id,
                "source_url": source_url,
                "retrieved_at": retrieved_at or now_iso(),
                "source_publication_date": source_publication_date or "",
                "indicator_type": indicator_type or meta.get("indicator_type"),
                "confidence_tier": confidence_tier or meta.get("confidence_tier"),
                "uncertainty_note": meta.get("uncertainty_note"),
                "notes": notes,
            }
        )

    def add_manual(
        self,
        indicator_id: str,
        source_id: str,
        reason: str,
        issue_type: str = "manual_parse",
        claim_or_value_to_check: str = "",
        reviewer_note: str = "",
        source_url: str | None = None,
    ) -> None:
        item_id = "mr_" + hashlib.sha1(f"{indicator_id}|{source_id}|{reason}".encode("utf-8")).hexdigest()[:12]
        self.manual.append(
            {
                "item_id": item_id,
                "indicator_id": indicator_id,
                "source_id": source_id,
                "source_url": source_url or self.source_url(source_id),
                "claim_or_value_to_check": claim_or_value_to_check,
                "issue_type": issue_type,
                "reason_for_review": reason,
                "status": "open",
                "reviewer_note": reviewer_note,
            }
        )

    def build_collection_status(self) -> pd.DataFrame:
        obs = pd.DataFrame(self.observations)
        manual = pd.DataFrame(self.manual)
        rows: list[dict[str, Any]] = []
        for indicator_id, meta in self.indicators.items():
            source_id = meta.get("primary_source_id", "")
            obs_i = obs[obs["indicator_id"] == indicator_id] if not obs.empty else pd.DataFrame()
            manual_i = manual[manual["indicator_id"] == indicator_id] if not manual.empty else pd.DataFrame()
            raw_paths = self.raw_files.get(source_id, [])
            years = pd.to_numeric(obs_i.get("year", pd.Series(dtype=float)), errors="coerce").dropna()
            rows.append(
                {
                    "indicator_id": indicator_id,
                    "source_id": source_id,
                    "attempted": bool(raw_paths or not manual_i.empty or not obs_i.empty),
                    "success": not obs_i.empty,
                    "latest_year_collected": int(years.max()) if not years.empty else "",
                    "countries_collected": ",".join(sorted(obs_i["country_iso3"].dropna().unique())) if not obs_i.empty else "",
                    "raw_file_path": ";".join(raw_paths),
                    "silver_file_path": str(SILVER_DIR / "observations.csv") if not obs_i.empty else "",
                    "error_or_limitation": self.errors.get(source_id, "") or ("; ".join(manual_i["reason_for_review"].head(3)) if not manual_i.empty else ""),
                    "needs_manual_review": not manual_i.empty or obs_i.empty,
                }
            )
        return pd.DataFrame(rows)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def clean_text(html_or_text: str) -> str:
    soup = BeautifulSoup(html_or_text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def number(value: str) -> float:
    return float(value.replace(",", "").replace("%", "").strip())


def krw_amount(value: str, magnitude: str) -> float:
    multiplier = {
        "trillion": 1_000_000_000_000,
        "billion": 1_000_000_000,
        "million": 1_000_000,
    }[magnitude.lower()]
    return number(value) * multiplier


def file_ext(content_type: str | None, url: str) -> str:
    lowered = (content_type or "").lower()
    if "pdf" in lowered or url.lower().endswith(".pdf"):
        return ".pdf"
    if "json" in lowered or url.lower().endswith(".json"):
        return ".json"
    if "csv" in lowered or url.lower().endswith(".csv"):
        return ".csv"
    if "spreadsheet" in lowered or url.lower().endswith(".xlsx"):
        return ".xlsx"
    if "zip" in lowered or url.lower().endswith(".zip"):
        return ".zip"
    if "xml" in lowered or url.lower().endswith(".xml"):
        return ".xml"
    return ".html"


def safe_name(source_id: str, suffix: str = "") -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{source_id}{suffix}")


def fetch_url(
    session: requests.Session,
    source_id: str,
    url: str,
    user_agent: str,
    suffix: str = "",
    extra_headers: dict[str, str] | None = None,
) -> RawDownload:
    retrieved_at = now_iso()
    target_dir = RAW_DIR / source_id / today_str()
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        headers = {"User-Agent": user_agent}
        if extra_headers:
            headers.update(extra_headers)
        response = session.get(url, headers=headers, timeout=SESSION_TIMEOUT)
        ext = file_ext(response.headers.get("content-type"), url)
        raw_path = target_dir / f"{safe_name(source_id, suffix)}{ext}"
        raw_path.write_bytes(response.content)
        metadata = {
            "source_id": source_id,
            "url": url,
            "retrieved_at": retrieved_at,
            "status_code": response.status_code,
            "file_path": str(raw_path),
            "content_type": response.headers.get("content-type"),
            "notes": "",
        }
        write_json(target_dir / f"{safe_name(source_id, suffix)}.metadata.json", metadata)
        return RawDownload(source_id, url, retrieved_at, response.status_code, raw_path, response.headers.get("content-type"))
    except Exception as exc:
        metadata = {
            "source_id": source_id,
            "url": url,
            "retrieved_at": retrieved_at,
            "status_code": None,
            "file_path": "",
            "notes": f"Download failed: {exc}",
        }
        write_json(target_dir / f"{safe_name(source_id, suffix)}.metadata.json", metadata)
        return RawDownload(source_id, url, retrieved_at, None, None, None, f"Download failed: {exc}")


def raw_text(download: RawDownload) -> str:
    if not download.file_path or not download.file_path.exists():
        return ""
    try:
        return clean_text(download.file_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return ""


def parse_msit_work_plan(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    if not text:
        state.add_manual("national_gpu_target_2026", "msit_2026_work_plan", "No readable MSIT work-plan text.")
        return

    m = re.search(r"AI Budget:\s*KRW\s*[\d.]+\s*trillion\s*\(2025\)\s*(?:->|\u2192)\s*KRW\s*([\d.]+)\s*trillion\s*\(2026\)", text)
    if m:
        state.add_observation("ai_budget_2026_krw", "KOR", 2026, krw_amount(m.group(1), "trillion"), "msit_2026_work_plan", download.url, notes="Official 2026 AI budget target from MSIT work plan.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("ai_budget_2026_krw", "msit_2026_work_plan", "Could not extract the 2026 AI budget target with a conservative regex.")

    m = re.search(r"cumulative total of\s*([\d,]+)\s*GPUs\s*will be secured by 2026", text, re.I)
    if m:
        state.add_observation("national_gpu_target_2026", "KOR", 2026, int(number(m.group(1))), "msit_2026_work_plan", download.url, notes="Official cumulative GPU target; includes government procurement and Supercomputer No. 6 components.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("national_gpu_target_2026", "msit_2026_work_plan", "Could not extract cumulative national GPU target.")

    if "foundation model project" in text.lower():
        state.add_manual("k_ai_foundation_model_team_count", "msit_2026_work_plan", "Work-plan page confirms a foundation-model project but does not expose a clear team count.")
    state.add_manual("k_ai_consortium_actor_type_share", "msit_2026_work_plan", "Actor-type composition requires manual classification of official K-AI teams.")
    state.add_manual("public_sector_ai_program_count", "msit_2026_work_plan", "Named public-sector AI program count requires manual coding.")


def parse_msit_gpu_procurement(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    m = re.search(r"secure\s*(?:a total of\s*)?([\d,]+)\s*(?:advanced\s*)?GPUs", text, re.I)
    if m:
        state.add_observation("public_gpu_procurement_count", "KOR", 2025, int(number(m.group(1))), "msit_gpu_procurement", download.url, notes="Total GPUs to be secured under public-private GPU procurement.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("public_gpu_procurement_count", "msit_gpu_procurement", "Could not extract total public GPU procurement count.")

    m = re.search(r"KRW\s*([\d.]+)\s*trillion", text, re.I)
    if m:
        state.add_observation("public_gpu_procurement_budget_krw", "KOR", 2025, krw_amount(m.group(1), "trillion"), "msit_gpu_procurement", download.url, notes="First supplementary budget amount for GPU procurement.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("public_gpu_procurement_budget_krw", "msit_gpu_procurement", "Could not extract procurement budget.")


def parse_kisti(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    m = re.search(r"equipped with\s*([\d,]+)\s*of NVIDIA", text, re.I)
    if m:
        state.add_observation("kisti6_gpu_count", "KOR", 2026, int(number(m.group(1))), "kisti_hangang", download.url, notes="KISTI-6/HANGANG stated GPU count.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("kisti6_gpu_count", "kisti_hangang", "Could not extract KISTI-6 GPU count.")
    m = re.search(r"performance of approximately\s*([\d,.]+)\s*PFlop/s", text, re.I)
    if m:
        state.add_observation("kisti6_peak_pflops", "KOR", 2026, number(m.group(1)), "kisti_hangang", download.url, notes="Approximate stated computing performance.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("kisti6_peak_pflops", "kisti_hangang", "Could not extract KISTI-6 PFLOP/s value.")


def parse_ifr_density(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    patterns = {
        "KOR": r"Republic of Korea records[^.]*?([\d,]+)\s*robots per 10,000",
        "USA": r"United States ranks[^.]*?with\s*([\d,]+)\s*units per 10,000",
        "CHN": r"China ranks.*?It has\s*([\d,]+)\s*robots for every 10,000",
    }
    for iso3, pattern in patterns.items():
        m = re.search(pattern, text, re.I | re.S)
        if m:
            state.add_observation("robot_density_manufacturing", iso3, 2024, int(number(m.group(1))), "ifr_robotics", download.url, notes="IFR press-release value for robot density in manufacturing.", retrieved_at=download.retrieved_at)
    if not any(o["indicator_id"] == "robot_density_manufacturing" for o in state.observations):
        state.add_manual("robot_density_manufacturing", "ifr_robotics", "Could not extract IFR robot density values.")


def parse_ifr_installations(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    patterns = {
        "CHN": r"China is by far.*?([\d,]+)\s*industrial robots have been installed",
        "KOR": r"Republic of Korea installed\s*([\d,]+)\s*units in 2024",
        "USA": r"United States\s*,\s*the largest regional market.*?Robot installations were down[^.]*?to\s*([\d,]+)\s*units",
    }
    for iso3, pattern in patterns.items():
        m = re.search(pattern, text, re.I | re.S)
        if m:
            state.add_observation("industrial_robot_installations", iso3, 2024, int(number(m.group(1))), "ifr_robotics", download.url, notes="IFR press-release annual installation value.", retrieved_at=download.retrieved_at)
    if not any(o["indicator_id"] == "industrial_robot_installations" for o in state.observations):
        state.add_manual("industrial_robot_installations", "ifr_robotics", "Could not extract IFR installation values.")


def parse_bok(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    values = [
        ("worker_genai_any_use_pct", "63.5%", 63.5, "Share of workers using GenAI in any capacity."),
        ("worker_genai_work_use_pct", "51.8%", 51.8, "Share using GenAI for work."),
        ("genai_time_saved_pct", "3.8%", 3.8, "Average work-time reduction from GenAI use."),
        ("genai_productivity_effect_pct", "1.0%", 1.0, "Estimated potential productivity effect."),
        ("physical_ai_exposure_pct", "11%", 11.0, "Current share exposed to physical AI/autonomous robots."),
        ("worker_positive_ai_society_pct", "48.1%", 48.1, "Workers expecting positive societal impact."),
        ("worker_retraining_intention_pct", "33.4%", 33.4, "Workers preparing through education/training."),
    ]
    for indicator_id, needle, value, note in values:
        if needle in text:
            state.add_observation(indicator_id, "KOR", 2025, value, "bok_genai", download.url, notes=note, retrieved_at=download.retrieved_at)
        else:
            state.add_manual(indicator_id, "bok_genai", f"Expected value marker {needle} was not found in BOK page text.")


def parse_mss_venture(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    if "KRW 6.8 trillion" in text:
        state.add_observation("total_venture_investment_krw", "KOR", 2025, krw_amount("6.8", "trillion"), "mss_venture", download.url, notes="Total Korean venture investment in 2025 from MSS release.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("total_venture_investment_krw", "mss_venture", "Could not extract total venture investment.")
    if "KRW 5.2 trillion" in text:
        state.add_observation("new_industry_venture_investment_krw", "KOR", 2025, krw_amount("5.2", "trillion"), "mss_venture", download.url, notes="Investment in twelve designated new industry sectors.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("new_industry_venture_investment_krw", "mss_venture", "Could not extract new-industry venture investment.")
    state.add_manual("ai_models_infrastructure_investment_krw", "mss_venture", "MSS release names AI models and infrastructure as a sector but the HTML text did not expose a clear sector-specific investment value.", source_url=download.url)
    state.add_manual("ai_unicorn_count", "mss_venture", "AI or AI-relevant unicorn count requires manual valuation review.", source_url=download.url)
    state.add_manual("domestic_ai_chip_unicorn_count", "mss_venture", "AI-chip unicorn/startup classification requires manual review.", source_url=download.url)


def parse_mss_smart(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    if "approximately 450 projects" in text or "450 projects" in text:
        state.add_observation("smart_manufacturing_ai_projects_2026", "KOR", 2026, 450, "mss_smart_manufacturing", download.url, notes="Approximate total support projects: autonomous factories, AI-specialized smart factories, and AI tracks.", retrieved_at=download.retrieved_at)
    else:
        pieces = re.findall(r"\((\d+)\s*projects\)", text, re.I)
        if pieces:
            state.add_observation("smart_manufacturing_ai_projects_2026", "KOR", 2026, sum(map(int, pieces)), "mss_smart_manufacturing", download.url, notes="Sum of clearly stated project-category counts.", retrieved_at=download.retrieved_at)
        else:
            state.add_manual("smart_manufacturing_ai_projects_2026", "mss_smart_manufacturing", "Could not extract project count.")


def parse_nvidia(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    m = re.search(r"Adding Over\s*([\d,]+)\s*NVIDIA GPUs", text, re.I)
    if not m:
        m = re.search(r"over a quarter-million NVIDIA GPUs", text, re.I)
    if m:
        value = int(number(m.group(1))) if m.groups() else 250_000
        state.add_observation("announced_gpu_deployments_count", "KOR", 2025, value, "nvidia_korea_ai_infrastructure", download.url, notes="Company claim; wording says over this count.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("announced_gpu_deployments_count", "nvidia_korea_ai_infrastructure", "Could not extract NVIDIA announced GPU deployment count.")


def parse_pew(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    m = re.search(r"as few as\s*(\d+)%\s*in South Korea", text, re.I)
    if m:
        state.add_observation("ai_concern_more_than_excited_pct", "KOR", 2025, int(m.group(1)), "pew_ai_views", download.url, notes="Share mainly concerned about AI in Pew report text.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("ai_concern_more_than_excited_pct", "pew_ai_views", "Could not extract South Korea concern percentage.")
    state.add_manual("ai_awareness_pct", "pew_ai_views", "Awareness values likely require Pew topline/survey data extraction.", source_url=download.url)


def parse_tradegov_defense(state: CollectionState, download: RawDownload) -> None:
    text = raw_text(download)
    values = [29.6, 13.6, 6.9]
    if all(f"{v} billion won" in text for v in values):
        state.add_observation("defense_unmanned_system_procurement_budget", "KOR", 2025, sum(values) * 1_000_000_000, "tradegov_unmanned_defense", download.url, notes="Aggregate of clearly stated anti-material strike UAV, reconnaissance UAV, and ground reconnaissance robot budgets.", retrieved_at=download.retrieved_at)
    else:
        state.add_manual("defense_unmanned_system_procurement_budget", "tradegov_unmanned_defense", "Could not extract all clearly stated unmanned-system budget components.")


def country_from_text(value: Any) -> list[str]:
    text = "" if pd.isna(value) else str(value)
    out = []
    for iso3, aliases in COUNTRY_ALIASES.items():
        if any(re.search(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", text, re.I) for alias in aliases):
            out.append(iso3)
    return out


def parse_year(value: Any) -> int | None:
    if pd.isna(value):
        return None
    m = re.search(r"(19|20)\d{2}", str(value))
    return int(m.group(0)) if m else None


def find_col(cols: Iterable[str], candidates: list[str], contains: list[str] | None = None) -> str | None:
    cols = list(cols)
    lowered = {c.lower().strip(): c for c in cols}
    for c in candidates:
        if c.lower().strip() in lowered:
            return lowered[c.lower().strip()]
    if contains:
        for c in cols:
            low = c.lower()
            if all(part.lower() in low for part in contains):
                return c
    return None


def collect_epoch_models(state: CollectionState, session: requests.Session, user_agent: str) -> None:
    source_id = "epoch_ai_models"
    datasets = {
        "notable_ai_models_count": ("https://epoch.ai/data/notable_ai_models.csv", "_notable"),
        "frontier_ai_models_count": ("https://epoch.ai/data/frontier_ai_models.csv", "_frontier"),
        "large_scale_models_count": ("https://epoch.ai/data/large_scale_ai_models.csv", "_large_scale"),
        "max_domestic_model_training_compute_flop": ("https://epoch.ai/data/all_ai_models.csv", "_all"),
    }
    any_success = False
    for indicator_id, (url, suffix) in datasets.items():
        dl = fetch_url(session, source_id, url, user_agent, suffix)
        state.add_raw(source_id, dl.file_path)
        if not dl.file_path or dl.status_code != 200:
            state.add_manual(indicator_id, source_id, f"Epoch CSV was unavailable at {url}.", source_url=url)
            continue
        try:
            df = pd.read_csv(dl.file_path)
            (BRONZE_DIR / source_id).mkdir(parents=True, exist_ok=True)
            df.to_parquet(BRONZE_DIR / source_id / f"{indicator_id}.parquet", index=False)
            country_col = find_col(df.columns, ["Country", "Countries", "Organization country", "Organization(s) country"], ["country"])
            date_col = find_col(df.columns, ["Publication date", "Publication Date", "Release date", "Date"], ["date"])
            compute_col = find_col(df.columns, ["Training compute (FLOP)", "Training compute"], ["training", "compute"])
            if not country_col:
                state.add_manual(indicator_id, source_id, "Epoch model CSV did not expose a recognizable country column.", source_url=url)
                continue
            if indicator_id == "max_domestic_model_training_compute_flop":
                if not compute_col:
                    state.add_manual(indicator_id, source_id, "No recognizable training-compute column in all-models CSV.", source_url=url)
                    continue
                df["_compute"] = pd.to_numeric(df[compute_col], errors="coerce")
                df["_year"] = df[date_col].map(parse_year) if date_col else None
                for iso3 in COUNTRIES:
                    mask = df[country_col].map(lambda x: iso3 in country_from_text(x))
                    sub = df[mask & df["_compute"].notna()]
                    if not sub.empty:
                        row = sub.sort_values("_compute").iloc[-1]
                        state.add_observation(indicator_id, iso3, int(row["_year"]) if pd.notna(row["_year"]) else None, float(row["_compute"]), source_id, url, notes=f"Max training compute from Epoch all-models CSV using country column '{country_col}'.", retrieved_at=dl.retrieved_at)
                        any_success = True
                continue
            if not date_col:
                state.add_manual(indicator_id, source_id, "Epoch model CSV did not expose a recognizable date column.", source_url=url)
                continue
            rows: list[dict[str, Any]] = []
            for _, row in df.iterrows():
                year = parse_year(row.get(date_col))
                if not year:
                    continue
                for iso3 in country_from_text(row.get(country_col)):
                    rows.append({"country_iso3": iso3, "year": year})
            counts = pd.DataFrame(rows).groupby(["country_iso3", "year"]).size().reset_index(name="count") if rows else pd.DataFrame()
            for _, row in counts.iterrows():
                state.add_observation(indicator_id, row["country_iso3"], int(row["year"]), int(row["count"]), source_id, url, notes=f"Count from Epoch CSV using country column '{country_col}' and date column '{date_col}'.", retrieved_at=dl.retrieved_at)
                any_success = True
        except Exception as exc:
            state.add_manual(indicator_id, source_id, f"Could not parse Epoch model CSV: {exc}", source_url=url)
    if not any_success:
        state.errors[source_id] = "No Epoch AI model observations collected."


def collect_epoch_gpu_clusters(state: CollectionState, session: requests.Session, user_agent: str) -> None:
    source_id = "epoch_gpu_clusters"
    urls = [
        "https://epoch.ai/data/gpu_clusters.csv",
        "https://epoch.ai/data/gpu-clusters.csv",
        "https://epoch.ai/data/ai_supercomputers.csv",
    ]
    for url in urls:
        dl = fetch_url(session, source_id, url, user_agent, "_clusters")
        state.add_raw(source_id, dl.file_path)
        if dl.file_path and dl.status_code == 200 and dl.file_path.suffix == ".csv":
            try:
                df = pd.read_csv(dl.file_path)
                country_col = find_col(df.columns, ["Country", "Location country", "Country/Region"], ["country"])
                ops_col = find_col(df.columns, ["16-bit operations", "16 bit operations", "FP16"], ["16"])
                if not country_col:
                    raise ValueError("No country column")
                rows = []
                for _, row in df.iterrows():
                    raw_ops = pd.to_numeric(row.get(ops_col), errors="coerce") if ops_col else None
                    if ops_col and raw_ops is not None and pd.notna(raw_ops) and "log" in ops_col.lower():
                        raw_ops = 10 ** float(raw_ops)
                    for iso3 in country_from_text(row.get(country_col)):
                        rows.append({"country_iso3": iso3, "ops": raw_ops})
                out = pd.DataFrame(rows)
                if not out.empty:
                    for iso3, sub in out.groupby("country_iso3"):
                        state.add_observation("known_ai_gpu_cluster_count", iso3, 2026, int(len(sub)), source_id, url, notes=f"Count from Epoch GPU clusters CSV using country column '{country_col}'.", retrieved_at=dl.retrieved_at)
                        if ops_col and sub["ops"].notna().any():
                            log_note = " Values converted from log scale before aggregation." if "log" in ops_col.lower() else ""
                            state.add_observation("known_ai_gpu_cluster_16bit_ops", iso3, 2026, float(sub["ops"].sum()), source_id, url, notes=f"Aggregate from Epoch GPU clusters CSV column '{ops_col}'.{log_note}", retrieved_at=dl.retrieved_at)
                    return
            except Exception as exc:
                state.add_manual("known_ai_gpu_cluster_count", source_id, f"Downloaded candidate GPU clusters CSV but parsing failed: {exc}", source_url=url)
    state.add_manual("known_ai_gpu_cluster_count", source_id, "No accessible Epoch GPU clusters CSV endpoint succeeded.")
    state.add_manual("known_ai_gpu_cluster_16bit_ops", source_id, "No accessible Epoch GPU clusters CSV endpoint succeeded or no 16-bit ops column found.")


def collect_epoch_chip_owners(state: CollectionState, session: requests.Session, user_agent: str) -> None:
    source_id = "epoch_ai_chip_owners"
    url = "https://epoch.ai/data/ai_chip_owners.zip"
    dl = fetch_url(session, source_id, url, user_agent, "_owners")
    state.add_raw(source_id, dl.file_path)
    if not dl.file_path or dl.status_code != 200:
        state.add_manual("h100e_compute_capacity_owned", source_id, "Epoch AI Chip Owners ZIP endpoint was unavailable; saved metadata for review.", source_url=url)
        return
    try:
        with zipfile.ZipFile(dl.file_path) as zf:
            names = zf.namelist()
            outdir = BRONZE_DIR / source_id
            outdir.mkdir(parents=True, exist_ok=True)
            for name in names:
                if name.lower().endswith(".csv"):
                    target = outdir / Path(name).name
                    target.write_bytes(zf.read(name))
        state.add_manual("h100e_compute_capacity_owned", source_id, "ZIP downloaded and extracted, but owner-to-country/H100e mapping needs manual review before observation creation.", source_url=url)
    except Exception as exc:
        state.add_manual("h100e_compute_capacity_owned", source_id, f"Could not inspect Epoch AI Chip Owners ZIP: {exc}", source_url=url)


def collect_openalex(state: CollectionState, session: requests.Session, user_agent: str) -> None:
    source_id = "openalex"
    mailto = os.getenv("OPENALEX_EMAIL", "").strip()
    concept = "C154945302"  # OpenAlex concept: Artificial intelligence.
    for iso3, name in COUNTRIES.items():
        country_code = {"KOR": "KR", "USA": "US", "CHN": "CN"}[iso3]
        for year in range(2020, 2027):
            url = (
                "https://api.openalex.org/works"
                f"?filter=from_publication_date:{year}-01-01,to_publication_date:{year}-12-31,"
                f"authorships.institutions.country_code:{country_code},concepts.id:{concept}"
                "&per-page=1"
            )
            if mailto:
                url += f"&mailto={mailto}"
            dl = fetch_url(session, source_id, url, user_agent, f"_{iso3}_{year}")
            state.add_raw(source_id, dl.file_path)
            if not dl.file_path or dl.status_code != 200:
                state.add_manual("ai_research_publications_count", source_id, f"OpenAlex query failed for {iso3} {year}.", source_url=url)
                continue
            try:
                data = json.loads(dl.file_path.read_text(encoding="utf-8"))
                count = int(data.get("meta", {}).get("count", 0))
                state.add_observation("ai_research_publications_count", iso3, year, count, source_id, url, notes="OpenAlex first-pass count using concept C154945302 and authorship institution country filter.", retrieved_at=dl.retrieved_at)
            except Exception as exc:
                state.add_manual("ai_research_publications_count", source_id, f"OpenAlex JSON parse failed for {iso3} {year}: {exc}", source_url=url)
    state.add_manual("ai_research_citations_count", source_id, "Citations require a broader paginated aggregation; v0.1 collects publication counts only.")
    state.add_manual("ai_author_count_proxy", source_id, "Author-count proxy requires author deduplication; not collected in v0.1.")


def collect_top500(state: CollectionState, session: requests.Session, user_agent: str) -> None:
    source_id = "top500"
    page = fetch_url(session, source_id, state.source_url(source_id), user_agent, "_stats_page")
    state.add_raw(source_id, page.file_path)
    candidates = [
        "https://top500.org/lists/top500/2025/11/download/TOP500_202511.xlsx",
        "https://top500.org/lists/top500/2025/11/download/TOP500_202511.xls",
        "https://top500.org/lists/top500/2025/11/download/TOP500_202511.xml",
    ]
    for url in candidates:
        dl = fetch_url(session, source_id, url, user_agent, "_current_list")
        state.add_raw(source_id, dl.file_path)
        if not dl.file_path or dl.status_code != 200:
            continue
        try:
            if dl.file_path.suffix == ".xlsx":
                df = pd.read_excel(dl.file_path)
            elif dl.file_path.suffix == ".xml":
                df = pd.read_xml(dl.file_path)
            else:
                continue
            country_col = find_col(df.columns, ["Country", "Country/Region"], ["country"])
            rmax_col = find_col(df.columns, ["Rmax [TFlop/s]", "Rmax", "Rmax (PFlop/s)"], ["rmax"])
            if not country_col or not rmax_col:
                continue
            for iso3, aliases in COUNTRY_ALIASES.items():
                mask = df[country_col].astype(str).str.lower().apply(lambda x: any(a.lower() == x.strip() or a.lower() in x for a in aliases))
                sub = df[mask].copy()
                if sub.empty:
                    continue
                rmax = pd.to_numeric(sub[rmax_col], errors="coerce").sum()
                # TOP500 downloads are commonly in TFlop/s; HTML current list labels PFlop/s.
                unit_note = "Rmax column parsed from TOP500 downloadable list; if source column is TFlop/s, value converted to PFLOP/s."
                value = float(rmax / 1000.0) if rmax > 10_000 else float(rmax)
                state.add_observation("top500_system_count", iso3, 2025, int(len(sub)), source_id, url, notes="Count from TOP500 downloadable current list.", retrieved_at=dl.retrieved_at)
                state.add_observation("top500_total_rmax_pflops", iso3, 2025, value, source_id, url, notes=unit_note, retrieved_at=dl.retrieved_at)
            return
        except Exception:
            continue
    state.add_manual("top500_system_count", source_id, "Could not access or parse a TOP500 downloadable list in v0.1.")
    state.add_manual("top500_total_rmax_pflops", source_id, "Could not access or parse a TOP500 downloadable list in v0.1.")


def collect_stanford_local(state: CollectionState) -> None:
    source_id = "stanford_ai_index"
    candidates = list(PROJECT_ROOT.parent.glob("PUBLIC DATA_*/*AI INDEX REPORT"))
    if not candidates:
        for indicator_id in ["private_ai_investment_usd", "newly_funded_ai_companies_count", "ai_patents_per_capita"]:
            state.add_manual(indicator_id, source_id, "No local Stanford AI Index public-data bundle found; online report/data not parsed in v0.1.")
        return
    base = candidates[0]
    raw_dir = RAW_DIR / source_id / today_str()
    raw_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "ai_patents_per_capita": base / "1. Research and Development" / "Data" / "fig_1.7.4.csv",
        "private_ai_investment_usd": base / "4. Economy" / "Data" / "fig_4.2.11.csv",
        "newly_funded_ai_companies_count": base / "4. Economy" / "Data" / "fig_4.2.14.csv",
    }
    for indicator_id, src in files.items():
        if not src.exists():
            state.add_manual(indicator_id, source_id, f"Expected local Stanford figure file not found: {src.name}")
            continue
        dest = raw_dir / src.name
        shutil.copy2(src, dest)
        state.add_raw(source_id, dest)
        write_json(
            raw_dir / f"{src.stem}.metadata.json",
            {
                "source_id": source_id,
                "url": state.source_url(source_id),
                "retrieved_at": now_iso(),
                "status_code": None,
                "file_path": str(dest),
                "notes": f"Copied from local public-data bundle: {src}",
            },
        )
        try:
            df = pd.read_csv(dest)
            if indicator_id == "ai_patents_per_capita":
                val_col = df.columns[0]
                for _, row in df.iterrows():
                    for iso3 in country_from_text(row.get("Country")):
                        state.add_observation(indicator_id, iso3, 2024, float(row[val_col]), source_id, state.source_url(source_id), notes=f"Stanford AI Index local figure {src.name}.", indicator_type="index_metric")
            elif indicator_id == "private_ai_investment_usd":
                for _, row in df.iterrows():
                    for iso3 in country_from_text(row.get("Label")):
                        year = parse_year(row.get("Year"))
                        if year:
                            state.add_observation(indicator_id, iso3, year, float(row["Total investment (in billions of US dollars)"]) * 1_000_000_000, source_id, state.source_url(source_id), notes=f"Stanford AI Index local figure {src.name}; billions converted to USD.", indicator_type="index_metric")
                state.add_manual(indicator_id, source_id, "Local annual private-investment figure does not include South Korea rows; Korea value needs source review.")
            elif indicator_id == "newly_funded_ai_companies_count":
                for _, row in df.iterrows():
                    for iso3 in country_from_text(row.get("Label")):
                        year = parse_year(row.get("Year"))
                        if year:
                            state.add_observation(indicator_id, iso3, year, int(row["Number of companies"]), source_id, state.source_url(source_id), notes=f"Stanford AI Index local figure {src.name}.", indicator_type="index_metric")
                state.add_manual(indicator_id, source_id, "Local annual newly-funded-companies figure does not include South Korea rows; Korea value needs source review.")
        except Exception as exc:
            state.add_manual(indicator_id, source_id, f"Could not parse local Stanford figure data: {exc}")


def collect_un_comtrade(state: CollectionState, session: requests.Session, user_agent: str) -> None:
    api_key = os.getenv("UN_COMTRADE_API_KEY", "").strip()
    headers = {"User-Agent": user_agent}
    if api_key:
        headers["Ocp-Apim-Subscription-Key"] = api_key
    source_id = "un_comtrade"
    year = 2024
    # HS 8542: Electronic integrated circuits. This is a narrow v0.1 proxy, not the full semiconductor universe.
    base = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
    urls = {
        "exports_world": f"{base}?reporterCode=410&period={year}&partnerCode=0&cmdCode=8542&flowCode=X",
        "imports_world": f"{base}?reporterCode=410&period={year}&partnerCode=0&cmdCode=8542&flowCode=M",
        "exports_china": f"{base}?reporterCode=410&period={year}&partnerCode=156&cmdCode=8542&flowCode=X",
        "exports_usa": f"{base}?reporterCode=410&period={year}&partnerCode=842&cmdCode=8542&flowCode=X",
    }
    values: dict[str, float] = {}
    for suffix, url in urls.items():
        extra = {"Ocp-Apim-Subscription-Key": api_key} if api_key else None
        dl = fetch_url(session, source_id, url, user_agent, f"_{suffix}", extra_headers=extra)
        state.add_raw(source_id, dl.file_path)
        if not dl.file_path or dl.status_code != 200:
            continue
        try:
            data = json.loads(dl.file_path.read_text(encoding="utf-8"))
            records = data.get("data") or data.get("dataset") or []
            total = sum(float(r.get("primaryValue") or r.get("TradeValue") or 0) for r in records)
            values[suffix] = total
        except Exception:
            continue
    if values.get("exports_world"):
        exports = values["exports_world"]
        state.add_observation("semiconductor_exports_usd", "KOR", year, exports, source_id, state.source_url(source_id), notes="UN Comtrade API v1, reporter Korea, HS 8542, exports to world. Narrow v0.1 semiconductor proxy.")
        if values.get("exports_china") is not None:
            state.add_observation("semiconductor_exports_to_china_share", "KOR", year, values["exports_china"] / exports * 100, source_id, state.source_url(source_id), notes="China share of Korean HS 8542 exports.")
        if values.get("exports_usa") is not None:
            state.add_observation("semiconductor_exports_to_us_share", "KOR", year, values["exports_usa"] / exports * 100, source_id, state.source_url(source_id), notes="U.S. share of Korean HS 8542 exports.")
        if values.get("imports_world") is not None:
            state.add_observation("semiconductor_trade_balance_usd", "KOR", year, exports - values["imports_world"], source_id, state.source_url(source_id), notes="Korean HS 8542 exports minus imports.")
    else:
        for indicator_id in ["semiconductor_exports_usd", "semiconductor_exports_to_china_share", "semiconductor_exports_to_us_share", "semiconductor_trade_balance_usd"]:
            state.add_manual(indicator_id, source_id, "UN Comtrade API did not return a simple parseable response for HS 8542 in v0.1.")


def collect_opendart_stub(state: CollectionState) -> None:
    source_id = "opendart"
    if not os.getenv("OPENDART_API_KEY", "").strip():
        reason = "OPENDART_API_KEY is not set; filing extraction skipped."
    else:
        reason = "OPENDART_API_KEY is set, but semiconductor revenue/HBM extraction still requires filing taxonomy mapping in v0.1."
    for indicator_id in ["samsung_sk_semiconductor_revenue", "ai_memory_hbm_disclosure_flag", "major_ai_company_filing_count"]:
        state.add_manual(indicator_id, source_id, reason, issue_type="api_key_or_manual_mapping")


def add_remaining_manual_items(state: CollectionState) -> None:
    manual_reasons = {
        "data_center_inventory_mw": ("cbre_data_center_trends", "CBRE market report table extraction is manual in v0.1."),
        "firm_ai_task_replacement_pct": ("oecd_korea_ai_labor", "OECD report table extraction is manual in v0.1."),
        "firm_ai_training_pct": ("oecd_korea_ai_labor", "OECD report table extraction is manual in v0.1."),
        "stem_tertiary_graduate_share": ("oecd_education", "OECD education portal category selection is manual in v0.1."),
        "ai_relevant_graduates_count": ("korea_moe", "Korea MOE category mapping is manual in v0.1."),
        "adult_learning_participation_pct": ("oecd_korea_ai_labor", "OECD report table extraction is manual in v0.1."),
        "ai_hub_dataset_count": ("nia_ai_hub", "AI Hub current dataset count requires manual site verification."),
        "un_egdi_score": ("un_egov", "UN EGDI data table extraction is manual in v0.1."),
        "un_egdi_rank": ("un_egov", "UN EGDI data table extraction is manual in v0.1."),
        "government_ai_readiness_rank": ("oxford_ai_readiness", "Oxford Insights index table extraction is manual in v0.1."),
        "ai_basic_act_status": ("msit_ai_basic_act", "AI Basic Act official status/date requires manual legal-source review."),
        "defense_ai_program_event_count": ("mnd_dapa_public", "Defense AI/autonomy event coding requires manual review."),
        "defense_ai_institution_count": ("mnd_dapa_public", "Defense AI institution coding requires manual review."),
        "military_manpower_pressure_indicator": ("kosis", "KOSIS exact demographic table selection is manual in v0.1."),
    }
    existing = {m["indicator_id"] for m in state.manual}
    observed = {o["indicator_id"] for o in state.observations}
    for indicator_id, (source_id, reason) in manual_reasons.items():
        if indicator_id not in existing and indicator_id not in observed:
            state.add_manual(indicator_id, source_id, reason)


def run_collection() -> CollectionState:
    ensure_dirs()
    indicators = load_indicators()
    sources = load_sources()
    state = CollectionState(indicators, sources)
    user_agent = os.getenv("USER_AGENT", "KoreaAIIndustrySnapshot/0.1 research project")
    session = requests.Session()

    ordered_pages = [
        ("msit_2026_work_plan", state.source_url("msit_2026_work_plan"), parse_msit_work_plan),
        ("msit_gpu_procurement", state.source_url("msit_gpu_procurement"), parse_msit_gpu_procurement),
        ("kisti_hangang", state.source_url("kisti_hangang"), parse_kisti),
        ("ifr_robotics", state.source_url("ifr_robotics"), parse_ifr_density),
        ("ifr_robotics", SOURCE_URL_OVERRIDES["ifr_robotics_installations"], parse_ifr_installations),
        ("bok_genai", state.source_url("bok_genai"), parse_bok),
        ("mss_venture", SOURCE_URL_OVERRIDES["mss_venture"], parse_mss_venture),
        ("mss_smart_manufacturing", state.source_url("mss_smart_manufacturing"), parse_mss_smart),
        ("nvidia_korea_ai_infrastructure", state.source_url("nvidia_korea_ai_infrastructure"), parse_nvidia),
        ("pew_ai_views", state.source_url("pew_ai_views"), parse_pew),
        ("tradegov_unmanned_defense", state.source_url("tradegov_unmanned_defense"), parse_tradegov_defense),
    ]
    for source_id, url, parser in ordered_pages:
        dl = fetch_url(session, source_id, url, user_agent)
        state.add_raw(source_id, dl.file_path)
        if dl.status_code == 200 and dl.file_path:
            parser(state, dl)
        else:
            state.errors[source_id] = dl.notes or f"HTTP status {dl.status_code}"
            for indicator_id, meta in state.indicators.items():
                if meta.get("primary_source_id") == source_id:
                    state.add_manual(indicator_id, source_id, f"Download failed or returned status {dl.status_code}.", issue_type="download_failed", source_url=url)

    collect_epoch_models(state, session, user_agent)
    collect_epoch_gpu_clusters(state, session, user_agent)
    collect_epoch_chip_owners(state, session, user_agent)
    collect_openalex(state, session, user_agent)
    collect_top500(state, session, user_agent)
    collect_stanford_local(state)
    collect_un_comtrade(state, session, user_agent)
    collect_opendart_stub(state)
    add_remaining_manual_items(state)

    obs = pd.DataFrame(state.observations, columns=OBSERVATION_COLUMNS)
    if not obs.empty:
        obs = obs.drop_duplicates(subset=["observation_id"]).sort_values(["indicator_id", "country_iso3", "year"])
    manual = pd.DataFrame(state.manual, columns=MANUAL_REVIEW_COLUMNS).drop_duplicates(subset=["item_id"]) if state.manual else pd.DataFrame(columns=MANUAL_REVIEW_COLUMNS)
    status = state.build_collection_status()
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    MANUAL_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    obs.to_csv(SILVER_DIR / "observations.csv", index=False)
    manual.to_csv(SILVER_DIR / "manual_review_queue.csv", index=False)
    manual.to_csv(REPORTS_DIR / "manual_review_queue.csv", index=False)
    status.to_csv(REPORTS_DIR / "collection_status.csv", index=False)
    status.to_csv(MANUAL_REVIEW_DIR / "collection_status.csv", index=False)
    if not obs.empty:
        obs.to_csv(REPORTS_DIR / "collected_observations.csv", index=False)
    return state
