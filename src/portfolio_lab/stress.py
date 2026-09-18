"""Stress tests: historical replay and hypothetical factor shocks.

Historical replay
    Today's weights are held through each past stress window (no rebalancing).
    ETFs that did not yet exist are proxied (config.STRESS_PROXIES), and the
    proxy share of each result is reported. Where the window falls inside the
    backtest, the portfolio's realised return is reported as well.

Hypothetical shocks (instantaneous, first-order plus convexity)
    Bond ETFs   r = -D*dy + 0.5*D^2*dy^2 - D*ig_share*d_ig - D*hy_share*d_hy
                (TIP uses real duration and d_real = dy - d_breakeven)
    Equity ETFs r = beta_eq * E + beta_usd * U, betas from a 3-year weekly
                regression of each ETF on ACWI and UUP. E is the ACWI move;
                if a scenario leaves it unspecified, E is implied from ACWI's
                own regression on 10y yield changes and UUP.
    Gold        scenario value;  cash (SHV) r = -D*dy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .attribution import to_weekly

EQUITY = {"IVV", "IEFA", "IEMG", "QUAL", "VLUE", "ACWI", "EFA", "EEM", "USMV", "MTUM", "IWM", "IWD", "IWF"}


def seg_of(t: str) -> str:
    return {"ACWI": "Global Equity"}.get(t, config.SEGMENT_OF.get(t, t))


def spliced_returns(returns: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fill pre-inception gaps with proxy composites. Returns (returns, is_proxy mask)."""
    out = returns.copy()
    mask = pd.DataFrame(False, index=returns.index, columns=returns.columns)
    for t, proxy in config.STRESS_PROXIES.items():
        if t not in out:
            continue
        comp = sum(returns[p].fillna(0.0) * w for p, w in proxy.items())
        avail = pd.concat([returns[p] for p in proxy], axis=1).notna().all(axis=1)
        gap = out[t].isna() & avail
        out.loc[gap, t] = comp[gap]
        mask.loc[gap, t] = True
    return out, mask


def historical_replay(weights: dict[str, pd.Series], returns: pd.DataFrame,
                      realised: dict[str, pd.Series] | None = None) -> pd.DataFrame:
    R, proxy = spliced_returns(returns)
    rows = []
    for name, start, end in config.STRESS_WINDOWS:
        win = R.loc[start:end]
        if len(win) < 2:
            continue
        # the window return is measured from the close on `start`
        win = win.iloc[1:]
        cum = (1 + win.fillna(0.0)).prod() - 1
        for code, w in weights.items():
            w = w[w > 1e-9]
            have = win[w.index].notna().all()
            if not have.all():
                continue
            proxy_share = float(w[proxy.loc[win.index, w.index].any()].sum())
            row = {"window": name, "start": start, "end": end, "code": code,
                   "replay_return": float((w * cum[w.index]).sum()), "proxy_share": proxy_share}
            if realised is not None and code in realised:
                rr = realised[code]
                if rr.index[0] <= pd.Timestamp(start) and rr.index[-1] >= pd.Timestamp(end):
                    row["realised_return"] = float((1 + rr.loc[win.index[0]:end]).prod() - 1)
            rows.append(row)
    return pd.DataFrame(rows)


def window_contributions(weights: pd.Series, returns: pd.DataFrame, start: str, end: str) -> pd.Series:
    R, _ = spliced_returns(returns)
    win = R.loc[start:end].iloc[1:]
    cum = (1 + win.fillna(0.0)).prod() - 1
    w = weights[weights > 1e-9]
    return (w * cum[w.index]).groupby(seg_of).sum()


# --------------------------------------------------------------------- hypothetical
def sensitivities(returns: pd.DataFrame, macro: pd.DataFrame, bonds: pd.DataFrame,
                  lookback_years: int = 3) -> tuple[pd.DataFrame, dict]:
    """Per-ETF sensitivities used by the hypothetical scenario engine."""
    end = returns.index[-1]
    start = end - pd.DateOffset(years=lookback_years)
    wk = to_weekly(returns.loc[start:end])
    y10 = None
    for col in ("UST10Y", "UST10Y_YAHOO"):
        if col in macro and macro[col].loc[start:end].notna().sum() > 100:
            y10 = macro[col].loc[start:end].ffill()
            break
    dy = y10.resample("W-FRI").last().diff() if y10 is not None else None

    def reg(y, X):
        df = pd.concat([y.rename("y"), X], axis=1).dropna()
        Xm = np.column_stack([np.ones(len(df)), df.iloc[:, 1:].to_numpy()])
        b, *_ = np.linalg.lstsq(Xm, df["y"].to_numpy(), rcond=None)
        return b[1:]

    rows = []
    for t in sorted(set(config.SEGMENT_OF) | {"ACWI"}):
        if t not in returns:
            continue
        row = {"ticker": t, "kind": "equity" if t in EQUITY else ("gold" if t == "IAU" else "bond"),
               "beta_eq": 0.0, "beta_usd": 0.0, "dur": 0.0, "real_dur": 0.0, "ig_sd": 0.0, "hy_sd": 0.0}
        if row["kind"] == "equity":
            b = reg(wk[t], wk[["ACWI", "UUP"]])
            row["beta_eq"], row["beta_usd"] = float(b[0]), float(b[1])
        elif row["kind"] == "bond" and t in bonds.index:
            bc = bonds.loc[t]
            row["dur"] = float(bc["duration"])
            row["real_dur"] = float(bc["real_duration"])
            row["ig_sd"] = float(bc["duration"] * bc["ig_spread_share"])
            row["hy_sd"] = float(bc["duration"] * bc["hy_spread_share"])
        rows.append(row)
    sens = pd.DataFrame(rows).set_index("ticker")
    implied = {"eq_per_1pp_rates": 0.0, "eq_per_usd": 0.0}
    if dy is not None:
        X = pd.concat([dy.rename("dy"), wk["UUP"].rename("usd")], axis=1)
        b = reg(wk["ACWI"], X)
        implied = {"eq_per_1pp_rates": float(b[0]), "eq_per_usd": float(b[1])}
    return sens, implied


def shock_returns(sens: pd.DataFrame, implied: dict, rates=0.0, breakeven=0.0, equity=None,
                  usd=0.0, ig=0.0, hy=0.0, gold=0.0) -> pd.Series:
    E = equity if equity is not None else implied["eq_per_1pp_rates"] * rates + implied["eq_per_usd"] * usd
    dy, dbe, dig, dhy = rates / 100, breakeven / 100, ig / 100, hy / 100
    dreal = dy - dbe
    out = {}
    for t, s in sens.iterrows():
        if s["kind"] == "equity":
            out[t] = s["beta_eq"] * E + s["beta_usd"] * usd
        elif s["kind"] == "gold":
            out[t] = gold
        else:
            r = -s["dur"] * dy + 0.5 * s["dur"] ** 2 * dy ** 2
            r += -s["real_dur"] * dreal + 0.5 * s["real_dur"] ** 2 * dreal ** 2
            r += -s["ig_sd"] * dig - s["hy_sd"] * dhy
            out[t] = r
    return pd.Series(out)


def run_scenarios(weights: dict[str, pd.Series], sens: pd.DataFrame, implied: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    tot, contrib = [], []
    for name, sc in config.SCENARIOS.items():
        r = shock_returns(sens, implied, **sc)
        for code, w in weights.items():
            w = w[w > 1e-9]
            c = w * r.reindex(w.index).fillna(0.0)
            tot.append({"scenario": name, "code": code, "return": float(c.sum())})
            for seg, v in c.groupby(seg_of).sum().items():
                contrib.append({"scenario": name, "code": code, "segment": seg, "contrib": float(v)})
    return pd.DataFrame(tot), pd.DataFrame(contrib)
