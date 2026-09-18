import numpy as np
import pandas as pd
import pytest

from portfolio_lab import attribution, backtest, config, metrics, stress
from portfolio_lab.config import PortfolioSpec, RebalanceRule
from portfolio_lab.data_fetch import parse_ishares_holdings
from portfolio_lab.optimizer import ledoit_wolf, min_variance, risk_contributions


def _rets(n=600, k=4, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    base = rng.standard_normal((n, 1)) * 0.01
    X = base + rng.standard_normal((n, k)) * np.array([0.002, 0.01, 0.015, 0.004])[:k]
    return pd.DataFrame(X, idx, ["A", "B", "C", "D"][:k])


def test_ledoit_wolf_is_valid_covariance():
    cov, delta = ledoit_wolf(_rets())
    assert 0 <= delta <= 1
    assert np.all(np.linalg.eigvalsh(cov.to_numpy()) > 0)
    assert np.allclose(cov, cov.T)


def test_min_variance_constraints():
    cov, _ = ledoit_wolf(_rets())
    w = min_variance(cov, max_weight=0.4, group_min={"g": (["B", "C"], 0.3)})
    assert abs(w.sum() - 1) < 1e-8
    assert (w >= -1e-10).all() and (w <= 0.4 + 1e-8).all()
    assert w[["B", "C"]].sum() >= 0.3 - 1e-6


def test_risk_contributions_sum_to_vol():
    cov, _ = ledoit_wolf(_rets())
    w = pd.Series([0.25] * 4, cov.index)
    rc = risk_contributions(w, cov)
    assert np.isclose(rc["ctr"].sum(), np.sqrt(w @ cov @ w))
    assert np.isclose(rc["pct"].sum(), 1.0)


def _toy_returns():
    idx = pd.bdate_range("2021-01-01", periods=300)
    rng = np.random.default_rng(1)
    r = pd.DataFrame({"IVV": rng.normal(0.0008, 0.01, 300), "AGG": rng.normal(0.0001, 0.003, 300)}, idx)
    return r


def test_buy_and_hold_matches_analytic():
    r = _toy_returns()
    spec = PortfolioSpec("T", "t", "static", RebalanceRule(None, None), weights={"IVV": 0.6, "AGG": 0.4})
    res = backtest.run_backtest(spec, r, pd.Series({"IVV": 1.0, "AGG": 1.0}), start=r.index[0])
    growth = (1 + r.iloc[1:]).prod()
    analytic = 0.6 * growth["IVV"] + 0.4 * growth["AGG"]
    assert np.isclose(res.nav.iloc[-1], analytic)
    assert res.turnover.sum() == 0 and res.cost.sum() == 0


def test_costs_equal_bps_times_traded():
    r = _toy_returns()
    spec = PortfolioSpec("T", "t", "static", RebalanceRule("M", None), weights={"IVV": 0.6, "AGG": 0.4})
    res = backtest.run_backtest(spec, r, pd.Series({"IVV": 10.0, "AGG": 10.0}), start=r.index[0])
    # with equal cost rates, cost = 2 * one-way turnover * 10bp
    assert np.isclose(res.cost.sum(), 2 * res.turnover.sum() * 10 / 1e4)
    assert (res.turnover > 0).sum() >= 12


def test_wide_band_never_trades():
    r = _toy_returns()
    spec = PortfolioSpec("T", "t", "static", RebalanceRule("Q", 0.5), weights={"IVV": 0.6, "AGG": 0.4})
    res = backtest.run_backtest(spec, r, pd.Series({"IVV": 1.0, "AGG": 1.0}), start=r.index[0])
    assert res.turnover.sum() == 0


def test_max_drawdown_known_path():
    r = pd.Series([0.1, -0.5, 0.2, 1.0], pd.bdate_range("2020-01-01", periods=4))
    mdd = metrics.max_drawdown(r)
    assert np.isclose(mdd["max_dd"], -0.5)
    assert mdd["recovery"] == r.index[3]


def test_style_analysis_recovers_mix():
    rng = np.random.default_rng(3)
    S = pd.DataFrame(rng.normal(0, 0.01, (500, 3)), columns=["a", "b", "c"])
    y = S @ np.array([0.6, 0.3, 0.1]) + rng.normal(0, 1e-4, 500)
    w = attribution.style_weights(y, S)
    assert np.allclose(w, [0.6, 0.3, 0.1], atol=0.01)


def test_carino_linking_is_additive():
    rng = np.random.default_rng(4)
    rp = pd.Series(rng.normal(0.001, 0.01, 250))
    rb = pd.Series(rng.normal(0.0005, 0.01, 250))
    kt, K = attribution._carino(rp, rb)
    linked = ((rp - rb) * kt / K).sum()
    assert np.isclose(linked, (1 + rp).prod() - (1 + rb).prod())


def test_bond_shock_signs():
    sens = pd.DataFrame(
        {"kind": ["bond", "bond", "equity"], "beta_eq": [0, 0, 1.0], "beta_usd": [0, 0, -0.5],
         "dur": [6.0, 0.0, 0], "real_dur": [0.0, 6.0, 0], "ig_sd": [0, 0, 0], "hy_sd": [0, 0, 0]},
        index=["IEF", "TIP", "IEFA"])
    imp = {"eq_per_1pp_rates": 0.0, "eq_per_usd": 0.0}
    up = stress.shock_returns(sens, imp, rates=1.0)
    assert up["IEF"] < -0.055 and up["TIP"] < -0.055
    infl = stress.shock_returns(sens, imp, rates=1.0, breakeven=1.0)
    assert np.isclose(infl["TIP"], 0.0)          # real yields unchanged
    usd = stress.shock_returns(sens, imp, usd=0.10)
    assert np.isclose(usd["IEFA"], -0.05)
    zero = stress.shock_returns(sens, imp)
    assert np.allclose(zero, 0.0)


SAMPLE = '''﻿iShares Core MSCI EAFE ETF
Fund Holdings as of,"Sep 10, 2026"
Inception Date,"Oct 18, 2012"

Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,Quantity,Price,Location,Exchange,Currency,FX Rate,Market Currency,Accrual Date
"ASML","ASML HOLDING NV","Information Technology","Equity","1,000.00","2.10","1,000.00","1.00","1.00","Netherlands","Euronext Amsterdam","EUR","1.10","EUR","-"
"7203","TOYOTA MOTOR CORP","Consumer Discretionary","Equity","900.00","1.20","900.00","1.00","1.00","Japan","Tokyo Stock Exchange","JPY","0.007","JPY","-"

"The content contained herein is owned or licensed by BlackRock"
'''


def test_parse_ishares_holdings():
    h = parse_ishares_holdings(SAMPLE, "IEFA")
    assert list(h["ticker"]) == ["ASML", "7203"]
    assert h["as_of"].iloc[0] == "2026-09-10"
    assert np.isclose(h["weight"].sum(), 3.3)
    assert set(h["currency"]) == {"EUR", "JPY"}


def test_pipeline_runs_on_synthetic_data(tmp_path):
    from portfolio_lab import db, pipeline, synthetic
    path = tmp_path / "syn.db"
    with db.session(path) as con:
        synthetic.write_to_db(con, start="2011-01-03", end="2016-12-30")
    out = pipeline.run(path, verbose=False)
    assert out["synthetic"]
    s = out["tables"]["res_summary"].set_index("code")
    assert set(s.index) == {"BENCH", "SAA", "MINVAR", "QV"}
    assert s.loc["BENCH", "tracking_error"] == 0
    tot = out["tables"]["res_brinson_totals"]
    parts = tot[["allocation", "selection", "costs", "bench_residual"]].sum(axis=1)
    assert np.allclose(parts, tot["active"], atol=1e-9)


def test_reports_and_dashboard_build(tmp_path):
    """The Excel workbook, figures, results database and HTML dashboard all build."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    from portfolio_lab import db, pipeline, reports, synthetic

    path = tmp_path / "syn.db"
    with db.session(path) as con:
        synthetic.write_to_db(con, start="2011-01-03", end="2016-12-30")
    pipeline.run(path, verbose=False)
    R = reports.read_results(path)
    assert reports.export_results_db(path, tmp_path / "results.db").exists()
    assert reports.build_excel(R, tmp_path / "book.xlsx").exists()
    payload = json.loads(reports.dashboard_json(R, tmp_path / "d.json").read_text())
    assert payload["meta"]["data"] == "SYNTHETIC"
    assert len(payload["nav"]["SAA"]["dates"]) > 100

    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "dashboard.html"
    subprocess.run([sys.executable, str(root / "scripts" / "build_dashboard.py"),
                    "--db", str(path), "--out", str(out)], check=True, capture_output=True)
    html = out.read_text(encoding="utf-8")
    assert "__DATA__" not in html and "__CHARTS__" not in html and "__METHOD__" not in html
    assert "class LineChart" in html and "</script>" in html
