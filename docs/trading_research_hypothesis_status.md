# Nova Trading Research — Frozen Hypothesis Status

Date: 2026-08-19

## Current disposition

**The finite EURUSD trading-research campaign is CLOSED / STOPPED.**

Five materially different frozen hypothesis families were evaluated under the
same causal train / validation / test protocol and 4 bps round-trip costs.
None demonstrated sufficient evidence for MT5 demo or live execution.

Stopping here is a successful research outcome: the campaign answered its
bounded question without turning into an endless strategy-mining loop.

## Dataset used for the campaign

`data/research/eurusd_daily.csv`

- 2400 daily EURUSD bars
- 2012-12-04 through 2022-03-04
- SHA-256: `e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e`
- Evaluation cost: 4 bps round-trip (1 bps fee + 1 bps slippage per side)

## 1. Horizon / expert adaptation family

**Disposition: REJECTED / NOT PROMOTED.**

Frozen non-overlapping results at 4 bps included:

| Configuration | Mean net return | 95% moving-block bootstrap CI |
|---|---:|---:|
| Naive long 8 | -8.052 bps | [-21.89, 5.07] |
| Naive short 8 | +0.052 bps | [-13.09, 13.81] |
| Adaptive 2/4/8 | +0.890 bps | [-14.75, 17.43] |
| Fixed expert 8 | -10.124 bps | [-25.57, 8.66] |

The original overlapping fixed-8 result of approximately +2.43 bps was not
robust; removing overlapping holdings reversed the sign to approximately
-10.12 bps.

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

The positive validation period was too small to clear the predefined gate and
was not used to rescue the hypothesis.

**Rule:** do not tune the mean-reversion threshold, lookback, or exit on this
dataset.

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

The mildly positive test segment contained only three trades and cannot
establish evidence of a tradable edge.

**Rule:** do not tune the 55/20 breakout after seeing this result.

## 4. Friday calendar continuation

Frozen rule:

- if Friday closes above the prior completed trading-day close, request long;
- next-bar-open execution;
- hold one subsequent trading session only.

**Final disposition: REJECTED.**

At 4 bps round-trip:

| Segment | Net return | Profit factor | Trades | Decision |
|---|---:|---:|---:|---|
| Train | -8.93% | 0.6443 | 136 | REJECT |
| Validation | +0.57% | 1.0816 | 51 | REJECT |
| Test | +1.08% | 1.1599 | 49 | INCONCLUSIVE |

The test segment was positive but failed the sample-size gate and was not
sufficient to overcome the rejected train/validation evidence.

**Rule:** do not retune the Friday effect on this dataset.

## 5. Opening-gap continuation — FINAL FAMILY

Frozen rule:

- if the current daily open is above the prior completed daily close, request
  long;
- next-bar-open causal execution;
- hold exactly one subsequent trading session;
- no threshold, tuning, parameter search, AI, regime filter, or execution
  modification.

**Final disposition: REJECTED.**

At 4 bps round-trip:

| Segment | Net return | Profit factor | Expectancy | Trades | Decision |
|---|---:|---:|---:|---:|---|
| Train | -20.07% | 0.7350 | -0.000638 | 342 | REJECT |
| Validation | -10.15% | 0.5652 | -0.000847 | 125 | REJECT |
| Test | +0.12% | 1.0141 | +0.000022 | 80 | REJECT |

The test segment is effectively flat and still fails both the predefined
profit-factor gate (1.15) and minimum-trade gate (100). More importantly,
train and validation are materially negative.

**Rule:** this final family is closed. No sixth same-dataset family is
permitted under the current campaign policy.

## Final campaign conclusion

The five-family campaign did **not** produce evidence sufficient to claim a
robust, promotion-worthy edge on the EURUSD daily dataset.

This does **not** prove that no trading edge exists anywhere. It establishes a
much narrower and useful conclusion:

> Under this fixed dataset, causal execution model, cost model, train /
> validation / test split, and predefined research gates, none of the five
> frozen hypothesis families survived strongly enough to justify progression
> to MT5 demo execution.

## Required next state

**M7 — Research campaign conclusion: STOP TRADING RESEARCH ON THIS EVIDENCE
SOURCE.**

Do not:

- add a sixth strategy on the same EURUSD sample;
- retune any rejected family;
- use AI to filter or rescue failed trades;
- cherry-pick periods or trades;
- reinterpret weak positive test segments as success;
- begin MT5 execution engineering from these results.

A future restart requires a materially changed evidence source or market
question, with provenance frozen before evaluation. Any promising candidate
from a future campaign must also pass independent validation before MT5 work.
