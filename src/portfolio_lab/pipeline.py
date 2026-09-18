"""End-to-end pipeline: prices in SQLite -> backtests -> analytics -> res_* tables."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import attribution, backtest, config, db, exposures, metrics, stress
from .optimizer import ledoit_wolf, risk_contributions

SUB_PERIODS = [
    ("2013-2019: low rates", "2013-08-01", "2019-12-31"),
    ("2020-2021: COVID & recovery", "2020-01-01", "2021-12-31"),
    ("2022: inflation shock", "2022-01-01", "2022-12-31"),
    ("2023-2026: higher for longer", "2023-01-01", None),
]


def _long_weights(res: backtest.BacktestResult, freq: str = "ME") -> pd.DataFrame:
    w = res.weights.resample(freq).last()
    out = w.stack().rename("weight").reset_index()
    out.columns = ["date", "ticker", "weight"]
    out["code"] = res.code
    return out


def run(db_path=None, verbose: bool = True) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    con = db.connect(db_path)
    db.write_universe(con)
    uni = db.load_universe().set_index("ticker")
    prices = db.read_prices(con)
    if prices.empty:
        raise SystemExit("No prices in the database. Run scripts/fetch_data.py first.")
    macro = db.read_macro(con)
    fl = pd.read_sql("SELECT item FROM fetch_log", con)
    synthetic = bool((fl["item"] == "synthetic").any())
    rets = backtest.to_returns(prices)
    rf = rets[config.RISK_FREE].fillna(0.0)
    log(f"Prices: {prices.shape[1]} tickers, {prices.index[0].date()} -> {prices.index[-1].date()}"
        + ("  [SYNTHETIC DATA]" if synthetic else ""))

    # ---------------------------------------------------------------- backtests
    results = backtest.run_all(rets, uni["cost_bps"])
    bench = results["BENCH"]
    codes = list(results)
    log("Backtests done: " + ", ".join(f"{c} ({r.rule})" for c, r in results.items()))

    summ = []
    for c, r in results.items():
        s = metrics.summary(r.net, bench.net, rf, r.turnover, r.cost, r.gross)
        s.update(code=c, name=r.name, rule=r.rule)
        summ.append(s)
    summary = pd.DataFrame(summ)

    per = []
    for label, a, b in SUB_PERIODS:
        for c, r in results.items():
            x = r.net.loc[a:b]
            if len(x) < 60:
                continue
            per.append({"period": label, "code": c, "cagr": metrics.cagr(x), "vol": metrics.ann_vol(x),
                        "sharpe": metrics.sharpe(x, rf), "max_dd": metrics.max_drawdown(x)["max_dd"],
                        "excess_cagr": metrics.cagr(x) - metrics.cagr(bench.net.loc[x.index])})
    periods = pd.DataFrame(per)

    nav = pd.DataFrame({c: r.nav for c, r in results.items()})
    dd = nav / nav.cummax() - 1
    nav_long = nav.stack().rename("nav").reset_index()
    nav_long.columns = ["date", "code", "nav"]
    nav_long["drawdown"] = dd.stack().to_numpy()
    cal = metrics.calendar_returns({c: r.net for c, r in results.items()})
    cal.index = cal.index.year
    cal_long = cal.stack().rename("return").reset_index()
    cal_long.columns = ["year", "code", "return"]

    weights_long = pd.concat([_long_weights(r) for r in results.values()], ignore_index=True)
    turnover_year = pd.DataFrame({c: r.turnover.groupby(r.turnover.index.year).sum() for c, r in results.items()})
    cost_year = pd.DataFrame({c: r.cost.groupby(r.cost.index.year).sum() * 1e4 for c, r in results.items()})
    ty = turnover_year.stack().rename("turnover").reset_index()
    ty.columns = ["year", "code", "turnover"]
    ty["cost_bps"] = cost_year.stack().to_numpy()

    # ---------------------------------------------------------------- rebalancing & costs
    study = []
    for rule in config.REBALANCE_STUDY:
        r = backtest.run_backtest(config.PORTFOLIOS["SAA"], rets, uni["cost_bps"], rule=rule)
        s = metrics.summary(r.net, bench.net, rf, r.turnover, r.cost, r.gross)
        study.append({"rule": rule.describe(), "cagr": s["cagr"], "vol": s["vol"], "sharpe": s["sharpe"],
                      "max_dd": s["max_dd"], "tracking_error": s["tracking_error"],
                      "turnover_ann": s["turnover_ann"], "n_rebalances": s["n_rebalances"],
                      "cost_bps_ann": s["cost_bps_ann"], "base_case": rule.describe() == results["SAA"].rule})
    rebal = pd.DataFrame(study)
    sens_rows = []
    for c in ("SAA", "MINVAR", "QV"):
        for m in config.COST_MULTIPLIERS:
            r = results[c] if m == 1.0 else backtest.run_backtest(config.PORTFOLIOS[c], rets, uni["cost_bps"], cost_mult=m)
            sens_rows.append({"code": c, "cost_multiplier": m, "cagr": metrics.cagr(r.net),
                              "sharpe": metrics.sharpe(r.net, rf), "cost_bps_ann": r.cost.sum() / (len(r.net) / 252) * 1e4})
    cost_sens = pd.DataFrame(sens_rows)
    log("Rebalancing study and cost sensitivity done")

    # ---------------------------------------------------------------- exposures
    fx = exposures.fund_exposures(con)
    bc = exposures.bond_characteristics(con)
    current = {c: r.weights.iloc[-1] for c, r in results.items()}
    exp_rows, dur_rows = [], []
    for c, w in current.items():
        for dim in ("sector", "country", "currency"):
            for k, v in exposures.look_through(w, fx, dim).items():
                exp_rows.append({"code": c, "dimension": dim, "bucket": k, "weight": float(v)})
        seg = w.groupby(stress.seg_of).sum()
        for k, v in seg.items():
            exp_rows.append({"code": c, "dimension": "segment", "bucket": k, "weight": float(v)})
        d = exposures.duration_profile(w, bc)
        d["code"] = c
        dur_rows.append(d)
    hold = pd.read_sql("SELECT * FROM holdings", con) if db.table_exists(con, "holdings") else pd.DataFrame()
    top_rows = []
    for c, w in current.items():
        t = exposures.look_through_holdings(w, hold)
        if len(t):
            top_rows.append(t.assign(code=c, rank=range(1, len(t) + 1)))
    top_holdings = pd.concat(top_rows, ignore_index=True) if top_rows else pd.DataFrame(
        columns=["name", "ticker", "weight", "via", "code", "rank"])
    expo = pd.DataFrame(exp_rows)
    dur = pd.DataFrame(dur_rows)
    fx_source = fx.groupby(["fund", "dimension"])["source"].first().unstack()

    # ---------------------------------------------------------------- attribution
    acwi_mix = attribution.acwi_regional_weights(rets, bench.net.index)
    br_seg, br_tot = [], []
    for c in ("SAA", "MINVAR", "QV"):
        b = attribution.brinson(results[c], bench, rets, acwi_mix)
        br_seg.append(b["segments"])
        br_tot.append(b["totals"])
    br_seg = pd.concat(br_seg, ignore_index=True)
    br_tot = pd.concat(br_tot, ignore_index=True)
    log("Brinson attribution done (identity check passed)")

    facs = attribution.factor_returns(rets)
    f_rows, f_meta, roll_rows = [], [], []
    for c, r in results.items():
        for mode in ("absolute", "active"):
            if mode == "active" and c == "BENCH":
                continue
            fa = attribution.factor_attribution(r.net, rf, facs, bench.net if mode == "active" else None)
            t = fa["table"].reset_index().rename(columns={"index": "factor"})
            t["code"], t["mode"] = c, mode
            f_rows.append(t)
            f_meta.append({"code": c, "mode": mode, "r2": fa["r2"], "alpha_ann": fa["alpha_ann"],
                           "alpha_t": fa["alpha_t"], "mean_ann": fa["mean_ann"], "n_weeks": fa["n"]})
        rb = attribution.rolling_betas(r.net, rf, facs, ["Equity", "Rates", "Value", "Quality", "USD"])
        rbl = rb.stack().rename("beta").reset_index()
        rbl.columns = ["date", "factor", "beta"]
        rbl["code"] = c
        roll_rows.append(rbl)
    factor_tbl = pd.concat(f_rows, ignore_index=True)
    factor_meta = pd.DataFrame(f_meta)
    factor_roll = pd.concat(roll_rows, ignore_index=True)
    log("Factor attribution done")

    # ---------------------------------------------------------------- ex-ante risk
    rc_rows = []
    for c, w in current.items():
        for label, window in (("1y", 252), ("full", None)):
            hist = rets.loc[bench.net.index, w.index]
            hist = hist.iloc[-window:] if window else hist
            cov, _ = ledoit_wolf(hist)
            rc = risk_contributions(w, cov * 252)
            for t, row in rc.iterrows():
                rc_rows.append({"code": c, "window": label, "ticker": t, "segment": stress.seg_of(t),
                                "weight": row["weight"], "ctr": row["ctr"], "pct_risk": row["pct"]})
    risk_contrib = pd.DataFrame(rc_rows)

    # ---------------------------------------------------------------- stress
    realised = {c: r.net for c, r in results.items()}
    replay = stress.historical_replay(current, rets, realised)
    sens, implied = stress.sensitivities(rets, macro, bc)
    scen, scen_contrib = stress.run_scenarios(current, sens, implied)
    win_contrib = []
    for name, a, b in config.STRESS_WINDOWS:
        for c, w in current.items():
            try:
                for seg, v in stress.window_contributions(w, rets, a, b).items():
                    win_contrib.append({"window": name, "code": c, "segment": seg, "contrib": float(v)})
            except KeyError:
                pass
    win_contrib = pd.DataFrame(win_contrib)
    log("Stress tests done")

    # ---------------------------------------------------------------- rolling
    roll = {}
    for c, r in results.items():
        roll[(c, "vol_63d")] = metrics.rolling_vol(r.net, 63)
        if c != "BENCH":
            roll[(c, "te_252d")] = metrics.rolling_te(r.net, bench.net, 252)
    roll_df = pd.DataFrame(roll).resample("W-FRI").last()
    roll_long = roll_df.stack(level=[0, 1], future_stack=True).rename("value").reset_index()
    roll_long.columns = ["date", "code", "metric", "value"]
    sb = rets["IVV"].rolling(126).corr(rets["AGG"]).resample("W-FRI").last().loc[config.BACKTEST_START:]
    sb = sb.rename("value").reset_index()
    sb.columns = ["date", "value"]

    # ---------------------------------------------------------------- write
    meta = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data": "SYNTHETIC" if synthetic else "Yahoo Finance / FRED / iShares",
        "prices_end": str(prices.index[-1].date()),
        "backtest_start": str(bench.net.index[0].date()),
        "backtest_end": str(bench.net.index[-1].date()),
        "implied_eq_per_1pp_rates": implied["eq_per_1pp_rates"],
        "implied_eq_per_usd": implied["eq_per_usd"],
        "holdings_as_of": json.dumps(fx.dropna(subset=["as_of"]).groupby("fund")["as_of"].max().to_dict()),
        "portfolios": json.dumps({c: {"name": s.name, "description": s.description, "rule": results[c].rule,
                                      "weights": s.weights, "universe": s.universe}
                                  for c, s in config.PORTFOLIOS.items()}),
    }
    tables = {
        "res_meta": pd.DataFrame(list(meta.items()), columns=["key", "value"]),
        "res_summary": summary,
        "res_periods": periods,
        "res_nav": nav_long,
        "res_calendar": cal_long,
        "res_weights": weights_long,
        "res_turnover_year": ty,
        "res_rebalance_study": rebal,
        "res_cost_sensitivity": cost_sens,
        "res_exposures": expo,
        "res_top_holdings": top_holdings,
        "res_duration": dur,
        "res_exposure_sources": fx_source.reset_index(),
        "res_bond_characteristics": bc.reset_index().rename(columns={"index": "fund"}),
        "res_brinson_segments": br_seg,
        "res_brinson_totals": br_tot,
        "res_factor": factor_tbl,
        "res_factor_meta": factor_meta,
        "res_factor_rolling": factor_roll,
        "res_risk_contrib": risk_contrib,
        "res_stress_replay": replay,
        "res_stress_window_contrib": win_contrib,
        "res_stress_scenarios": scen,
        "res_stress_contrib": scen_contrib,
        "res_sensitivities": sens.reset_index(),
        "res_rolling": roll_long,
        "res_stock_bond_corr": sb,
        "res_acwi_mix": acwi_mix.resample("ME").last().reset_index().rename(columns={"index": "date"}),
    }
    for name, df in tables.items():
        df = df.copy()
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d")
        db.write_frame(con, name, df)
    con.commit()
    con.close()
    log(f"Wrote {len(tables)} result tables to {db_path or db.DEFAULT_DB}")
    return {"results": results, "tables": tables, "synthetic": synthetic}
