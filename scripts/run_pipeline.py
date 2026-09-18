"""Run backtests, attribution, exposures and stress tests; write res_* tables.

    python scripts/run_pipeline.py              # uses data/etf_lab.db
    python scripts/run_pipeline.py --synthetic  # builds a throwaway synthetic DB first
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from portfolio_lab import db, pipeline, synthetic  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=None)
    p.add_argument("--synthetic", action="store_true", help="generate synthetic data (testing only)")
    a = p.parse_args()
    path = a.db
    if a.synthetic:
        path = path or str(ROOT / "data" / "synthetic.db")
        with db.session(path) as con:
            synthetic.write_to_db(con)
        print(f"Synthetic data written to {path} (NOT real market data)")
    pipeline.run(path)


if __name__ == "__main__":
    main()
