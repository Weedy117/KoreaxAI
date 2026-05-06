from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kai_dash.collectors import run_collection


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    state = run_collection()
    print(f"Collected observations: {len(state.observations)}")
    print(f"Manual review items: {len(state.manual)}")


if __name__ == "__main__":
    main()
