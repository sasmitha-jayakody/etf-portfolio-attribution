"""Portfolio definitions, rebalancing rules and model settings.

Everything that is a judgement call lives here so it can be read in one place
and changed without touching the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Backtest window. QUAL (the youngest ETF used in a live portfolio) listed on
# 2013-07-16, so the common start is the first full month after that.
BACKTEST_START = "2013-08-01"
RISK_FREE = "SHV"          # 0-1y Treasury ETF, total return, used as cash
BENCHMARK = "BENCH"
TRADE_LAG_DAYS = 1         # signal at close t, trade at close t+1
TRADING_DAYS = 252


@dataclass
class RebalanceRule:
    """When to trade back to target.

    calendar: 'M', 'Q', 'A' or None. Rebalancing is considered on the last
        trading day of each period.
    band: absolute drift trigger in weight units (0.025 = 2.5pp). With a
        calendar, the band is checked only on calendar dates; without one it is
        checked every day.
    """

    calendar: str | None = "Q"
    band: float | None = None
    label: str = ""

    def describe(self) -> str:
        if self.label:
            return self.label
        cal = {"M": "monthly", "Q": "quarterly", "A": "annual", None: "daily check"}[self.calendar]
        if self.band is None:
            return f"{cal} calendar"
        return f"{cal}, {self.band * 100:.1f}pp band"


@dataclass
class PortfolioSpec:
    code: str
    name: str
    kind: str                        # 'static' or 'minvar'
    rule: RebalanceRule
    weights: dict[str, float] = field(default_factory=dict)   # static target
    universe: list[str] = field(default_factory=list)          # minvar assets
    costs: bool = True
    description: str = ""


PORTFOLIOS: dict[str, PortfolioSpec] = {
    "BENCH": PortfolioSpec(
        code="BENCH",
        name="Benchmark 60/40",
        kind="static",
        weights={"ACWI": 0.60, "AGG": 0.40},
        rule=RebalanceRule("M", None),
        costs=False,
        description="60% MSCI ACWI (ACWI) / 40% US Aggregate (AGG), rebalanced monthly, no costs.",
    ),
    "SAA": PortfolioSpec(
        code="SAA",
        name="Strategic 60/40",
        kind="static",
        weights={"IVV": 0.36, "IEFA": 0.16, "IEMG": 0.08, "AGG": 0.32, "TIP": 0.08},
        rule=RebalanceRule("Q", 0.025),
        description=(
            "Core iShares building blocks. Fixed regional split (US 60% of equity), "
            "a TIPS sleeve inside bonds. Quarterly review, trade only if a sleeve is "
            "more than 2.5pp from target."
        ),
    ),
    "MINVAR": PortfolioSpec(
        code="MINVAR",
        name="Minimum Variance",
        kind="minvar",
        universe=["IVV", "IEFA", "IEMG", "AGG", "TIP", "IEF", "TLT", "LQD", "HYG", "EMB", "IAU"],
        rule=RebalanceRule("M", None),
        description=(
            "Long-only minimum variance across 11 ETFs. Ledoit-Wolf shrunk covariance "
            "on 252 trading days, max 25% per ETF, at least 20% in equities. "
            "Re-optimised monthly; trades skipped when the new target is within 1pp."
        ),
    ),
    "QV": PortfolioSpec(
        code="QV",
        name="Quality-Value Factor",
        kind="static",
        weights={"QUAL": 0.18, "VLUE": 0.18, "IEFA": 0.16, "IEMG": 0.08, "AGG": 0.32, "TIP": 0.08},
        rule=RebalanceRule("Q", 0.025),
        description=(
            "Same asset and regional allocation as the strategic portfolio, but the US "
            "equity sleeve is split 50/50 between the MSCI USA Quality and Value factor "
            "ETFs. Any difference versus SAA is therefore a factor effect."
        ),
    ),
}

# Minimum-variance settings
MINVAR_LOOKBACK = 252
MINVAR_MAX_WEIGHT = 0.25
MINVAR_MIN_EQUITY = 0.20
MINVAR_NO_TRADE = 0.01

# Alternative rules tested on the strategic portfolio
REBALANCE_STUDY = [
    RebalanceRule(None, None, "Buy and hold (never)"),
    RebalanceRule("M", None),
    RebalanceRule("Q", None),
    RebalanceRule("A", None),
    RebalanceRule("Q", 0.025),
    RebalanceRule(None, 0.05, "5pp band, checked daily"),
]
COST_MULTIPLIERS = [0.0, 1.0, 3.0, 5.0]

# Attribution segments: ETF -> segment, and the reference ETF used as the
# benchmark return of each segment (Brinson-Fachler).
SEGMENT_OF = {
    "IVV": "US Equity", "QUAL": "US Equity", "VLUE": "US Equity",
    "IEFA": "Dev ex-US Equity", "EFA": "Dev ex-US Equity",
    "IEMG": "EM Equity", "EEM": "EM Equity",
    "AGG": "US Aggregate", "TIP": "TIPS",
    "IEF": "Treasuries", "TLT": "Treasuries", "SHY": "Treasuries",
    "LQD": "Credit", "HYG": "Credit", "EMB": "Credit",
    "IAU": "Gold", "SHV": "Cash",
}
SEGMENT_REFERENCE = {
    "US Equity": "IVV", "Dev ex-US Equity": "IEFA", "EM Equity": "IEMG",
    "US Aggregate": "AGG", "TIPS": "TIP", "Treasuries": "IEF",
    "Credit": "LQD", "Gold": "IAU", "Cash": "SHV",
}
SEGMENT_ORDER = list(SEGMENT_REFERENCE)
ASSET_CLASS_OF_SEGMENT = {
    "US Equity": "Equity", "Dev ex-US Equity": "Equity", "EM Equity": "Equity",
    "US Aggregate": "Fixed Income", "TIPS": "Fixed Income", "Treasuries": "Fixed Income",
    "Credit": "Fixed Income", "Gold": "Real Assets", "Cash": "Cash",
}

# Factor-mimicking returns built from ETFs (long leg, short leg).
FACTORS = {
    "Equity": ("ACWI", "SHV"),
    "Size": ("IWM", "IVV"),
    "Value": ("IWD", "IWF"),
    "Quality": ("QUAL", "IVV"),
    "Momentum": ("MTUM", "IVV"),
    "Rates": ("IEF", "SHV"),
    "Credit": ("LQD", "IEF"),
    "Inflation": ("TIP", "IEF"),
    "USD": ("UUP", None),
    "Gold": ("IAU", "SHV"),
}

# Historical stress windows (peak-to-trough of the relevant market).
STRESS_WINDOWS = [
    ("Global Financial Crisis", "2007-10-09", "2009-03-09"),
    ("US downgrade / euro crisis", "2011-07-22", "2011-10-03"),
    ("Taper tantrum", "2013-05-02", "2013-06-24"),
    ("China deval / oil crash", "2015-08-10", "2016-02-11"),
    ("Q4 2018 selloff", "2018-09-20", "2018-12-24"),
    ("COVID crash", "2020-02-19", "2020-03-23"),
    ("2022 inflation & rate shock", "2022-01-03", "2022-10-12"),
    ("2023 bond rout (10y to 5%)", "2023-07-31", "2023-10-27"),
    ("April 2025 tariff shock", "2025-04-02", "2025-04-08"),
]

# Composite proxies for ETFs that did not exist during early stress windows.
# Used ONLY for historical scenario replay, never in the backtest itself.
STRESS_PROXIES = {
    "IEFA": {"EFA": 1.0},
    "IEMG": {"EEM": 1.0},
    "QUAL": {"IVV": 1.0},
    "VLUE": {"IWD": 1.0},
    "ACWI": {"IVV": 0.55, "EFA": 0.35, "EEM": 0.10},
    "EMB": {"LQD": 0.5, "HYG": 0.5},
    "HYG": {"LQD": 0.5, "IVV": 0.2, "IEF": 0.3},
}

# Hypothetical shocks. Units: rates/breakeven/spreads in percentage points,
# equity/usd/gold as returns. Equity shock is the ACWI move in USD.
SCENARIOS = {
    "Rates +100bp": dict(rates=1.00, breakeven=0.0, equity=None, usd=0.0, ig=0.0, hy=0.0, gold=-0.03),
    "Rates -100bp": dict(rates=-1.00, breakeven=0.0, equity=None, usd=0.0, ig=0.0, hy=0.0, gold=0.03),
    "Inflation shock (2022-style)": dict(rates=1.50, breakeven=0.50, equity=-0.15, usd=0.05, ig=0.50, hy=1.50, gold=-0.05),
    "Stagflation": dict(rates=0.75, breakeven=1.00, equity=-0.15, usd=0.0, ig=0.75, hy=2.50, gold=0.10),
    "Equity drawdown -20%": dict(rates=-0.75, breakeven=-0.25, equity=-0.20, usd=0.05, ig=0.75, hy=2.50, gold=0.05),
    "Equity crash -35% (GFC-like)": dict(rates=-1.25, breakeven=-1.00, equity=-0.35, usd=0.10, ig=2.00, hy=6.00, gold=0.00),
    "USD +10%": dict(rates=0.0, breakeven=0.0, equity=None, usd=0.10, ig=0.0, hy=0.0, gold=-0.08),
    "USD -10%": dict(rates=0.0, breakeven=0.0, equity=None, usd=-0.10, ig=0.0, hy=0.0, gold=0.08),
}
