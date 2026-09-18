"""Build the supporting outputs: results.db, Excel workbook, figures, dashboard JSON.

    python scripts/build_reports.py [--db data/etf_lab.db]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from portfolio_lab import reports  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=None)
    a = p.parse_args()
    R = reports.read_results(a.db)
    print("results.db ->", reports.export_results_db(a.db))
    print("workbook   ->", reports.build_excel(R))
    for f in reports.build_figures(R):
        print("figure     ->", f)
    print("json       ->", reports.dashboard_json(R))


if __name__ == "__main__":
    main()
