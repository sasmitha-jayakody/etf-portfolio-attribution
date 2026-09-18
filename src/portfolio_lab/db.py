"""SQLite storage for prices, holdings, macro series and pipeline results.

One file (data/etf_lab.db) holds everything. Raw inputs (prices, holdings,
macro) are written by the fetch step; the pipeline writes its results into
tables prefixed ``res_`` so the dashboard only ever has to read one file.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
REF_DIR = DATA_DIR / "reference"
DEFAULT_DB = DATA_DIR / "etf_lab.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS securities (
    ticker            TEXT PRIMARY KEY,
    name              TEXT,
    issuer            TEXT,
    asset_class       TEXT,
    segment           TEXT,
    role              TEXT,
    expense_ratio_pct REAL,
    cost_bps          REAL,
    inception         TEXT,
    backfill_proxy    TEXT
);

CREATE TABLE IF NOT EXISTS prices (
    ticker    TEXT NOT NULL,
    date      TEXT NOT NULL,
    close     REAL,
    adj_close REAL,
    volume    REAL,
    dividend  REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS macro (
    series TEXT NOT NULL,
    date   TEXT NOT NULL,
    value  REAL,
    source TEXT,
    PRIMARY KEY (series, date)
);

-- One row per holding line in an iShares holdings file.
CREATE TABLE IF NOT EXISTS holdings (
    fund         TEXT NOT NULL,
    as_of        TEXT,
    name         TEXT,
    ticker       TEXT,
    sector       TEXT,
    asset_class  TEXT,
    location     TEXT,
    currency     TEXT,
    weight       REAL,
    duration     REAL,
    ytm          REAL,
    maturity     TEXT,
    coupon       REAL
);
CREATE INDEX IF NOT EXISTS ix_holdings_fund ON holdings(fund);

-- Fund-level exposures in long format (dimension = sector | country | currency).
CREATE TABLE IF NOT EXISTS fund_exposures (
    fund      TEXT NOT NULL,
    as_of     TEXT,
    dimension TEXT NOT NULL,
    bucket    TEXT NOT NULL,
    weight    REAL,
    source    TEXT
);

-- Fund-level bond characteristics.
CREATE TABLE IF NOT EXISTS fund_characteristics (
    fund       TEXT PRIMARY KEY,
    as_of      TEXT,
    duration   REAL,
    ytm        REAL,
    source     TEXT
);

CREATE TABLE IF NOT EXISTS fetch_log (
    run_at  TEXT,
    item    TEXT,
    status  TEXT,
    detail  TEXT
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path) if path else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


@contextmanager
def session(path: Path | str | None = None):
    con = connect(path)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def load_universe() -> pd.DataFrame:
    return pd.read_csv(REF_DIR / "etf_universe.csv", dtype={"backfill_proxy": str}).fillna(
        {"backfill_proxy": ""}
    )


def write_universe(con: sqlite3.Connection) -> None:
    uni = load_universe()
    con.execute("DELETE FROM securities")
    uni.to_sql("securities", con, if_exists="append", index=False)


def read_prices(con: sqlite3.Connection, field: str = "adj_close") -> pd.DataFrame:
    """Wide frame of prices, index = date, columns = tickers."""
    df = pd.read_sql(f"SELECT ticker, date, {field} AS v FROM prices", con, parse_dates=["date"])
    if df.empty:
        return pd.DataFrame()
    return df.pivot(index="date", columns="ticker", values="v").sort_index()


def read_macro(con: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT series, date, value FROM macro", con, parse_dates=["date"])
    if df.empty:
        return pd.DataFrame()
    return df.pivot(index="date", columns="series", values="value").sort_index()


def write_frame(con: sqlite3.Connection, name: str, df: pd.DataFrame, index: bool = False) -> None:
    """Replace a results table."""
    df.to_sql(name, con, if_exists="replace", index=index)


def read_table(con: sqlite3.Connection, name: str) -> pd.DataFrame:
    return pd.read_sql(f"SELECT * FROM {name}", con)


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None
