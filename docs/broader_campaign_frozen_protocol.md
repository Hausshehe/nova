# Nova Broader Campaign — Frozen Screening Protocol

Date: 2026-08-19

This protocol freezes the executable screening rules before the broader dataset is acquired or evaluated.

## Frozen universe

- 13 instruments
- 2 discovery timeframes: 1D, 4H
- 4 hypothesis families
- maximum 104 contexts

## Data window

- start: 2010-01-01T00:00:00+00:00
- end: 2025-12-31T23:59:59+00:00

## Split

Every dataset is split chronologically by row count:

- train: 60%
- validation: next 20%
- test: final 20%

No shuffling and no post-result split changes.

## Execution and costs

Signals use only information available at the end of bar i.
A state change is executed at the next bar open.

Costs are frozen at:

- fee: 1 bps per side
- slippage: 1 bps per side
- 4 bps round trip

## Family A — Momentum / trend continuation

Long/flat rule:

- fast SMA = 20 closes
- slow SMA = 50 closes
- enter/hold long when SMA20 >= SMA50
- otherwise flat

No parameter search is permitted.

## Family B — Mean reversion

Long/flat rule:

- rolling mean = 20 closes
- rolling population standard deviation = 20 closes
- enter/hold long when close <= mean - 2 * standard deviation
- exit when close >= mean

No threshold/lookback/exit tuning is permitted.

## Family C — Breakout / volatility expansion

Long/flat rule:

- Donchian breakout level = highest high of the prior 55 completed bars
- volatility filter = current 20-bar true-range average is at least its prior 20-bar true-range average
- enter/hold long when close is strictly above the prior 55-bar high AND the volatility filter is true
- exit when close is strictly below the prior 20 completed-bar low

No parameter search is permitted.

## Family D — Cross-market relative behavior

For each instrument, at each timestamp:

- compute the 20-bar close-to-close return
- within the instrument's asset family and same timeframe, compute the cross-sectional median return and median absolute deviation (MAD)
- enter/hold long when the instrument return is strictly greater than median + MAD
- exit when the instrument return is at or below the cross-sectional median

Only instruments with an exact common timestamp are compared. No forward filling is allowed.

## Screening diagnostics

For every context report:

- train / validation / test final return
- profit factor
- expectancy per trade
- maximum drawdown
- trade count
- test moving-block bootstrap 95% CI on trade returns

Bootstrap is deterministic:

- block length = 5 trades
- samples = 1000
- seed = 42

The bootstrap interval is an uncertainty diagnostic, not proof of future profitability.

## Research decision rule

The 104-context run is exploratory evidence. No single context is promotion evidence.

A family/context can only become a serious candidate when positive after costs, supported by meaningful sample size, not isolated to one market context, and stable across unseen data. Any candidate still requires independent validation before MT5 DEMO work.

After all 104 contexts are evaluated, stop and make the campaign decision:

- YES: credible repeatable evidence exists
- NO: broader campaign does not support a repeatable edge
- INCONCLUSIVE: evidence quality is insufficient and a genuinely pre-planned evidence step remains

Do not create new hypotheses or expand the universe after this checkpoint.
