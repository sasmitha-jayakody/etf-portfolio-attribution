"""Download prices, macro data and ETF holdings into data/etf_lab.db.

    python scripts/fetch_data.py                 # everything (about 3-5 minutes)
    python scripts/fetch_data.py --no-holdings   # prices and macro only
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from portfolio_lab import data_fetch  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=None, help="SQLite path (default data/etf_lab.db)")
    p.add_argument("--start", default="2003-01-01", help="first date to download")
    p.add_argument("--tickers", nargs="*", help="subset of tickers (default: whole universe)")
    p.add_argument("--no-prices", action="store_true")
    p.add_argument("--no-macro", action="store_true")
    p.add_argument("--no-holdings", action="store_true")
    a = p.parse_args()
    data_fetch.run(
        db_path=a.db,
        start=a.start,
        tickers=a.tickers,
        prices=not a.no_prices,
        macro=not a.no_macro,
        holdings=not a.no_holdings,
    )


if __name__ == "__main__":
    main()
