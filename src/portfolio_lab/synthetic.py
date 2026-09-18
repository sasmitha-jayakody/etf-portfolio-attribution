"""Synthetic market data for tests and offline development ONLY.

Generates a plausible factor-driven daily return history for the ETF universe
(with each ETF starting at its real inception date) and matching macro
series. Results produced from this data are labelled SYNTHETIC by the
pipeline and must never be presented as real performance.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import db

# factor: annual vol, annual drift
_F = {
    "eq": (0.16, 0.08), "exus": (0.08, -0.02), "em": (0.10, 0.0), "val": (0.07, -0.01),
    "qual": (0.04, 0.01), "size": (0.07, -0.01), "mom": (0.08, 0.01), "rates": (0.07, 0.0),
    "credit": (0.05, 0.0), "infl": (0.03, 0.0), "usd": (0.08, 0.0), "gold": (0.16, 0.06),
    "comm": (0.22, 0.0),
}
# ETF loadings on the factors above
_L = {
    "IVV": {"eq": 1.0}, "ACWI": {"eq": 0.95, "exus": 0.35, "em": 0.1, "usd": -0.35},
    "IEFA": {"eq": 0.9, "exus": 1.0, "usd": -0.8}, "EFA": {"eq": 0.9, "exus": 1.0, "usd": -0.8},
    "IEMG": {"eq": 1.0, "exus": 0.6, "em": 1.0, "usd": -0.6}, "EEM": {"eq": 1.0, "exus": 0.6, "em": 1.0, "usd": -0.6},
    "QUAL": {"eq": 0.98, "qual": 1.0}, "VLUE": {"eq": 1.05, "val": 1.2, "size": 0.2},
    "USMV": {"eq": 0.72, "qual": 0.5}, "MTUM": {"eq": 1.0, "mom": 1.0},
    "IWM": {"eq": 1.15, "size": 1.0}, "IWD": {"eq": 0.95, "val": 0.6}, "IWF": {"eq": 1.05, "val": -0.5},
    "AGG": {"rates": 0.8, "credit": 0.25}, "TIP": {"rates": 0.85, "infl": 1.0},
    "IEF": {"rates": 1.0}, "TLT": {"rates": 2.3}, "SHY": {"rates": 0.25},
    "LQD": {"rates": 1.1, "credit": 1.0, "eq": 0.08}, "HYG": {"rates": 0.4, "credit": 1.6, "eq": 0.3},
    "EMB": {"rates": 1.0, "credit": 1.4, "eq": 0.2, "em": 0.2},
    "IAU": {"gold": 1.0, "usd": -0.3}, "GSG": {"comm": 1.0, "usd": -0.3}, "UUP": {"usd": 1.0},
    "SHV": {},
}
_IDIO = {"IVV": 0.01, "ACWI": 0.015, "SHV": 0.002, "SHY": 0.004, "IEF": 0.01, "TLT": 0.02, "AGG": 0.008}


def generate(start="2003-01-02", end="2026-09-10", seed=7) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    n = len(dates)
    names = list(_F)
    vol = np.array([_F[f][0] for f in names]) / np.sqrt(252)
    mu = np.array([_F[f][1] for f in names]) / 252
    # regimes: stress periods get higher vol and negative equity drift
    stress = np.zeros(n)
    for a, b, s in [("2007-10-09", "2009-03-09", 2.5), ("2020-02-19", "2020-03-23", 4.0),
                    ("2011-07-22", "2011-10-03", 1.8), ("2018-10-01", "2018-12-24", 1.6),
                    ("2022-01-03", "2022-10-12", 1.6)]:
        stress[(dates >= a) & (dates <= b)] = s
    scale = np.where(stress > 0, stress, 1.0)
    Z = rng.standard_normal((n, len(names))) * vol * scale[:, None] + mu
    i_eq, i_rates, i_cr, i_usd = names.index("eq"), names.index("rates"), names.index("credit"), names.index("usd")
    in_stress = stress > 0
    Z[in_stress, i_eq] -= 0.0012 * stress[in_stress]
    Z[in_stress, i_cr] -= 0.0004 * stress[in_stress]
    Z[in_stress, i_usd] += 0.0002 * stress[in_stress]
    y22 = (dates >= "2022-01-03") & (dates <= "2022-10-12")
    Z[y22, i_rates] -= 0.0007          # 2022: bonds fall with stocks
    Z[~y22 & in_stress, i_rates] += 0.0004  # other crises: flight to quality
    F = pd.DataFrame(Z, index=dates, columns=names)

    uni = db.load_universe().set_index("ticker")
    rf = 0.015 / 252
    rets = {}
    for t, load in _L.items():
        r = rf + sum(F[f] * b for f, b in load.items())
        r = r + rng.standard_normal(n) * _IDIO.get(t, 0.02) / np.sqrt(252)
        r = r - uni.loc[t, "expense_ratio_pct"] / 100 / 252 if t in uni.index else r
        rets[t] = r
    R = pd.DataFrame(rets)
    prices = 100 * (1 + R).cumprod()
    for t in prices.columns:
        inc = uni.loc[t, "inception"] if t in uni.index else start
        prices.loc[prices.index < inc, t] = np.nan

    y10 = 4.0 - 2.0 * (-F["rates"]).cumsum().clip(-3, 3) * 0 + (-F["rates"] / 0.07 * 0.06).cumsum()
    y10 = y10.clip(0.5, 5.5)
    be = (2.2 + (F["infl"] / 0.03 * 0.02).cumsum()).clip(0.2, 3.2)
    macro = pd.DataFrame({"UST10Y": y10, "BE10Y": be, "REAL10Y": y10 - be,
                          "VIX": 15 + 10 * scale + rng.standard_normal(n)}, index=dates)
    return prices, macro


def write_to_db(con, **kw) -> None:
    prices, macro = generate(**kw)
    db.write_universe(con)
    con.execute("DELETE FROM prices")
    con.execute("DELETE FROM macro")
    long = prices.stack().rename("adj_close").reset_index()
    long.columns = ["date", "ticker", "adj_close"]
    long["date"] = long["date"].dt.strftime("%Y-%m-%d")
    long["close"] = long["adj_close"]
    long["volume"] = np.nan
    long["dividend"] = 0.0
    long[["ticker", "date", "close", "adj_close", "volume", "dividend"]].to_sql("prices", con, if_exists="append", index=False)
    m = macro.stack().rename("value").reset_index()
    m.columns = ["date", "series", "value"]
    m["date"] = m["date"].dt.strftime("%Y-%m-%d")
    m["source"] = "synthetic"
    m[["series", "date", "value", "source"]].to_sql("macro", con, if_exists="append", index=False)
    con.execute("INSERT INTO fetch_log VALUES (datetime('now'), 'synthetic', 'ok', 'SYNTHETIC DATA')")
    con.commit()
