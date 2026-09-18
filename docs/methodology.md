# Methodology

**Universe.** Fourteen US-listed iShares ETFs, USD, total return (dividends reinvested, net of
fund fees). Equity: IVV (S&P 500), IEFA (developed ex-US), IEMG (emerging), QUAL and VLUE (MSCI
USA Quality and Value factor). Bonds: AGG, TIP, IEF, TLT, SHY, LQD, HYG, EMB. Real assets: IAU
(gold). Cash: SHV. Prices, Treasury yields, breakevens and CPI come from Yahoo Finance and FRED;
holdings, sectors, countries, currencies and durations come from the iShares holdings files. All
of it lands in one SQLite database.

**Window.** Daily data from 2003; the backtest starts 2013-08-01, the first full month after
QUAL listed, so all four portfolios run on the same days. It covers 2015-16, Q4 2018, COVID,
2022, 2023 and April 2025. The 2008 crisis sits before the window and is handled by stress
replay with proxies, not by the backtest.

**Portfolios.**

| Portfolio | Construction | Rebalancing |
|---|---|---|
| Benchmark 60/40 | 60% ACWI, 40% AGG | monthly, no costs |
| Strategic 60/40 | IVV 36, IEFA 16, IEMG 8, AGG 32, TIP 8 | quarterly check, trade only if a sleeve is >2.5pp from target |
| Minimum Variance | long-only min-variance over 11 ETFs, Ledoit-Wolf shrunk covariance on 252 days, max 25% per ETF, equities >= 20% | monthly re-optimisation, no trade if the new target is within 1pp |
| Quality-Value | the strategic portfolio with its 36% US equity sleeve split 50/50 QUAL/VLUE | same as strategic |

The strategic and quality-value portfolios differ **only** in the US equity sleeve, so the gap
between them is a factor effect and nothing else.

**Backtest mechanics.** Weights drift daily with returns. Targets are computed from data up to a
signal date and executed at the next close (one-day lag, no look-ahead). Trading costs are
one-way basis points per ETF (1bp IVV to 5bp VLUE, covering half-spread and impact), charged on
the weight actually traded. Turnover is one-way: half the sum of absolute weight changes. Fund
fees are already inside total returns. Cash return is SHV; it is also the risk-free rate in
Sharpe ratios.

**Risk.** Volatility, Sharpe, Sortino, maximum drawdown and recovery, tracking error and
information ratio versus the benchmark, beta, up/down capture, historical VaR and CVaR at 95%.
Ex-ante risk contributions use a Ledoit-Wolf covariance matrix and Euler decomposition, so each
holding's contribution sums to portfolio volatility.

**Exposures.** Look-through: portfolio weight × each fund's holdings gives sector (GICS for
equity, issuer type for bonds), country of risk and market currency. Duration comes from the
per-bond durations in the iShares files, weighted up to the fund and then to the portfolio;
TIPS duration is treated as real duration and reported separately. Spread duration is duration
× the fund's credit share.

**Attribution.** Brinson-Fachler by segment, daily, Carino-linked: allocation is
(portfolio weight − benchmark weight) × (segment benchmark return − total benchmark return);
selection is benchmark weight × (segment portfolio return − segment benchmark return);
interaction is reported with selection. Segment benchmark returns use a reference ETF per
segment (IVV, IEFA, IEMG, AGG, TIP, IEF, LQD, IAU, SHV). The benchmark's own regional mix is
estimated monthly by returns-based style analysis (Sharpe 1992) of ACWI on IVV/IEFA/IEMG, so
allocation can be measured region by region. Two terms close the identity exactly: trading
costs, and a benchmark residual (ACWI/AGG versus the composite, fees, small caps, Canada).
Effects sum to the active return every single day before linking.

**Factor model.** Weekly OLS of excess (and active) returns on ten ETF-built factors: equity
(ACWI−SHV), size (IWM−IVV), value (IWD−IWF), quality (QUAL−IVV), momentum (MTUM−IVV), rates
(IEF−SHV), credit (LQD−IEF), inflation (TIP−IEF), dollar (UUP), gold (IAU−SHV). Return
contribution is beta × the factor's realised premium; risk shares are the Euler decomposition
of regression variance, with the residual shown as specific risk.

**Stress tests.** Two kinds. *Historical replay* holds today's weights through nine past
episodes; ETFs that did not exist are proxied (IEFA→EFA, IEMG→EEM, QUAL→IVV, VLUE→IWD,
ACWI→IVV/EFA/EEM, EMB→LQD/HYG) and the proxy share is reported beside the result.
*Hypothetical shocks* are instantaneous: bonds by −D·Δy plus convexity plus spread duration ×
spread change (TIPS on real yields, Δreal = Δnominal − Δbreakeven); equities by their 3-year
weekly betas to ACWI and to the dollar; gold by assumption. Scenarios that specify no equity
move imply one from ACWI's own regression on 10y yield changes and the dollar.

**What this is not.** A backtest of fixed rules on ETF price history, not live performance. It
ignores taxes, securities lending, bid-ask variation through time, cash drag and capacity, and
it uses one holdings snapshot for look-through exposures. Every ETF here still exists, so
survivorship is not an issue, but the factor ETFs were chosen with hindsight about which
factors are interesting.
