"""Performance and risk statistics on daily return series."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import TRADING_DAYS as N


def cagr(r: pd.Series) -> float:
    r = r.dropna()
    return float((1 + r).prod() ** (N / len(r)) - 1) if len(r) else np.nan


def ann_vol(r: pd.Series) -> float:
    return float(r.std(ddof=1) * np.sqrt(N))


def sharpe(r: pd.Series, rf: pd.Series) -> float:
    ex = (r - rf.reindex(r.index).fillna(0.0)).dropna()
    return float(ex.mean() / ex.std(ddof=1) * np.sqrt(N))


def sortino(r: pd.Series, rf: pd.Series) -> float:
    ex = (r - rf.reindex(r.index).fillna(0.0)).dropna()
    downside = np.sqrt((np.minimum(ex, 0) ** 2).mean())
    return float(ex.mean() / downside * np.sqrt(N)) if downside > 0 else np.nan


def drawdown(r: pd.Series) -> pd.Series:
    nav = (1 + r).cumprod()
    return nav / nav.cummax() - 1


def max_drawdown(r: pd.Series) -> dict:
    dd = drawdown(r)
    trough = dd.idxmin()
    nav = (1 + r).cumprod()
    peak = nav.loc[:trough].idxmax()
    after = dd.loc[trough:]
    rec = after[after >= -1e-12]
    recovery = rec.index[0] if len(rec) else None
    return {
        "max_dd": float(dd.min()),
        "peak": peak,
        "trough": trough,
        "recovery": recovery,
        "days_to_recover": (recovery - trough).days if recovery is not None else None,
    }


def tracking_error(r: pd.Series, b: pd.Series) -> float:
    a = (r - b.reindex(r.index)).dropna()
    return float(a.std(ddof=1) * np.sqrt(N))


def information_ratio(r: pd.Series, b: pd.Series) -> float:
    a = (r - b.reindex(r.index)).dropna()
    te = a.std(ddof=1) * np.sqrt(N)
    return float(a.mean() * N / te) if te > 0 else np.nan


def beta(r: pd.Series, b: pd.Series) -> float:
    x = pd.concat([r, b], axis=1).dropna()
    c = np.cov(x.iloc[:, 0], x.iloc[:, 1])
    return float(c[0, 1] / c[1, 1])


def var_cvar(r: pd.Series, level: float = 0.95) -> tuple[float, float]:
    q = r.quantile(1 - level)
    return float(q), float(r[r <= q].mean())


def capture(r: pd.Series, b: pd.Series, freq: str = "ME") -> tuple[float, float]:
    rm = (1 + r).resample(freq).prod() - 1
    bm = (1 + b.reindex(r.index)).resample(freq).prod() - 1
    up, dn = bm > 0, bm < 0
    upc = ((1 + rm[up]).prod() ** (1 / up.sum()) - 1) / ((1 + bm[up]).prod() ** (1 / up.sum()) - 1)
    dnc = ((1 + rm[dn]).prod() ** (1 / dn.sum()) - 1) / ((1 + bm[dn]).prod() ** (1 / dn.sum()) - 1)
    return float(upc), float(dnc)


def summary(r: pd.Series, bench: pd.Series, rf: pd.Series, turnover: pd.Series | None = None,
            cost: pd.Series | None = None, gross: pd.Series | None = None) -> dict:
    mdd = max_drawdown(r)
    v, cv = var_cvar(r)
    up, dn = capture(r, bench)
    monthly = (1 + r).resample("ME").prod() - 1
    years = len(r) / N
    out = {
        "start": r.index[0].date().isoformat(),
        "end": r.index[-1].date().isoformat(),
        "cagr": cagr(r),
        "vol": ann_vol(r),
        "sharpe": sharpe(r, rf),
        "sortino": sortino(r, rf),
        "max_dd": mdd["max_dd"],
        "dd_peak": mdd["peak"].date().isoformat(),
        "dd_trough": mdd["trough"].date().isoformat(),
        "dd_recovery": mdd["recovery"].date().isoformat() if mdd["recovery"] is not None else None,
        "calmar": cagr(r) / abs(mdd["max_dd"]) if mdd["max_dd"] < 0 else np.nan,
        "tracking_error": tracking_error(r, bench),
        "info_ratio": information_ratio(r, bench),
        "excess_cagr": cagr(r) - cagr(bench.reindex(r.index)),
        "beta": beta(r, bench),
        "corr": float(r.corr(bench.reindex(r.index))),
        "var95_daily": v,
        "cvar95_daily": cv,
        "up_capture": up,
        "down_capture": dn,
        "best_month": float(monthly.max()),
        "worst_month": float(monthly.min()),
        "pct_pos_months": float((monthly > 0).mean()),
    }
    if turnover is not None:
        out["turnover_ann"] = float(turnover.sum() / years)
        out["n_rebalances"] = int((turnover > 1e-9).sum())
    if cost is not None:
        out["cost_bps_ann"] = float(cost.sum() / years * 1e4)
    if gross is not None:
        out["gross_cagr"] = cagr(gross)
        out["cost_drag_cagr"] = cagr(gross) - cagr(r)
    return out


def calendar_returns(series: dict[str, pd.Series]) -> pd.DataFrame:
    df = pd.DataFrame(series)
    return (1 + df).resample("YE").prod() - 1


def rolling_vol(r: pd.Series, window: int = 63) -> pd.Series:
    return r.rolling(window).std() * np.sqrt(N)


def rolling_te(r: pd.Series, b: pd.Series, window: int = 252) -> pd.Series:
    return (r - b.reindex(r.index)).rolling(window).std() * np.sqrt(N)
