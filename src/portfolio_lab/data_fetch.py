"""Download prices, macro series and ETF holdings into SQLite.

Sources
-------
* Yahoo Finance (via yfinance): daily close and dividend-adjusted close for every
  ETF in data/reference/etf_universe.csv, plus Treasury yield indices, VIX and
  the dollar index. Also fund sector weights and bond duration as a fallback.
* FRED (public CSV endpoint, no key): Treasury yields, 10y real yield,
  10y breakeven inflation, CPI and the broad trade-weighted dollar.
* iShares (public holdings CSV on each product page): line-by-line holdings
  with GICS sector, country, market currency and, for bond funds, duration.

Every item is attempted independently and logged, so one failed download
never stops the rest. Run ``python scripts/fetch_data.py --help`` for options.
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import db

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

YAHOO_MACRO = {
    "^TNX": "UST10Y_YAHOO",   # 10y Treasury yield, percent
    "^FVX": "UST5Y_YAHOO",
    "^IRX": "TBILL3M_YAHOO",  # 13-week T-bill, percent
    "^TYX": "UST30Y_YAHOO",
    "^VIX": "VIX",
    "DX-Y.NYB": "DXY",
}

FRED_SERIES = {
    "DGS10": "UST10Y",        # 10y nominal Treasury, %
    "DGS2": "UST2Y",
    "DGS3MO": "TBILL3M",
    "DFII10": "REAL10Y",      # 10y TIPS real yield, %
    "T10YIE": "BE10Y",        # 10y breakeven inflation, %
    "CPIAUCSL": "CPI",        # CPI index, monthly
    "DTWEXBGS": "USD_BROAD",  # broad trade-weighted dollar index
}

# Fallback map used if the iShares product screener cannot be read.
ISHARES_PRODUCTS = {
    "IVV": "239726/ishares-core-sp-500-etf",
    "IEFA": "244049/ishares-core-msci-eafe-etf",
    "IEMG": "244050/ishares-core-msci-emerging-markets-etf",
    "QUAL": "256101/ishares-msci-usa-quality-factor-etf",
    "VLUE": "251616/ishares-msci-usa-value-factor-etf",
    "AGG": "239458/ishares-core-total-us-bond-market-etf",
    "TIP": "239467/ishares-tips-bond-etf",
    "IEF": "239456/ishares-710-year-treasury-bond-etf",
    "TLT": "239454/ishares-20-year-treasury-bond-etf",
    "SHY": "239452/ishares-13-year-treasury-bond-etf",
    "LQD": "239566/ishares-iboxx-investment-grade-corporate-bond-etf",
    "HYG": "239565/ishares-iboxx-high-yield-corporate-bond-etf",
    "EMB": "239572/ishares-jp-morgan-usd-emerging-markets-bond-etf",
    "SHV": "239466/ishares-short-treasury-bond-etf",
    "ACWI": "239600/ishares-msci-acwi-etf",
    "USMV": "239695/ishares-msci-usa-minimum-volatility-etf",
    "MTUM": "251614/ishares-msci-usa-momentum-factor-etf",
    "EFA": "239623/ishares-msci-eafe-etf",
    "EEM": "239637/ishares-msci-emerging-markets-etf",
}
ISHARES_SCREENER = (
    "https://www.ishares.com/us/product-screener/product-screener-v3.1.jsn?"
    "dcrPath=/templatedata/config/product-screener-v3/data/en/us-ishares/"
    "ishares-product-screener-backend-config&siteEntryPassthrough=true"
)
# iShares moved the holdings download in 2026; the slug in the path is ignored,
# only the portfolio id matters. The old .ajax endpoint is kept as a fallback.
HOLDINGS_PATHS = [
    "latest-holdings.csv",
    "1467271812596.ajax?fileType=csv&fileName={t}_holdings&dataType=fund",
]

# Morningstar sector keys used by Yahoo -> GICS-style names.
YAHOO_SECTOR_MAP = {
    "technology": "Information Technology",
    "financial_services": "Financials",
    "healthcare": "Health Care",
    "consumer_cyclical": "Consumer Discretionary",
    "consumer_defensive": "Consumer Staples",
    "communication_services": "Communication",
    "industrials": "Industrials",
    "energy": "Energy",
    "utilities": "Utilities",
    "realestate": "Real Estate",
    "basic_materials": "Materials",
}


# --------------------------------------------------------------------------- utils
def _log(con, item: str, status: str, detail: str = "") -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("INSERT INTO fetch_log VALUES (?,?,?,?)", (ts, item, status, detail[:500]))
    print(f"  [{status:>4}] {item} {detail[:120]}")


def _http_get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return raw.decode("utf-8-sig", errors="replace")


def _num(x) -> float:
    if x is None:
        return np.nan
    s = str(x).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "--", "N/A", "NA", "nan"):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        fields = {"Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends"}
        lvl = 0 if set(df.columns.get_level_values(0)) & fields else 1
        df = df.copy()
        df.columns = df.columns.get_level_values(lvl)
    return df


def _naive_dates(idx) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(idx)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


# --------------------------------------------------------------------------- prices
def download_history(ticker: str, start: str, retries: int = 3) -> pd.DataFrame:
    """Daily close, adjusted close, volume and dividends for one ticker."""
    import yfinance as yf

    last_err = None
    for attempt in range(retries):
        try:
            hist = yf.Ticker(ticker).history(start=start, auto_adjust=False, actions=True)
            hist = _flatten(hist)
            if hist is None or hist.empty:
                hist = _flatten(
                    yf.download(ticker, start=start, auto_adjust=False, actions=True, progress=False)
                )
            if hist is None or hist.empty:
                raise ValueError("empty response")
            if "Adj Close" not in hist.columns:
                adj = _flatten(yf.Ticker(ticker).history(start=start, auto_adjust=True))
                hist["Adj Close"] = adj["Close"].reindex(hist.index)
            out = pd.DataFrame(
                {
                    "date": _naive_dates(hist.index).strftime("%Y-%m-%d"),
                    "close": hist["Close"].to_numpy(dtype=float),
                    "adj_close": hist["Adj Close"].to_numpy(dtype=float),
                    "volume": hist.get("Volume", pd.Series(np.nan, index=hist.index)).to_numpy(dtype=float),
                    "dividend": hist.get("Dividends", pd.Series(0.0, index=hist.index)).to_numpy(dtype=float),
                }
            )
            out = out.dropna(subset=["adj_close"]).drop_duplicates("date", keep="last")
            out.insert(0, "ticker", ticker)
            return out
        except Exception as e:  # noqa: BLE001 - network code, log and retry
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{ticker}: {last_err}")


def fetch_prices(con, tickers: list[str], start: str) -> None:
    print(f"\nPrices ({len(tickers)} ETFs from {start})")
    for t in tickers:
        try:
            df = download_history(t, start)
            con.execute("DELETE FROM prices WHERE ticker=?", (t,))
            df.to_sql("prices", con, if_exists="append", index=False)
            _log(con, f"prices:{t}", "ok", f"{len(df)} rows {df['date'].iloc[0]} -> {df['date'].iloc[-1]}")
        except Exception as e:  # noqa: BLE001
            _log(con, f"prices:{t}", "FAIL", str(e))
        con.commit()
        time.sleep(0.5)


# --------------------------------------------------------------------------- macro
def fetch_yahoo_macro(con, start: str) -> None:
    print("\nMacro series from Yahoo")
    for sym, name in YAHOO_MACRO.items():
        try:
            df = download_history(sym, start)
            rows = pd.DataFrame(
                {"series": name, "date": df["date"], "value": df["close"], "source": "yahoo"}
            )
            con.execute("DELETE FROM macro WHERE series=?", (name,))
            rows.to_sql("macro", con, if_exists="append", index=False)
            _log(con, f"macro:{name}", "ok", f"{len(rows)} rows")
        except Exception as e:  # noqa: BLE001
            _log(con, f"macro:{name}", "FAIL", str(e))
        con.commit()


def fetch_fred(con, start: str) -> None:
    print("\nMacro series from FRED")
    for fred_id, name in FRED_SERIES.items():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}&cosd={start}"
        try:
            text = _http_get(url)
            df = pd.read_csv(io.StringIO(text))
            date_col = df.columns[0]
            df = df.rename(columns={date_col: "date", df.columns[1]: "value"})
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df = df.dropna()
            if df.empty:
                raise ValueError("no observations")
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df["series"] = name
            df["source"] = "fred"
            con.execute("DELETE FROM macro WHERE series=?", (name,))
            df[["series", "date", "value", "source"]].to_sql("macro", con, if_exists="append", index=False)
            _log(con, f"macro:{name}", "ok", f"{len(df)} rows")
        except Exception as e:  # noqa: BLE001
            _log(con, f"macro:{name}", "FAIL", str(e))
        con.commit()


# --------------------------------------------------------------------------- holdings
def _screener_map() -> dict[str, str]:
    """ticker -> '/us/products/<id>/<slug>' from the iShares product screener."""
    try:
        data = json.loads(_http_get(ISHARES_SCREENER, timeout=45))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, str] = {}

    def val(v):
        if isinstance(v, dict):
            return v.get("r") or v.get("d")
        return v

    records = data.values() if isinstance(data, dict) else data
    for rec in records:
        if not isinstance(rec, dict):
            continue
        tick, url = None, None
        for k, v in rec.items():
            kl = k.lower()
            if "ticker" in kl and tick is None:
                tick = val(v)
            if "productpageurl" in kl:
                url = val(v)
        if isinstance(tick, str) and isinstance(url, str) and "/products/" in url:
            out.setdefault(tick.upper(), url)
    return out


def parse_ishares_holdings(text: str, fund: str) -> pd.DataFrame:
    """Parse an iShares holdings CSV (metadata header, table, disclaimer footer)."""
    lines = text.splitlines()
    as_of = None
    for ln in lines[:20]:
        if "holdings as of" in ln.lower():
            m = re.search(r'"?([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})"?', ln)
            if m:
                as_of = datetime.strptime(m.group(1), "%b %d, %Y").strftime("%Y-%m-%d")
    hdr = next(
        (i for i, ln in enumerate(lines) if "Weight (%)" in ln and ("Name" in ln or "Ticker" in ln)),
        None,
    )
    if hdr is None:
        raise ValueError("holdings table header not found")
    reader = csv.reader(lines[hdr:])
    header = [h.strip() for h in next(reader)]
    rows = []
    for row in reader:
        if len(row) < max(3, len(header) // 2):
            if rows:
                break
            continue
        rows.append(row[: len(header)] + [""] * (len(header) - len(row)))
    raw = pd.DataFrame(rows, columns=header)

    def col(*names):
        for n in names:
            if n in raw.columns:
                return raw[n]
        return pd.Series([None] * len(raw))

    out = pd.DataFrame(
        {
            "fund": fund,
            "as_of": as_of,
            "name": col("Name"),
            "ticker": col("Ticker", "Issuer Ticker"),
            "sector": col("Sector"),
            "asset_class": col("Asset Class"),
            "location": col("Location", "Location of Risk"),
            "currency": col("Market Currency", "Currency"),
            "weight": col("Weight (%)").map(_num),
            "duration": col("Duration", "Effective Duration", "Mod. Duration").map(_num),
            "ytm": col("YTM (%)", "Yield to Worst (%)").map(_num),
            "maturity": col("Maturity"),
            "coupon": col("Coupon (%)").map(_num),
        }
    )
    out = out[out["weight"].notna()]
    if out.empty:
        raise ValueError("no holdings rows parsed")
    return out


def fetch_ishares_holdings(con, funds: list[str]) -> None:
    print(f"\niShares holdings ({len(funds)} funds)")
    screener = _screener_map()
    _log(con, "ishares:screener", "ok" if screener else "WARN",
         f"{len(screener)} products mapped" if screener else "screener unavailable, using built-in map")
    for f in funds:
        path = screener.get(f)
        bases = []
        if path:
            bases.append("https://www.ishares.com" + path.rstrip("/"))
        if f in ISHARES_PRODUCTS:
            bases.append(f"https://www.ishares.com/us/products/{ISHARES_PRODUCTS[f]}")
        candidates = [f"{b}/{suffix.format(t=f)}" for b in bases for suffix in HOLDINGS_PATHS]
        if not candidates:
            _log(con, f"holdings:{f}", "skip", "no product page known")
            continue
        err = ""
        for url in candidates:
            try:
                df = parse_ishares_holdings(_http_get(url, timeout=60), f)
                con.execute("DELETE FROM holdings WHERE fund=?", (f,))
                df.to_sql("holdings", con, if_exists="append", index=False)
                _log(con, f"holdings:{f}", "ok", f"{len(df)} lines as of {df['as_of'].iloc[0]}, "
                                                  f"weights sum {df['weight'].sum():.1f}%")
                err = ""
                break
            except Exception as e:  # noqa: BLE001
                err = str(e)
        if err:
            _log(con, f"holdings:{f}", "FAIL", err)
        con.commit()
        time.sleep(1.0)


def fetch_yahoo_fund_data(con, funds: list[str]) -> None:
    """Sector weights and bond duration from Yahoo, used where iShares data is missing."""
    import yfinance as yf

    print(f"\nYahoo fund data ({len(funds)} funds)")
    today = datetime.now().strftime("%Y-%m-%d")
    for f in funds:
        try:
            fd = yf.Ticker(f).funds_data
            n = 0
            sw = getattr(fd, "sector_weightings", None) or {}
            if sw:
                con.execute("DELETE FROM fund_exposures WHERE fund=? AND source='yahoo'", (f,))
                for k, w in sw.items():
                    con.execute(
                        "INSERT INTO fund_exposures VALUES (?,?,?,?,?,?)",
                        (f, today, "sector", YAHOO_SECTOR_MAP.get(k, k), float(w), "yahoo"),
                    )
                n += len(sw)
            bh = getattr(fd, "bond_holdings", None)
            if isinstance(bh, pd.DataFrame) and not bh.empty and "Duration" in bh.index:
                dur = _num(bh.loc["Duration"].iloc[0])
                if np.isfinite(dur) and dur > 0:
                    con.execute(
                        "INSERT OR REPLACE INTO fund_characteristics VALUES (?,?,?,?,?)",
                        (f, today, dur, None, "yahoo"),
                    )
                    n += 1
            _log(con, f"yahoo_fund:{f}", "ok" if n else "skip", f"{n} fields")
        except Exception as e:  # noqa: BLE001
            _log(con, f"yahoo_fund:{f}", "FAIL", str(e))
        con.commit()
        time.sleep(0.5)


# --------------------------------------------------------------------------- driver
def run(db_path=None, start: str = "2003-01-01", tickers: list[str] | None = None,
        prices: bool = True, macro: bool = True, holdings: bool = True) -> None:
    uni = db.load_universe()
    tickers = tickers or uni["ticker"].tolist()
    with db.session(db_path) as con:
        db.write_universe(con)
        if prices:
            fetch_prices(con, tickers, start)
        if macro:
            fetch_yahoo_macro(con, start)
            fetch_fred(con, start)
        if holdings:
            funds = [t for t in tickers if t in ISHARES_PRODUCTS]
            fetch_ishares_holdings(con, funds)
            fetch_yahoo_fund_data(con, funds)
        log = pd.read_sql("SELECT * FROM fetch_log", con)
    last = log.groupby("item").tail(1)
    bad = last[last["status"] == "FAIL"]
    print("\nSummary")
    print(f"  items attempted: {len(last)}   failed: {len(bad)}")
    if len(bad):
        print("  failed items: " + ", ".join(bad["item"]))
    print(f"  database: {db_path or db.DEFAULT_DB}")
