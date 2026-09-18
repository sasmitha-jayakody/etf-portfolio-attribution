"""Performance attribution.

1. Brinson-Fachler (daily, Carino-linked) by segment:
       allocation_s  = (wp_s - wb_s) * (Rb_s - Rb)
       selection_s   = wb_s * (Rp_s - Rb_s)
       interaction_s = (wp_s - wb_s) * (Rp_s - Rb_s)
   Segment benchmark returns come from a reference ETF per segment. The
   benchmark's regional equity weights are estimated each month by returns-
   based style analysis of ACWI on IVV / IEFA / IEMG, so allocation can be
   measured by region. Two extra terms close the identity exactly:
       costs     = net - gross portfolio return
       residual  = composite benchmark - actual ACWI/AGG benchmark
2. Returns-based factor attribution (weekly OLS on ETF long/short factors):
   return contribution beta_k * mean(f_k) and Euler risk shares.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from . import config
from .backtest import BacktestResult


# --------------------------------------------------------------------- style analysis
def style_weights(target: pd.Series, styles: pd.DataFrame) -> pd.Series:
    """Sharpe (1992) style analysis: min ||target - styles @ w||, w >= 0, sum w = 1."""
    df = pd.concat([target, styles], axis=1).dropna()
    y = df.iloc[:, 0].to_numpy()
    X = df.iloc[:, 1:].to_numpy()
    # enforce sum-to-one with a heavily weighted extra row, then NNLS
    lam = 1e3
    Xa = np.vstack([X, lam * np.ones(X.shape[1])])
    ya = np.append(y, lam)
    w, _ = nnls(Xa, ya)
    w = w / w.sum()
    return pd.Series(w, index=styles.columns)


def acwi_regional_weights(returns: pd.DataFrame, dates: pd.DatetimeIndex, window: int = 126) -> pd.DataFrame:
    """Monthly style-analysis estimate of ACWI's US / Dev ex-US / EM mix, forward-filled daily."""
    styles = returns[["IVV", "IEFA", "IEMG"]].copy()
    # before IEFA/IEMG existed use EFA/EEM
    styles["IEFA"] = styles["IEFA"].fillna(returns.get("EFA"))
    styles["IEMG"] = styles["IEMG"].fillna(returns.get("EEM"))
    month_ends = pd.Series(dates, index=dates).groupby(dates.to_period("M")).max()
    rows = {}
    for d in month_ends:
        hist = returns.loc[:d, "ACWI"].dropna().iloc[-window:]
        rows[d] = style_weights(hist, styles.loc[hist.index])
    est = pd.DataFrame(rows).T
    est.columns = ["US Equity", "Dev ex-US Equity", "EM Equity"]
    # weights estimated at month end t apply from the next day
    return est.shift(1).reindex(dates, method="ffill").bfill()


# --------------------------------------------------------------------- Brinson
def segment_frame(bod_weights: pd.DataFrame, returns: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Segment weights and segment returns from ETF-level weights."""
    R = returns.reindex(index=bod_weights.index, columns=bod_weights.columns).fillna(0.0)
    seg = pd.Series({t: config.SEGMENT_OF[t] for t in bod_weights.columns})
    ws = bod_weights.T.groupby(seg).sum().T
    contrib = (bod_weights * R).T.groupby(seg).sum().T
    rs = contrib / ws.replace(0, np.nan)
    return ws.reindex(columns=config.SEGMENT_ORDER, fill_value=0.0), rs.reindex(columns=config.SEGMENT_ORDER)


def benchmark_segments(bench: BacktestResult, acwi_mix: pd.DataFrame) -> pd.DataFrame:
    w = bench.bod_weights
    out = pd.DataFrame(0.0, index=w.index, columns=config.SEGMENT_ORDER)
    for s in ["US Equity", "Dev ex-US Equity", "EM Equity"]:
        out[s] = w["ACWI"] * acwi_mix.loc[w.index, s]
    out["US Aggregate"] = w["AGG"]
    return out


def _carino(rp: pd.Series, rb: pd.Series) -> tuple[pd.Series, float]:
    def k(a, b):
        a, b = np.asarray(a, float), np.asarray(b, float)
        diff = a - b
        with np.errstate(divide="ignore", invalid="ignore"):
            out = (np.log1p(a) - np.log1p(b)) / diff
        return np.where(np.abs(diff) < 1e-12, 1 / (1 + a), out)

    Rp, Rb = (1 + rp).prod() - 1, (1 + rb).prod() - 1
    return pd.Series(k(rp, rb), rp.index), float(k(Rp, Rb))


def brinson(port: BacktestResult, bench: BacktestResult, returns: pd.DataFrame,
            acwi_mix: pd.DataFrame) -> dict[str, pd.DataFrame]:
    idx = port.net.index.intersection(bench.net.index)
    wp, rp_seg = segment_frame(port.bod_weights.loc[idx], returns)
    wb = benchmark_segments(bench, acwi_mix).loc[idx]
    ref = pd.DataFrame({s: returns.loc[idx, t] for s, t in config.SEGMENT_REFERENCE.items()})
    rp_seg = rp_seg.fillna(ref)                    # segments the portfolio does not hold
    rb_comp = (wb * ref).sum(axis=1)
    alloc = (wp - wb).mul(ref.sub(rb_comp, axis=0))
    sel = wb * (rp_seg - ref)
    inter = (wp - wb) * (rp_seg - ref)
    daily = {
        "allocation": alloc, "selection": sel, "interaction": inter,
    }
    cost = port.net.loc[idx] - port.gross.loc[idx]
    resid = rb_comp - bench.net.loc[idx]
    rp_net, rb = port.net.loc[idx], bench.net.loc[idx]

    # identity check: effects + cost + residual == active return, every day
    active = rp_net - rb
    recon = alloc.sum(axis=1) + sel.sum(axis=1) + inter.sum(axis=1) + cost + resid
    assert np.allclose(active, recon, atol=1e-10), "Brinson identity failed"

    seg_rows, tot_rows = [], []
    periods = [("Full period", idx)] + [(str(y), idx[idx.year == y]) for y in sorted(set(idx.year))]
    for label, pidx in periods:
        kt, K = _carino(rp_net.loc[pidx], rb.loc[pidx])
        scale = kt / K
        linked = {name: df.loc[pidx].mul(scale, axis=0).sum() for name, df in daily.items()}
        for s in config.SEGMENT_ORDER:
            seg_rows.append({
                "code": port.code, "period": label, "segment": s,
                "port_weight": float(wp.loc[pidx, s].mean()), "bench_weight": float(wb.loc[pidx, s].mean()),
                "allocation": float(linked["allocation"][s]), "selection": float(linked["selection"][s]),
                "interaction": float(linked["interaction"][s]),
            })
        Rp, Rb = (1 + rp_net.loc[pidx]).prod() - 1, (1 + rb.loc[pidx]).prod() - 1
        tot_rows.append({
            "code": port.code, "period": label,
            "port_return": float(Rp), "bench_return": float(Rb), "active": float(Rp - Rb),
            "allocation": float(linked["allocation"].sum()),
            "selection": float(linked["selection"].sum() + linked["interaction"].sum()),
            "costs": float((cost.loc[pidx] * scale).sum()),
            "bench_residual": float((resid.loc[pidx] * scale).sum()),
        })
    return {"segments": pd.DataFrame(seg_rows), "totals": pd.DataFrame(tot_rows)}


# --------------------------------------------------------------------- factor model
def factor_returns(returns: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for name, (long, short) in config.FACTORS.items():
        if long not in returns:
            continue
        f = returns[long]
        if short is not None:
            f = f - returns[short]
        out[name] = f
    return pd.DataFrame(out)


def to_weekly(daily: pd.DataFrame | pd.Series):
    return (1 + daily).resample("W-FRI").prod(min_count=1) - 1


def ols(y: pd.Series, X: pd.DataFrame) -> dict:
    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    Y = df["y"].to_numpy()
    Xm = np.column_stack([np.ones(len(df)), df[X.columns].to_numpy()])
    beta, *_ = np.linalg.lstsq(Xm, Y, rcond=None)
    resid = Y - Xm @ beta
    n, k = Xm.shape
    s2 = resid @ resid / (n - k)
    cov = s2 * np.linalg.inv(Xm.T @ Xm)
    se = np.sqrt(np.diag(cov))
    r2 = 1 - resid.var() / Y.var()
    return {
        "alpha": beta[0], "betas": pd.Series(beta[1:], X.columns), "t": pd.Series(beta[1:] / se[1:], X.columns),
        "alpha_t": beta[0] / se[0], "r2": r2, "resid_var": resid.var(ddof=k), "n": n,
        "X": df[X.columns], "y": df["y"],
    }


def factor_attribution(r: pd.Series, rf: pd.Series, factors: pd.DataFrame, bench: pd.Series | None = None) -> dict:
    """Weekly regression of excess (or active, if bench given) returns on factors."""
    if bench is None:
        y_d = r - rf.reindex(r.index).fillna(0.0)
    else:
        y_d = r - bench.reindex(r.index)
    y = to_weekly(y_d)
    X = to_weekly(factors.loc[r.index])
    res = ols(y, X)
    b = res["betas"]
    fmean = res["X"].mean()
    ret_contrib = b * fmean * 52
    Sf = res["X"].cov()
    total_var = res["y"].var()
    risk_contrib = b * (Sf @ b) / total_var
    table = pd.DataFrame({
        "beta": b, "t_stat": res["t"], "factor_ann_return": fmean * 52,
        "return_contrib": ret_contrib, "risk_share": risk_contrib,
    })
    table.loc["Alpha / residual", ["return_contrib", "risk_share"]] = [
        res["alpha"] * 52, res["resid_var"] / total_var]
    return {"table": table, "r2": res["r2"], "alpha_ann": res["alpha"] * 52, "alpha_t": res["alpha_t"],
            "mean_ann": res["y"].mean() * 52, "n": res["n"]}


def rolling_betas(r: pd.Series, rf: pd.Series, factors: pd.DataFrame, cols: list[str], window: int = 52) -> pd.DataFrame:
    y = to_weekly(r - rf.reindex(r.index).fillna(0.0))
    X = to_weekly(factors.loc[r.index, cols])
    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    out = {}
    for i in range(window, len(df) + 1, 4):
        sub = df.iloc[i - window:i]
        Xm = np.column_stack([np.ones(window), sub[cols].to_numpy()])
        beta, *_ = np.linalg.lstsq(Xm, sub["y"].to_numpy(), rcond=None)
        out[sub.index[-1]] = beta[1:]
    return pd.DataFrame(out, index=cols).T
