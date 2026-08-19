# Nova Trading Research — Frozen Hypothesis Status

Date: 2026-08-19

## Current disposition

No strategy tested so far has demonstrated sufficient evidence for MT5 demo or live execution.

The current evidence campaign is deliberately finite. See `docs/research_campaign_policy.md`.

## Dataset used for the current campaign

`data/research/eurusd_daily.csv`

- 2400 daily EURUSD bars
- 2012-12-04 through 2022-03-04
- SHA-256: `e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e`
- Evaluation cost: 4 bps round-trip (1 bps fee + 1 bps slippage per side)

## 1. Horizon / expert adaptation family

**Disposition: REJECTED / NOT PROMOTED.**

Frozen non-overlapping results at 4 bps:

| Configuration | Mean net return | 95% moving-block bootstrap CI |
|---|---:|---:|
| Naive long 8 | -8.052 bps | [-21.89, 5.07] |
| Naive short 8 | +0.052 bps | [-13.09, 13.81] |
| Adaptive 2/4/8 | +0.890 bps | [-14.75, 17.43] |
| Fixed expert 8 | -10.124 bps | [-25.57, 8.66] |

The original overlapping fixed-8 result of approximately +2.43 bps was not robust. Removing overlapping holdings reversed the sign to approximately -10.12 bps.

**Rule:** do not retune the horizon/expert family on this dataset.

## 2. Volatility-normalized mean reversion

Frozen rule:

- 20-bar rolling mean;
- 20-bar rolling population standard deviation;
- enter long at or below mean - 2 sigma;
- exit when close returns to the mean or above;
- next-bar-open execution.

**Final disposition: REJECTED.**

At 4 bps round-trip:

| Segment | Net return | Profit factor | Trades | Decision |
|---|---:|---:|---:|---|
| Train | -9.82% | 0.56 | 23 | REJECT |
| Validation | +10.66% | 14.71 | 12 | INCONCLUSIVE |
| Test | -1.06% | 0.85 | 10 | REJECT |

The positive validation period was too small to clear the predefined evidence gate and therefore was not used to rescue the hypothesis.

**Rule:** do not tune the mean-reversion threshold, lookback, or exit against this dataset.

## 3. Donchian breakout trend following

Frozen rule:

- enter long when close is strictly above the prior 55 completed daily highs;
- exit when close is strictly below the prior 20 completed daily lows;
- next-bar-open execution.

**Final disposition: REJECTED.**

At 4 bps round-trip:

| Segment | Net return | Profit factor | Trades | Decision |
|---|---:|---:|---:|---|
| Train | -3.56% | 0.78 | 8 | REJECT |
| Validation | -7.92% | 0.00 | 2 | REJECT |
| Test | +0.56% | 1.31 | 3 | INCONCLUSIVE |

The test segment was mildly positive but contained only three trades, so it cannot establish evidence of a tradable edge.

**Rule:** do not tune the 55/20 breakout after seeing this result.

## Research interpretation

The first three materially different families have all failed to establish a robust edge on the current evidence source.

This does **not** prove that no trading edge exists. It proves that these tested hypotheses did not provide sufficient evidence under the predefined research rules.

The next experiment must be materially different, frozen before evaluation, and bounded by the finite campaign policy. A positive result among several attempts remains exploratory and must survive independent validation before MT5 work.
