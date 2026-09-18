"""Daily drift-and-rebalance backtest with transaction costs.

Mechanics
---------
* Weights drift every day with each ETF's total return (adjusted close).
* On a rebalance *signal* date (last trading day of the month/quarter/year,
  or any day for a pure band rule) the target is computed from data up to and
  including that close. Trades execute at the close ``TRADE_LAG_DAYS`` later.
* Trading cost for a day = sum_i |w_target_i - w_drifted_i| * cost_bps_i,
  charged against NAV on the execution day.
* Turnover is one-way: 0.5 * sum_i |dw_i|. Initial construction is not
  charged (every portfolio starts fully invested on day 0).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config
from .config import PortfolioSpec, RebalanceRule
from .optimizer import ledoit_wolf, min_variance

EQUITY_TICKERS = {"IVV", "IEFA", "IEMG", "QUAL", "VLUE", "ACWI", "EFA", "EEM", "USMV", "MTUM", "IWM", "IWD", "IWF"}


def to_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple daily returns from adjusted prices; NaN before each ETF's first price."""
    rets = prices.sort_index().pct_change(fill_method=None)
    return rets.iloc[1:]


@dataclass
class BacktestResult:
    code: str
    name: str
    rule: str
    net: pd.Series            # daily net returns
    gross: pd.Series          # daily returns before costs
    weights: pd.DataFrame     # end-of-day weights (post-trade)
    bod_weights: pd.DataFrame # start-of-day weights (used for attribution)
    turnover: pd.Series       # daily one-way turnover
    cost: pd.Series           # daily cost as a fraction of NAV
    targets: pd.DataFrame     # target weights at each signal date

    @property
    def nav(self) -> pd.Series:
        return (1 + self.net).cumprod()


def signal_dates(index: pd.DatetimeIndex, calendar: str | None) -> pd.DatetimeIndex:
    if calendar is None:
        return index
    freq = {"M": "M", "Q": "Q", "A": "Y"}[calendar]
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(index.to_period(freq)).max().to_numpy())


def _minvar_target(returns: pd.DataFrame, date, universe, prev=None) -> pd.Series:
    hist = returns.loc[:date, universe].dropna().iloc[-config.MINVAR_LOOKBACK:]
    cov, _ = ledoit_wolf(hist)
    eq = [t for t in universe if t in EQUITY_TICKERS]
    x0 = None if prev is None else prev.reindex(universe).fillna(0).to_numpy() + 1e-4
    return min_variance(
        cov,
        max_weight=config.MINVAR_MAX_WEIGHT,
        group_min={"equity": (eq, config.MINVAR_MIN_EQUITY)},
        x0=None if x0 is None else x0 / x0.sum(),
    )


def run_backtest(
    spec: PortfolioSpec,
    returns: pd.DataFrame,
    cost_bps: pd.Series,
    start: str = config.BACKTEST_START,
    end: str | None = None,
    rule: RebalanceRule | None = None,
    cost_mult: float = 1.0,
) -> BacktestResult:
    rule = rule or spec.rule
    assets = list(spec.weights) if spec.kind == "static" else list(spec.universe)
    rets = returns.loc[start:end, assets]
    if rets.iloc[0].isna().any():
        missing = rets.columns[rets.iloc[0].isna()].tolist()
        raise ValueError(f"{spec.code}: no data on {rets.index[0].date()} for {missing}")
    dates = rets.index
    R = rets.fillna(0.0).to_numpy()
    cb = cost_bps.reindex(assets).fillna(5.0).to_numpy() / 1e4 * (cost_mult if spec.costs else 0.0)

    def target_at(date, prev=None) -> np.ndarray:
        if spec.kind == "static":
            return np.array([spec.weights[a] for a in assets], dtype=float)
        return _minvar_target(returns, date, assets, prev).reindex(assets).to_numpy()

    # day 0: invested at target computed from data up to the previous close
    prev_date = returns.index[returns.index.get_loc(dates[0]) - 1]
    tgt = target_at(prev_date)
    w = tgt.copy()
    never = rule.calendar is None and rule.band is None
    sig = set() if never else set(signal_dates(dates, rule.calendar))
    lag = config.TRADE_LAG_DAYS

    n = len(dates)
    W = np.zeros((n, len(assets)))
    BOD = np.zeros((n, len(assets)))
    gross = np.zeros(n)
    cost = np.zeros(n)
    turn = np.zeros(n)
    W[0] = w
    BOD[0] = w
    target_log = {dates[0]: tgt.copy()}
    pending: tuple[int, np.ndarray] | None = None

    for t in range(1, n):
        BOD[t] = w
        r = R[t]
        g = float(w @ r)
        w = w * (1.0 + r) / (1.0 + g)
        gross[t] = g
        if pending is not None and pending[0] == t:
            new = pending[1]
            dw = new - w
            turn[t] = 0.5 * np.abs(dw).sum()
            cost[t] = float(np.abs(dw) @ cb)
            w = new.copy()
            pending = None
        W[t] = w
        d = dates[t]
        if d in sig and t + lag < n:
            if spec.kind == "minvar":
                new_t = target_at(d, pd.Series(tgt, index=assets))
                target_log[d] = new_t
                if np.abs(new_t - w).max() > config.MINVAR_NO_TRADE:
                    tgt = new_t
                    pending = (t + lag, tgt)
            else:
                drift = np.abs(w - tgt).max()
                if rule.band is None or drift > rule.band:
                    pending = (t + lag, tgt)

    net = (1.0 + gross) * (1.0 - cost) - 1.0
    idx = dates
    return BacktestResult(
        code=spec.code,
        name=spec.name,
        rule=rule.describe(),
        net=pd.Series(net, idx, name=spec.code).iloc[1:],
        gross=pd.Series(gross, idx, name=spec.code).iloc[1:],
        weights=pd.DataFrame(W, idx, assets),
        bod_weights=pd.DataFrame(BOD, idx, assets).iloc[1:],
        turnover=pd.Series(turn, idx).iloc[1:],
        cost=pd.Series(cost, idx).iloc[1:],
        targets=pd.DataFrame(target_log, index=assets).T,
    )


def run_all(returns: pd.DataFrame, cost_bps: pd.Series, end: str | None = None) -> dict[str, BacktestResult]:
    return {code: run_backtest(spec, returns, cost_bps, end=end) for code, spec in config.PORTFOLIOS.items()}
