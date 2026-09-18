# Three ways to build a 60/40, and what actually made the difference

Backtest: 2 August 2013 to 11 September 2026, daily, USD, net of trading costs. Benchmark is 60% MSCI ACWI (ACWI) and 40% US Aggregate (AGG), rebalanced monthly.

!!! Strategic 60/40 | 8.1% p.a.
!!! Quality-Value | 7.8% p.a.
!!! Benchmark 60/40 | 7.5% p.a.
!!! Minimum Variance | 4.0% p.a.

## Which portfolio performed best

The strategic 60/40 finished ahead: 8.06% a year against the benchmark's 7.53%, with the same volatility (10.1%), a Sharpe of 0.64 against 0.59, and an information ratio of 0.58 on 0.83% tracking error. Over thirteen years that is 17.0 percentage points of cumulative outperformance. Hold it loosely. An information ratio of 0.58 over 13.1 years is a t of about 2.1, which clears the usual bar and not much more, and the next section shows where all of it came from: one asset allocation stance, set at the start and never revisited. Run the same stance through a decade where bonds beat equities and the table looks very different.

The quality-value version finished at 7.83%. It beat the benchmark but lost to the plain strategic portfolio by 0.23% a year, which is the whole point of building the two to be identical everywhere except the US equity sleeve.

Minimum variance did exactly what it says: 5.4% volatility, a bit over half the benchmark's, and a beta of 0.42. It also returned 3.98% a year, so it gave up 3.5 percentage points of annual return to buy that calm. Sharpe 0.42 against 0.59. If the mandate is a growth portfolio, this is the wrong tool. If the mandate is an insurance-style sleeve, it is a reasonable one, though see the drawdown point below before you assume it is safe.

| | Strategic 60/40 | Minimum Variance | Quality-Value | Benchmark |
|---|---|---|---|---|
| Return p.a. | 8.06% | 3.98% | 7.83% | 7.53% |
| Volatility | 10.1% | 5.4% | 10.3% | 10.2% |
| Sharpe | 0.64 | 0.42 | 0.61 | 0.59 |
| Max drawdown | -21.6% | -19.2% | -22.2% | -22.1% |
| Recovered | Mar 2024 | Sep 2024 | Mar 2024 | Mar 2024 |
| Tracking error | 0.83% | 6.80% | 1.93% | n/a |
| Information ratio | 0.58 | -0.55 | 0.15 | n/a |
| Turnover p.a. | 4.7% | 41.4% | 4.2% | 9.1% |
| Trading cost p.a. | 0.15bp | 1.71bp | 0.22bp | n/a |

![Growth of $100 net of costs, and drawdown from the previous peak. Coloured lines are the portfolios, grey is the benchmark.|0.70](figures/performance.png)

## Allocation, selection or factor exposure

Brinson-Fachler run daily and linked with Carino, so the pieces add up to the active return exactly:

| Cumulative vs benchmark | Allocation | Selection | Costs | Benchmark replication | Total |
|---|---|---|---|---|---|
| Strategic 60/40 | +12.6pp | 0.0pp | -0.1pp | +4.4pp | +17.0pp |
| Minimum Variance | -94.7pp | -0.2pp | -0.5pp | +3.5pp | -91.9pp |
| Quality-Value | +10.1pp | -5.0pp | -0.1pp | +4.4pp | +9.5pp |

Allocation is the whole story for the strategic portfolio. Its equity is split on fixed regional weights (60% of equity in the US) against a benchmark whose US share moved from roughly 53% in 2013 to 67% by 2025 on my style-analysis estimate. Early on that made the portfolio overweight America while America won. Since 2023 the same fixed weight has been an underweight, and the US equity effect has turned slightly negative each year since. The bond side swapped 8% of core aggregate into TIPS, worth +3.3pp net over the period.

The 4.4pp "benchmark replication" line is not skill. It is the cost of buying the benchmark as a single fund: ACWI charges 0.32% against roughly 0.05% for the three building blocks, and the blocks also hold small caps that ACWI does not.

The factor story is more interesting than the headline suggests. Selection cost the quality-value portfolio 5.0pp over thirteen years, but that number hides a reversal. The sleeve lost 3.5pp in 2020, another 3.5pp in 2024, then made 1.8pp in 2025 and 6.1pp in the first nine months of 2026. Regressing its active return weekly on ETF factor spreads gives a value beta of 0.09 (t 17) and a quality beta of 0.16 (t 9), against a value premium of -5.4% a year over the period. The factor exposure is real, the factors themselves were a drag for most of the window, and the residual alpha of +0.7% a year (t 1.9) is a coin I would not press too hard.

## What happened under stress

Realised behaviour, using the weights each portfolio actually held at the time:

| | Strategic 60/40 | Minimum Variance | Quality-Value | Benchmark |
|---|---|---|---|---|
| COVID crash, Feb to Mar 2020 | -20.5% | -8.2% | -21.3% | -21.2% |
| 2022 inflation and rate shock | -21.4% | -17.7% | -21.9% | -21.6% |
| 2023 bond rout, 10y to 5% | -8.2% | -5.6% | -8.1% | -8.3% |
| April 2025 tariff shock | -7.4% | -4.0% | -7.5% | -7.5% |
| Global financial crisis (replayed) | -33.7% | -13.0% | -33.1% | -32.6% |

The GFC line holds today's weights through 2007 to 2009 and proxies the ETFs that did not exist yet, so read it as an order of magnitude rather than a measurement.

The number that should bother a portfolio manager is not in that table. Minimum variance ran at 5.4% volatility, roughly half the benchmark, and still drew down 19.2% against the benchmark's 22.1%. Low volatility bought almost no drawdown protection, because the drawdown came from stocks and bonds falling together in 2022, and its answer to equity risk was more duration. It also took until September 2024 to recover, six months longer than the portfolios that fell further.

Rolling six-month correlation between IVV and AGG averaged -0.16 from 2013 to 2020. Since January 2022 it has averaged +0.20 and been positive in 87% of weeks. It sits at 0.58 today. Every one of these portfolios is built on bonds diversifying equities, and for four years they mostly have not.

## How much did turnover and costs matter

Almost nothing. I had assumed costs would be the interesting constraint here, and they are not. At 4.7% one-way turnover a year, the strategic portfolio pays 0.15 basis points a year in trading costs. Multiply my cost assumptions by five and its return falls by one basis point a year. Even minimum variance, at 41% turnover, only loses nine basis points a year at five times costs.

The rebalancing rule, though, is worth more than a percentage point:

| Rule | Return p.a. | Volatility | Max drawdown | Tracking error | Turnover p.a. | Cost p.a. |
|---|---|---|---|---|---|---|
| Buy and hold | 9.18% | 11.7% | -23.7% | 2.28% | 0% | 0.00bp |
| Monthly | 7.89% | 10.1% | -21.6% | 0.78% | 10.7% | 0.35bp |
| Quarterly | 7.96% | 10.1% | -21.6% | 0.81% | 6.5% | 0.21bp |
| Quarterly with 2.5pp band | 8.06% | 10.1% | -21.6% | 0.83% | 4.7% | 0.15bp |
| Annual | 7.88% | 10.1% | -21.5% | 0.88% | 3.1% | 0.10bp |

Letting equities run added 1.1% a year and 1.5 points of volatility, and by the end the portfolio is not 60/40 any more. That is a risk decision dressed up as a performance result. The band rule is the compromise I would defend: it trades less than half as often as monthly rebalancing, for the same risk profile and a slightly better return, because it does not sell winners on the calendar's schedule.

## What I would monitor, and what would change the portfolio

Concentration first. In the strategic portfolio, looking through the funds, NVIDIA is 3.0% of total assets and technology is 19.7%. The quality-value version is worse on this measure, not better: its single largest position is Micron at 4.0% of the portfolio, because VLUE is 21.7% Micron as of 10 September 2026. A value tilt that ends up as a concentrated semiconductor bet is not the diversifier the label implies, and it is the single thing I would put in front of a risk committee.

Second, the stock-bond correlation. If it stays positive, the 40% is a return drag rather than a hedge, and the honest responses are more TIPS, shorter duration, or an explicit allocation to gold. The portfolio carries 2.1 years of rate duration today, a DV01 of about $212 per basis point per million, so a 100bp selloff costs about 2.1% in the bond sleeve and 2.7% once the equity reaction implied by the last three years is added.

Third, the regional weights. The fixed 60% US split inside equities was an overweight for most of the backtest and is now an underweight: look through the funds and the portfolio is 72% United States against the benchmark's 75%. That drift is a live active position nobody decided to take. Either the policy weight follows the index and the bet goes away, or the bet stays and gets stated out loud in the mandate.

What would make me change the portfolios: a stock-bond correlation back below zero for two or three quarters would make the case for adding back duration and trimming TIPS. A value spread that keeps compressing after the 2025 to 2026 run would make me cut the factor sleeve, because the quality-value tilt has now earned a decade of underperformance back in twenty months and that is usually when people add to it. And any single look-through position above 5% would force a trim regardless of what the factor model says, because a 5% single-name loss of 40% is a 2% hit to the whole portfolio, which is not a risk this mandate is paid to take.
