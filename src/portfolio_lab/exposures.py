"""Look-through exposures: sector, country, currency and duration.

Fund-level exposures come from, in order of preference:
1. iShares holdings files stored in the ``holdings`` table (line-by-line);
2. the factsheet-based fallback files in data/reference/;
3. Yahoo sector weights stored in ``fund_exposures`` (Morningstar buckets,
   equity funds only).

Portfolio exposure to bucket k = sum_i w_i * e_ik, where e_ik is fund i's
weight in bucket k. Holdings are a single snapshot, so look-through figures
describe the portfolio as it stands today, not historically.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import db

COUNTRY_CCY = {
    "United States": "USD", "Japan": "JPY", "United Kingdom": "GBP", "France": "EUR",
    "Germany": "EUR", "Netherlands": "EUR", "Spain": "EUR", "Italy": "EUR", "Ireland": "EUR",
    "Belgium": "EUR", "Finland": "EUR", "Austria": "EUR", "Portugal": "EUR", "Switzerland": "CHF",
    "Australia": "AUD", "Sweden": "SEK", "Denmark": "DKK", "Norway": "NOK", "Hong Kong": "HKD",
    "Singapore": "SGD", "Israel": "ILS", "New Zealand": "NZD", "Canada": "CAD", "Taiwan": "TWD",
    "South Korea": "KRW", "Korea (South)": "KRW", "China": "HKD/CNY", "India": "INR", "Brazil": "BRL",
    "South Africa": "ZAR", "Saudi Arabia": "SAR", "Mexico": "MXN", "Malaysia": "MYR",
    "United Arab Emirates": "AED", "Indonesia": "IDR", "Thailand": "THB", "Poland": "PLN",
    "Other Developed": "Other DM", "Other EM": "Other EM", "Other": "Other",
    "Gold (no country)": "Gold (XAU)",
}
MAJOR_CCY = ["USD", "EUR", "JPY", "GBP", "CHF", "TWD", "KRW", "HKD/CNY", "INR", "CAD", "AUD", "Gold (XAU)"]
BOND_FUNDS = {"AGG", "TIP", "IEF", "TLT", "SHY", "SHV", "LQD", "HYG", "EMB"}


def _norm_country(x: str) -> str:
    x = (x or "").strip()
    return {"Korea (South)": "South Korea", "Korea": "South Korea", "": "Other", "-": "Other",
            "European Union": "Other"}.get(x, x)


def _bond_sector(fund: str, s: str) -> str:
    s = (s or "").lower()
    if "cash" in s or "money market" in s:
        return "Cash & T-bills"
    if fund == "TIP":
        return "FI: TIPS"
    if fund == "HYG":
        return "FI: HY Corporate"
    if fund == "EMB":
        return "FI: EM Sovereign"
    if "treasur" in s:
        return "FI: Treasury"
    if any(k in s for k in ("mbs", "cmbs", "abs", "covered", "securitized")):
        return "FI: Securitized (MBS/CMBS)"
    if any(k in s for k in ("industrial", "financial", "utility", "corporate")):
        return "FI: IG Corporate"
    return "FI: Govt-related"


def _equity_sector(s: str) -> str:
    s = (s or "").strip()
    if "cash" in s.lower() or "derivative" in s.lower():
        return "Cash & T-bills"
    if s in ("Real Estate", "Other", "", "-"):
        return "Real Estate & Other"
    return {"Communication Services": "Communication"}.get(s, s)


def from_holdings(h: pd.DataFrame) -> pd.DataFrame:
    """Fund exposures (long format) from a holdings table."""
    rows = []
    for fund, g in h.groupby("fund"):
        g = g.copy()
        # iShares rounds each line to two decimals, so a fund with thousands of
        # tiny positions (AGG has 13k) loses weight, and the loss is not spread
        # evenly: small corporate bonds round to zero while large Treasuries do
        # not. Below 95% of weight accounted for, the factsheet split is the
        # better source for sector, country and currency.
        if g["weight"].sum() < 95:
            continue
        g["w"] = g["weight"] / g["weight"].sum()
        is_bond = fund in BOND_FUNDS
        g["sector_b"] = [(_bond_sector(fund, s) if is_bond else _equity_sector(s)) for s in g["sector"]]
        g["country_b"] = [_norm_country(c) for c in g["location"]]
        if is_bond:
            g["ccy_b"] = "USD"
        else:
            g["ccy_b"] = g["currency"].fillna("USD").replace({"CNY": "HKD/CNY", "HKD": "HKD/CNY", "CNH": "HKD/CNY"})
        as_of = g["as_of"].iloc[0]
        for dim, col in (("sector", "sector_b"), ("country", "country_b"), ("currency", "ccy_b")):
            s = g.groupby(col)["w"].sum()
            rows += [(fund, as_of, dim, k, float(v), "ishares holdings") for k, v in s.items()]
    return pd.DataFrame(rows, columns=["fund", "as_of", "dimension", "bucket", "weight", "source"])


def _currency_from_country(fx: pd.DataFrame) -> pd.DataFrame:
    c = fx[fx["dimension"] == "country"].copy()
    bond = c["fund"].isin(BOND_FUNDS)
    c["bucket"] = np.where(bond, "USD", c["bucket"].map(COUNTRY_CCY).fillna("Other"))
    c["dimension"] = "currency"
    c["source"] = c["source"] + " (ccy via country)"
    return c.groupby(["fund", "as_of", "dimension", "bucket", "source"], as_index=False)["weight"].sum()


def fund_exposures(con) -> pd.DataFrame:
    """Best available exposures per fund and dimension."""
    fb = pd.read_csv(db.REF_DIR / "fund_exposures_fallback.csv")
    fb = pd.concat([fb, _currency_from_country(fb)], ignore_index=True)
    parts = [fb.assign(rank=2)]
    if db.table_exists(con, "fund_exposures"):
        # Yahoo sectors use Morningstar buckets and cover equity funds only, so they
        # are a last resort behind the iShares factsheet figures.
        yh = pd.read_sql("SELECT * FROM fund_exposures", con)
        if len(yh):
            parts.append(yh.assign(rank=3))
    h = pd.read_sql("SELECT * FROM holdings", con) if db.table_exists(con, "holdings") else pd.DataFrame()
    if len(h):
        parts.append(from_holdings(h).assign(rank=1))
    allx = pd.concat(parts, ignore_index=True)
    best = allx.groupby(["fund", "dimension"])["rank"].transform("min")
    out = allx[allx["rank"] == best].drop(columns="rank")
    # IAU is gold: no holdings file, force the obvious answer
    out = out[out["fund"] != "IAU"]
    gold = pd.DataFrame([("IAU", None, d, b, 1.0, "by construction") for d, b in
                         (("sector", "Gold"), ("country", "Gold (no country)"), ("currency", "Gold (XAU)"))],
                        columns=out.columns)
    return pd.concat([out, gold], ignore_index=True)


def bond_characteristics(con) -> pd.DataFrame:
    """Duration and spread sensitivities per bond fund."""
    fb = pd.read_csv(db.REF_DIR / "bond_characteristics_fallback.csv").set_index("fund")
    fb["dur_source"] = fb["source"]
    h = pd.read_sql("SELECT fund, as_of, weight, duration FROM holdings", con) if db.table_exists(con, "holdings") else pd.DataFrame()
    for f in fb.index:
        # Duration comes from the holdings file or the factsheet fallback. Yahoo's
        # fund "duration" field was checked and is not an effective duration
        # (it puts TLT at 3.6 years against a published 15.3), so it is not used.
        dur, src = None, None
        g = h[(h["fund"] == f) & h["duration"].notna()] if len(h) else pd.DataFrame()
        if len(g) and g["weight"].sum() > 50:
            dur = float((g["weight"] * g["duration"]).sum() / h.loc[h["fund"] == f, "weight"].sum())
            src = f"ishares holdings {g['as_of'].iloc[0]}"
        if dur is not None and 0 < dur < 30:
            if f == "TIP":
                fb.loc[f, "real_duration"] = dur
            else:
                fb.loc[f, "duration"] = dur
            fb.loc[f, "dur_source"] = src
    return fb[["duration", "real_duration", "ig_spread_share", "hy_spread_share", "dur_source"]]


def look_through(weights: pd.Series, fx: pd.DataFrame, dimension: str) -> pd.Series:
    d = fx[fx["dimension"] == dimension]
    w = weights[weights.abs() > 1e-9]
    out = {}
    for fund, wt in w.items():
        g = d[d["fund"] == fund]
        if g.empty:
            out["Unmapped"] = out.get("Unmapped", 0.0) + wt
            continue
        s = g.groupby("bucket")["weight"].sum()
        s = s / s.sum()
        for k, v in s.items():
            out[k] = out.get(k, 0.0) + wt * v
    return pd.Series(out).sort_values(ascending=False)


def duration_profile(weights: pd.Series, bc: pd.DataFrame) -> dict:
    w = weights.reindex(bc.index).fillna(0.0)
    bond_w = w.sum()
    nominal = float((w * bc["duration"]).sum())
    real = float((w * bc["real_duration"]).sum())
    ig = float((w * bc["duration"] * bc["ig_spread_share"]).sum())
    hy = float((w * bc["duration"] * bc["hy_spread_share"]).sum())
    return {
        "bond_weight": float(bond_w),
        "nominal_duration": nominal,           # years, contribution to total portfolio
        "real_duration": real,
        "total_rate_duration": nominal + real,
        "bond_sleeve_duration": (nominal + real) / bond_w if bond_w > 0 else 0.0,
        "ig_spread_duration": ig,
        "hy_spread_duration": hy,
        "dv01_per_1m": (nominal + real) * 100.0,  # USD per 1bp per USD 1m
    }


def by_duration_contributor(weights: pd.Series, bc: pd.DataFrame) -> pd.Series:
    w = weights.reindex(bc.index).fillna(0.0)
    return (w * (bc["duration"] + bc["real_duration"])).loc[lambda s: s > 1e-9].sort_values(ascending=False)


def look_through_holdings(weights: pd.Series, h: pd.DataFrame, top: int = 12) -> pd.DataFrame:
    """Largest single issuers once the funds are looked through."""
    if h.empty:
        return pd.DataFrame(columns=["name", "ticker", "weight", "via"])
    rows = []
    for fund, wt in weights[weights > 1e-9].items():
        g = h[(h["fund"] == fund) & (h["asset_class"].str.lower() == "equity")]
        if g.empty or g["weight"].sum() < 50:
            continue
        g = g.assign(w=wt * g["weight"] / g["weight"].sum())
        rows.append(g[["name", "ticker", "w"]].assign(via=fund))
    if not rows:
        return pd.DataFrame(columns=["name", "ticker", "weight", "via"])
    allh = pd.concat(rows)
    agg = (allh.groupby(["name", "ticker"], as_index=False)
                .agg(weight=("w", "sum"), via=("via", lambda s: ", ".join(sorted(set(s))))))
    return agg.sort_values("weight", ascending=False).head(top).reset_index(drop=True)
